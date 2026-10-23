from __future__ import annotations

from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
import httpx

from pgd_report.models import GitLabIssue, GitLabMergeRequest


class GitLabError(Exception):
    """Exceção customizada para erros de comunicação com a API do GitLab."""
    pass


class GitLabClient:
    """Cliente para a API REST v4 do GitLab Institucional (ex: git.uft.edu.br)."""

    def __init__(
        self,
        base_url: str,
        token: Optional[str] = None,
        username: Optional[str] = None
    ):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.username = username
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
        """Testa o token de acesso e busca o username e ID do usuário caso não informados."""
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
        state: str = "all"
    ) -> List[GitLabIssue]:
        """
        Busca issues atribuídas ao usuário ou atualizadas após a data `since`.
        """
        # Garante que temos o username
        if not self.username:
            self.verify_auth_and_get_user()

        url = f"{self.base_url}/issues"
        params: Dict[str, Any] = {
            "scope": "all",
            "assignee_username": self.username,
            "updated_after": since.isoformat(),
            "per_page": 100,
        }
        if state != "all":
            params["state"] = state

        results: List[GitLabIssue] = []
        try:
            with httpx.Client(timeout=20.0) as client:
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

                    # Verifica cabeçalhos de paginação
                    next_page = response.headers.get("x-next-page")
                    if not next_page:
                        break
                    page = int(next_page)

        except httpx.RequestError as exc:
            raise GitLabError(f"Erro ao consultar issues no GitLab: {exc}")

        return results

    def get_merge_requests(
        self,
        since: datetime,
        until: Optional[datetime] = None,
        state: str = "all"
    ) -> List[GitLabMergeRequest]:
        """
        Busca Merge Requests de autoria do usuário atualizados após a data `since`.
        """
        if not self.username:
            self.verify_auth_and_get_user()

        url = f"{self.base_url}/merge_requests"
        params: Dict[str, Any] = {
            "scope": "all",
            "author_username": self.username,
            "updated_after": since.isoformat(),
            "per_page": 100,
        }
        if state != "all":
            params["state"] = state

        results: List[GitLabMergeRequest] = []
        try:
            with httpx.Client(timeout=20.0) as client:
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

    def _parse_issue(
        self,
        item: Dict[str, Any],
        since: datetime,
        until: Optional[datetime] = None
    ) -> Optional[GitLabIssue]:
        updated_dt = self._parse_iso_datetime(item.get("updated_at"))
        closed_dt = self._parse_iso_datetime(item.get("closed_at"))

        # Filtro de data caso especificado
        effective_dt = closed_dt or updated_dt
        if effective_dt and effective_dt < since:
            return None
        if until and effective_dt and effective_dt > until:
            return None

        # Extrai nome do projeto a partir do web_url se não estiver direto
        project_name = self._extract_project_name(item.get("web_url", ""))

        return GitLabIssue(
            id=item["id"],
            iid=item.get("iid", item["id"]),
            title=item.get("title", "").strip(),
            project_name=project_name,
            state=item.get("state", "opened"),
            updated_at=updated_dt,
            closed_at=closed_dt,
            web_url=item.get("web_url", ""),
            labels=item.get("labels", []) or [],
        )

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
        """Extrai o slug do projeto (ex: 'dti/atendemais') a partir da URL web."""
        if not web_url:
            return "GitLab"
        try:
            # Ex: https://git.uft.edu.br/sistemas/frotas/-/issues/45 -> sistemas/frotas
            parts = web_url.split("/-/")
            if len(parts) > 1:
                path = parts[0].split("://")[-1]
                # remove o domínio
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
            # Normaliza timezone se terminar com Z
            clean = val.replace("Z", "+00:00")
            dt = datetime.fromisoformat(clean)
            # Remove timezone info para comparações homogêneas com datetime.now() naive
            return dt.replace(tzinfo=None)
        except Exception:
            return None
