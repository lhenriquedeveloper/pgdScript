from __future__ import annotations

import re
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
import httpx

from pgd_report.models import GitLabIssue, GitLabMergeRequest


class GitLabError(Exception):
    """Exceção customizada para erros de comunicação com a API do GitLab."""
    pass


class GitLabClient:
    """Cliente para a API REST v4 do GitLab Institucional (git.uft.edu.br)."""

    def __init__(
        self,
        base_url: str,
        token: Optional[str] = None,
        username: Optional[str] = None
    ):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.username = username or "luishenrique.sr"
        self._user_id: Optional[int] = None

    def _get_headers(self) -> Dict[str, str]:
        if not self.token:
            raise GitLabError(
                "GITLAB_TOKEN não configurado. Defina a variável no seu arquivo .env com escopo read_api."
            )
        return {
            "PRIVATE-TOKEN": self.token,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def verify_auth_and_get_user(self) -> Dict[str, Any]:
        """Testa o token de acesso e busca o username e ID do usuário."""
        url = f"{self.base_url}/user"
        try:
            with httpx.Client(timeout=15.0) as client:
                response = client.get(url, headers=self._get_headers())
                if response.status_code == 401:
                    raise GitLabError(
                        "Falha de autenticação no GitLab (401 Unauthorized). "
                        "Verifique se o GITLAB_TOKEN no seu .env está correto e não expirou."
                    )
                response.raise_for_status()
                data = response.json()
                if not self.username and "username" in data:
                    self.username = data["username"]
                if "id" in data:
                    self._user_id = data["id"]
                return data
        except httpx.RequestError as exc:
            raise GitLabError(f"Não foi possível conectar ao GitLab em '{self.base_url}': {exc}")

    def get_issues(
        self,
        since: datetime,
        until: Optional[datetime] = None,
    ) -> List[GitLabIssue]:
        """
        Busca issues com Author Luis Henrique Sousa Rodrigues (luishenrique.sr):
        1. Issues em execução: SOMENTE vinculadas a uma milestone e ongoing/em andamento.
        2. Issues encerradas: SOMENTE se foram fechadas NAQUELA semana específica.
        3. Caso contrário, desconsidera.
        """
        if not self._user_id or not self.username:
            self.verify_auth_and_get_user()

        url = f"{self.base_url}/issues"
        params: Dict[str, Any] = {
            "per_page": 100,
        }
        if self._user_id:
            params["author_id"] = self._user_id
        else:
            params["author_username"] = self.username

        results: List[GitLabIssue] = []
        try:
            with httpx.Client(timeout=25.0) as client:
                page = 1
                while True:
                    params["page"] = page
                    response = client.get(url, headers=self._get_headers(), params=params)
                    if response.status_code == 401:
                        raise GitLabError("Acesso não autorizado no GitLab. Verifique o GITLAB_TOKEN.")
                    response.raise_for_status()

                    items = response.json()
                    if not items or not isinstance(items, list):
                        break

                    for item in items:
                        issue = self._parse_issue(item, since, until)
                        if issue:
                            results.append(issue)

                    next_page = response.headers.get("x-next-page")
                    if not next_page:
                        break
                    page = int(next_page)

        except httpx.RequestError as exc:
            raise GitLabError(f"Erro ao consultar issues no GitLab: {exc}")

        return results

    def _parse_issue(
        self,
        item: Dict[str, Any],
        since: datetime,
        until: Optional[datetime] = None
    ) -> Optional[GitLabIssue]:
        # Validação estrita do autor
        author_data = item.get("author", {})
        if self._user_id and author_data.get("id") and author_data.get("id") != self._user_id:
            return None
        if self.username and author_data.get("username") and author_data.get("username") != self.username:
            return None

        state = item.get("state", "opened")

        milestone = item.get("milestone")
        labels = item.get("labels", []) or []
        updated_dt = self._parse_iso_datetime(item.get("updated_at"))
        closed_dt = self._parse_iso_datetime(item.get("closed_at"))

        # Determina o estágio no fluxo de desenvolvimento:
        # "analise", "desenvolvimento", "disponibilidade no betas", "disponibilidade em produção"
        stage = self._detect_stage(labels, state)

        # REGRA 1: Issues Fechadas
        # "Se estiver com status closed naquela semana, cite no relatório como encerrada naquela semana.
        # Caso não seja naquela semana, desconsidere."
        if state == "closed":
            if not closed_dt:
                return None
            if closed_dt < since:
                return None
            if until and closed_dt > until:
                return None

            return GitLabIssue(
                id=item["id"],
                iid=item.get("iid", item["id"]),
                title=item.get("title", "").strip(),
                project_name=self._extract_project_name(item.get("web_url", "")),
                author_username=self.username,
                state="closed",
                updated_at=updated_dt,
                closed_at=closed_dt,
                web_url=item.get("web_url", ""),
                labels=labels,
                milestone=milestone,
                stage=stage,
                is_ongoing=False,
                closed_this_week=True,
            )

        # REGRA 2: Issues Abertas / Em Execução
        # "só estarão em execução issues vinculadas em uma milestone. Se ela estiver ongoing coloque no relatório em execução."
        if state == "opened":
            # Sem milestone vinculada -> DESCONSIDERAR
            if not milestone:
                return None

            # REGRA: "só estarão em execução issues vinculadas em uma milestone. Se ela estiver ongoing coloque no relatório em execução."
            is_explicit_ongoing = any(
                l.lower() in ("doing", "ongoing", "em andamento", "em execução", "wip")
                for l in labels
            )
            is_updated_in_period = bool(updated_dt and updated_dt >= since)

            if not (is_explicit_ongoing or is_updated_in_period):
                return None


            return GitLabIssue(
                id=item["id"],
                iid=item.get("iid", item["id"]),
                title=item.get("title", "").strip(),
                project_name=self._extract_project_name(item.get("web_url", "")),
                author_username=self.username,
                state="opened",
                updated_at=updated_dt,
                closed_at=None,
                web_url=item.get("web_url", ""),
                labels=labels,
                milestone=milestone,
                stage=stage,
                is_ongoing=True,
                closed_this_week=False,
            )

        return None

    def _detect_stage(self, labels: List[str], state: str) -> str:
        """
        Mapeia labels para o fluxo oficial de desenvolvimento da equipe:
        1. Análise
        2. Desenvolvimento
        3. Disponibilidade no Betas
        4. Disponibilidade em Produção
        """
        labels_lower = [l.lower() for l in labels]

        # Checagem de Estágio por Labels
        for l in labels_lower:
            if any(k in l for k in ["analise", "análise"]):
                return "Análise"
            if any(k in l for k in ["betas", "homolog", "review", "revis"]):
                return "Disponibilidade no Betas"
            if any(k in l for k in ["deploy", "producao", "produção"]):
                return "Disponibilidade em Produção"
            if any(k in l for k in ["doing", "dev", "desenvolvimento", "backend", "frontend"]):
                return "Desenvolvimento"

        if state == "closed":
            return "Disponibilidade em Produção"

        return "Desenvolvimento"

    def get_merge_requests(
        self,
        since: datetime,
        until: Optional[datetime] = None,
        state: str = "all"
    ) -> List[GitLabMergeRequest]:
        """Busca Merge Requests de autoria de Luis Henrique no período."""
        if not self._user_id or not self.username:
            self.verify_auth_and_get_user()

        url = f"{self.base_url}/merge_requests"
        params: Dict[str, Any] = {
            "updated_after": since.isoformat(),
            "per_page": 100,
        }
        if self._user_id:
            params["author_id"] = self._user_id
        else:
            params["author_username"] = self.username
        if state != "all":
            params["state"] = state


        results: List[GitLabMergeRequest] = []
        try:
            with httpx.Client(timeout=25.0) as client:
                page = 1
                while True:
                    params["page"] = page
                    response = client.get(url, headers=self._get_headers(), params=params)
                    if response.status_code == 401:
                        raise GitLabError("Acesso não autorizado no GitLab. Verifique o GITLAB_TOKEN.")
                    response.raise_for_status()

                    items = response.json()
                    if not items or not isinstance(items, list):
                        break

                    for item in items:
                        mr = self._parse_merge_request(item, since, until)
                        if mr:
                            results.append(mr)

                    next_page = response.headers.get("x-next-page")
                    if not next_page:
                        break
                    page = int(next_page)

        except httpx.RequestError as exc:
            raise GitLabError(f"Erro ao consultar merge requests no GitLab: {exc}")

        return results

    def _parse_merge_request(
        self,
        item: Dict[str, Any],
        since: datetime,
        until: Optional[datetime] = None
    ) -> Optional[GitLabMergeRequest]:
        updated_dt = self._parse_iso_datetime(item.get("updated_at"))
        merged_dt = self._parse_iso_datetime(item.get("merged_at"))

        effective_dt = merged_dt or updated_dt
        if effective_dt and effective_dt < since:
            return None
        if until and effective_dt and effective_dt > until:
            return None

        project_name = self._extract_project_name(item.get("web_url", ""))

        return GitLabMergeRequest(
            id=item["id"],
            iid=item.get("iid", item["id"]),
            title=item.get("title", "").strip(),
            project_name=project_name,
            state=item.get("state", "opened"),
            target_branch=item.get("target_branch", ""),
            source_branch=item.get("source_branch", ""),
            updated_at=updated_dt,
            merged_at=merged_dt,
            web_url=item.get("web_url", ""),
            labels=item.get("labels", []) or [],
        )

    @staticmethod
    def _extract_project_name(web_url: str) -> str:
        if not web_url:
            return "GitLab"
        try:
            parts = web_url.split("/-/")
            if len(parts) > 1:
                path = parts[0].split("://")[-1]
                domain_parts = path.split("/")
                return "/".join(domain_parts[1:])
        except Exception:
            pass
        return "GitLab"

    @staticmethod
    def _parse_iso_datetime(val: Any) -> Optional[datetime]:
        if not val or not isinstance(val, str):
            return None
        try:
            clean = val.replace("Z", "+00:00")
            dt = datetime.fromisoformat(clean)
            return dt.replace(tzinfo=None)
        except Exception:
            return None
