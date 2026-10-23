from __future__ import annotations

import csv
import html
import io
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
import httpx

from pgd_report.models import GLPITicket


class GLPIError(Exception):
    """Exceção customizada para erros de comunicação com a API do GLPI."""
    pass


class GLPIClient:
    """Cliente para a API REST e importador CSV do GLPI (AtendeMais)."""

    STATUS_MAP = {
        1: "Novo",
        2: "Em atendimento (atribuído)",
        3: "Em atendimento (planejado)",
        4: "Pendente (Aguardando Retorno do Cliente)",
        5: "Solucionado",
        6: "Fechado",
    }

    # Status permitidos conforme especificação do usuário
    ALLOWED_STATUSES = {4, 5, 6}

    def __init__(
        self,
        base_url: str,
        user_token: Optional[str] = None,
        app_token: Optional[str] = None,
        user_id: Optional[str] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.user_token = user_token
        self.app_token = app_token
        self.user_id = user_id
        self.session_token: Optional[str] = None
        self._user_info: Dict[str, Any] = {}
        self._http_client: Optional[httpx.Client] = None

    def _get_headers(self, with_session: bool = True) -> Dict[str, str]:
        headers: Dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.app_token:
            headers["App-Token"] = self.app_token
        if with_session and self.session_token:
            headers["Session-Token"] = self.session_token
        return headers

    def _client(self) -> httpx.Client:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.Client(timeout=25.0)
        return self._http_client

    def init_session(self) -> str:
        """Inicia a sessão REST no GLPI e obtém os dados do usuário conectado."""
        if not self.user_token:
            raise GLPIError(
                "GLPI_USER_TOKEN não configurado. Defina a variável no .env ou passe o arquivo CSV."
            )

        url = f"{self.base_url}/initSession"
        headers = self._get_headers(with_session=False)
        headers["Authorization"] = f"user_token {self.user_token}"

        client = self._client()
        try:
            response = client.get(url, headers=headers)
            if response.status_code in (400, 401):
                raise GLPIError(
                    f"Falha de autenticação no GLPI ({response.status_code}): {response.text}."
                )
            response.raise_for_status()
            data = response.json()
            self.session_token = data.get("session_token")
            if not self.session_token:
                raise GLPIError(f"Resposta inválida do GLPI (sem session_token): {data}")

            # Busca informações do usuário conectado (ID 1872 etc)
            self._fetch_session_info(client)
            return self.session_token
        except httpx.RequestError as exc:
            raise GLPIError(
                f"Não foi possível conectar ao GLPI em '{self.base_url}': {exc}.\n"
                "Dica: Se a API estiver instável ou restrita, você pode exportar os chamados em CSV "
                "no AtendeMais e usar: pgd --glpi-csv chamados.csv"
            )

    def _fetch_session_info(self, client: httpx.Client) -> None:
        """Descobre o ID e nome do usuário na sessão ativa."""
        try:
            url = f"{self.base_url}/getFullSession"
            res = client.get(url, headers=self._get_headers())
            if res.status_code == 200:
                session_data = res.json().get("session", {})
                self._user_info = session_data
                if not self.user_id and "glpiID" in session_data:
                    self.user_id = str(session_data["glpiID"])
        except Exception:
            pass

    def kill_session(self) -> None:
        """Encerra a sessão ativa no GLPI."""
        if self.session_token and self._http_client and not self._http_client.is_closed:
            try:
                url = f"{self.base_url}/killSession"
                self._http_client.get(url, headers=self._get_headers())
            except Exception:
                pass
        self.session_token = None
        if self._http_client and not self._http_client.is_closed:
            self._http_client.close()
            self._http_client = None

    def __enter__(self) -> GLPIClient:
        self.init_session()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.kill_session()

    def get_solved_tickets(
        self,
        since: datetime,
        until: Optional[datetime] = None
    ) -> List[GLPITicket]:
        """
        Busca chamados onde LUIS HENRIQUE SOUSA RODRIGUES é Atribuído ou Observador.
        Filtra estritamente por status: Solucionado (5), Fechado (6) ou Pendente (4).
        """
        if not self.session_token:
            self.init_session()

        client = self._client()
        headers = self._get_headers()
        user_id = self.user_id or "1872"

        # 1. Busca Ticket_User vinculados ao usuário
        # type 2 = Atribuído (Técnico), type 3 = Observador
        tu_url = f"{self.base_url}/Ticket_User"
        tu_params = {
            "searchText[users_id]": user_id,
            "sort": "tickets_id",
            "order": "DESC",
            "range": "0-60",
        }

        try:
            tu_res = client.get(tu_url, headers=headers, params=tu_params)
            if tu_res.status_code not in (200, 206):
                return []
            tu_items = tu_res.json()
            if not isinstance(tu_items, list):
                return []
        except httpx.RequestError as exc:
            raise GLPIError(f"Erro ao buscar vínculos de chamados no GLPI: {exc}")

        # Filtra por papel: Atribuído (2) ou Observador (3)
        relevant_tuples = []
        for tu in tu_items:
            role_type = tu.get("type")
            if role_type in (2, 3):
                role_name = "Atribuído" if role_type == 2 else "Observador"
                relevant_tuples.append((str(tu["tickets_id"]), role_name))

        tickets: List[GLPITicket] = []
        seen_ids = set()

        for ticket_id, role_name in relevant_tuples:
            if ticket_id in seen_ids:
                continue
            seen_ids.add(ticket_id)

            try:
                ticket_res = client.get(f"{self.base_url}/Ticket/{ticket_id}", headers=headers)
                if ticket_res.status_code != 200:
                    continue
                item = ticket_res.json()
                status_code = int(item.get("status", 0))

                # REGRA: Somente status Solucionado (5), Fechado (6) ou Pendente (4)
                if status_code not in self.ALLOWED_STATUSES:
                    continue

                # Checagem de datas
                date_mod_dt = self._parse_datetime(item.get("date_mod"))
                solved_dt = self._parse_datetime(item.get("solvedate"))
                closed_dt = self._parse_datetime(item.get("closedate"))

                effective_dt = solved_dt or closed_dt or date_mod_dt
                if not effective_dt:
                    continue

                # Filtro pelo período da semana
                if effective_dt < since:
                    continue
                if until and effective_dt > until:
                    continue

                # Busca descrição do que foi feito no chamado
                description = self._fetch_ticket_action_summary(client, headers, ticket_id, item)

                status_label = self.STATUS_MAP.get(status_code, f"Status {status_code}")
                base_front_url = self.base_url.replace("/apirest.php", "")
                ticket_url = f"{base_front_url}/front/ticket.form.php?id={ticket_id}"

                ticket = GLPITicket(
                    id=ticket_id,
                    title=item.get("name", f"Chamado #{ticket_id}").strip(),
                    status=status_label,
                    role=role_name,
                    solved_date=solved_dt,
                    closed_date=closed_dt,
                    modified_date=date_mod_dt,
                    category=str(item.get("itilcategories_id", "")) if item.get("itilcategories_id") else None,
                    url=ticket_url,
                    description_summary=description,
                    source="api",
                )
                tickets.append(ticket)

            except Exception:
                continue

        return tickets

    def _fetch_ticket_action_summary(
        self,
        client: httpx.Client,
        headers: Dict[str, str],
        ticket_id: str,
        ticket_data: Dict[str, Any],
    ) -> str:
        """
        Extrai uma pequena descrição clara do que foi feito no chamado,
        priorizando a solução ou o último followup registrado.
        """
        # 1. Tenta buscar ITILSolution
        try:
            sol_res = client.get(f"{self.base_url}/Ticket/{ticket_id}/ITILSolution", headers=headers)
            if sol_res.status_code in (200, 206):
                sols = sol_res.json()
                if sols and isinstance(sols, list):
                    last_sol = sols[-1].get("content")
                    cleaned = self._clean_html(last_sol)
                    if cleaned and not "encerrado devido a falta de retorno" in cleaned.lower():
                        return cleaned[:200]
        except Exception:
            pass

        # 2. Tenta buscar ITILFollowup
        try:
            fol_res = client.get(f"{self.base_url}/Ticket/{ticket_id}/ITILFollowup", headers=headers)
            if fol_res.status_code in (200, 206):
                fols = fol_res.json()
                if fols and isinstance(fols, list):
                    # Procura último followup técnico ou com conteúdo real
                    for f in reversed(fols):
                        content = f.get("content", "")
                        cleaned = self._clean_html(content)
                        # Ignora mensagens automáticas de aviso
                        if cleaned and "precisa de uma resposta para continuidade" not in cleaned.lower():
                            return cleaned[:200]
        except Exception:
            pass

        # 3. Fallback: conteúdo/descrição inicial do chamado
        raw_content = ticket_data.get("content", "")
        cleaned_content = self._clean_html(raw_content)
        if cleaned_content:
            return cleaned_content[:180]

        return "Atendimento realizado conforme solicitação."

    @staticmethod
    def _clean_html(raw_html: Optional[str]) -> str:
        """Remove tags HTML, decodifica entidades e normaliza espaços."""
        if not raw_html:
            return ""
        # Decodifica entidades HTML como &#60; &nbsp; etc
        text = html.unescape(raw_html)
        # Remove tags HTML
        text = re.sub(r"<[^>]+>", " ", text)
        # Normaliza quebras de linha e múltiplos espaços
        text = " ".join(text.split())
        return text.strip()

    @staticmethod
    def _parse_datetime(val: Any) -> Optional[datetime]:
        """Converte strings de datas de formatos variados do GLPI para datetime."""
        if not val or not isinstance(val, str) or val in ("null", "None", ""):
            return None
        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d",
            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y %H:%M",
            "%d/%m/%Y",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(val.strip(), fmt)
            except ValueError:
                continue
        return None

    @classmethod
    def parse_csv(
        cls,
        file_path: Path,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None
    ) -> List[GLPITicket]:
        """
        Lê e extrai chamados do CSV garantindo os filtros de LUIS HENRIQUE SOUSA RODRIGUES
        como Atribuído ou Observador, e status Solucionado, Fechado ou Pendente.
        """
        if not file_path.exists():
            raise FileNotFoundError(f"Arquivo CSV não encontrado: {file_path}")

        raw_bytes = file_path.read_bytes()
        text = ""
        for encoding in ["utf-8-sig", "utf-8", "latin-1", "cp1252"]:
            try:
                text = raw_bytes.decode(encoding)
                break
            except UnicodeDecodeError:
                continue

        if not text:
            raise GLPIError(f"Não foi possível decodificar o arquivo CSV '{file_path}'.")

        sample = text[:4096]
        delimiter = ";" if ";" in sample and sample.count(";") > sample.count(",") else ","
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        if not reader.fieldnames:
            raise GLPIError("Arquivo CSV vazio ou sem cabeçalhos válidos.")

        col_map = cls._map_csv_columns(reader.fieldnames)
        tickets: List[GLPITicket] = []

        for row in reader:
            ticket = cls._parse_csv_row(row, col_map, since, until)
            if ticket:
                tickets.append(ticket)

        return tickets

    @classmethod
    def _map_csv_columns(cls, fieldnames: List[str]) -> Dict[str, str]:
        mapping: Dict[str, str] = {}
        for col in fieldnames:
            clean = col.lower().strip()
            clean_ascii = re.sub(r"[áàãâä]", "a", clean)
            clean_ascii = re.sub(r"[éèêë]", "e", clean_ascii)
            clean_ascii = re.sub(r"[íìîï]", "i", clean_ascii)
            clean_ascii = re.sub(r"[óòõôö]", "o", clean_ascii)
            clean_ascii = re.sub(r"[úùûü]", "u", clean_ascii)
            clean_ascii = re.sub(r"[ç]", "c", clean_ascii)

            if clean_ascii in ("id", "chamado", "numero", "codigo"):
                mapping["id"] = col
            elif any(k in clean_ascii for k in ["titulo", "title", "assunto", "nome"]):
                mapping["title"] = col
            elif "status" in clean_ascii or "situacao" in clean_ascii:
                mapping["status"] = col
            elif any(k in clean_ascii for k in ["solucao", "resolvido", "data solucao"]):
                mapping["solved_date"] = col
            elif any(k in clean_ascii for k in ["fechamento", "fechado em", "data fechamento"]):
                mapping["closed_date"] = col
            elif any(k in clean_ascii for k in ["modificacao", "data modificacao", "atualizacao"]):
                mapping["modified_date"] = col
            elif any(k in clean_ascii for k in ["tecnico", "atribuido", "responsavel"]):
                mapping["technician"] = col
            elif "observador" in clean_ascii:
                mapping["observer"] = col
            elif any(k in clean_ascii for k in ["descricao", "solucao descricao", "detalhes"]):
                mapping["description"] = col
            elif "categoria" in clean_ascii:
                mapping["category"] = col
        return mapping

    @classmethod
    def _parse_csv_row(
        cls,
        row: Dict[str, str],
        col_map: Dict[str, str],
        since: Optional[datetime],
        until: Optional[datetime]
    ) -> Optional[GLPITicket]:
        id_col = col_map.get("id")
        title_col = col_map.get("title")
        if not id_col or not title_col:
            return None

        ticket_id = (row.get(id_col) or "").strip()
        title = (row.get(title_col) or "").strip()
        if not ticket_id or not title:
            return None

        # REGRA: Somente se Luis Henrique for Atribuído ou Observador
        tech_val = (row.get(col_map.get("technician", "")) or "").lower()
        obs_val = (row.get(col_map.get("observer", "")) or "").lower()

        is_assigned = any(n in tech_val for n in ["luis henrique", "luishenrique", "1872"])
        is_observer = any(n in obs_val for n in ["luis henrique", "luishenrique", "1872"])

        # Se existirem colunas de atribuído/observador no CSV e o usuário não estiver nelas, descarta
        if (tech_val or obs_val) and not (is_assigned or is_observer):
            return None

        role_name = "Observador" if (is_observer and not is_assigned) else "Atribuído"

        # REGRA: Status Solucionado, Fechado ou Pendente
        status_val = (row.get(col_map.get("status", "")) or "Solucionado").strip()
        status_lower = status_val.lower()
        if not any(s in status_lower for s in ["solucionad", "fechad", "pendent"]):
            return None

        solved_dt = cls._parse_datetime(row.get(col_map.get("solved_date", "")))
        closed_dt = cls._parse_datetime(row.get(col_map.get("closed_date", "")))
        mod_dt = cls._parse_datetime(row.get(col_map.get("modified_date", "")))

        eff_dt = solved_dt or closed_dt or mod_dt
        if since and eff_dt and eff_dt < since:
            return None
        if until and eff_dt and eff_dt > until:
            return None

        desc_raw = row.get(col_map.get("description", "")) or ""
        desc_summary = cls._clean_html(desc_raw)[:200] if desc_raw else "Atendimento realizado conforme solicitação."

        return GLPITicket(
            id=ticket_id,
            title=title,
            status=status_val,
            role=role_name,
            solved_date=solved_dt,
            closed_date=closed_dt,
            modified_date=mod_dt,
            category=(row.get(col_map.get("category", "")) or "").strip() if col_map.get("category") else None,
            description_summary=desc_summary,
            source="csv",
        )
