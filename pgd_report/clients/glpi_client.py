from __future__ import annotations

import csv
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
        4: "Pendente",
        5: "Solucionado",
        6: "Fechado",
    }

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

    def init_session(self) -> str:
        """Inicia a sessão REST no GLPI e armazena o Session-Token."""
        if not self.user_token:
            raise GLPIError(
                "GLPI_USER_TOKEN não configurado. Defina a variável no .env ou passe o arquivo CSV."
            )

        url = f"{self.base_url}/initSession"
        headers = self._get_headers(with_session=False)
        headers["Authorization"] = f"user_token {self.user_token}"

        try:
            with httpx.Client(timeout=15.0) as client:
                response = client.get(url, headers=headers)
                if response.status_code == 401 or response.status_code == 400:
                    raise GLPIError(
                        f"Falha de autenticação no GLPI ({response.status_code}): "
                        f"{response.text}. Verifique se o GLPI_USER_TOKEN e GLPI_APP_TOKEN estão corretos "
                        "ou se a API REST está habilitada na sua instância do AtendeMais."
                    )
                response.raise_for_status()
                data = response.json()
                self.session_token = data.get("session_token")
                if not self.session_token:
                    raise GLPIError(f"Resposta inválida do GLPI (sem session_token): {data}")
                
                # Tenta recuperar dados do usuário da sessão atual
                self._fetch_session_info(client)
                return self.session_token
        except httpx.RequestError as exc:
            raise GLPIError(
                f"Não foi possível conectar ao GLPI em '{self.base_url}': {exc}.\n"
                "Dica: Se a API estiver restrita a administradores, use a exportação CSV do sistema "
                "com o comando: pgd-report --glpi-csv chamados.csv"
            )

    def _fetch_session_info(self, client: httpx.Client) -> None:
        """Obtém os detalhes da sessão para descobrir o ID do técnico autenticado."""
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
        if not self.session_token:
            return
        url = f"{self.base_url}/killSession"
        try:
            with httpx.Client(timeout=10.0) as client:
                client.get(url, headers=self._get_headers())
        except Exception:
            pass
        finally:
            self.session_token = None

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
        """Busca chamados solucionados ou fechados atribuídos ao técnico no período."""
        if not self.session_token:
            self.init_session()

        headers = self._get_headers()
        tickets: List[GLPITicket] = []
        since_str = since.strftime("%Y-%m-%d %H:%M:%S")

        # 1. Estratégia direta via endpoint /Ticket com ordenação
        url = f"{self.base_url}/Ticket"
        params = {
            "range": "0-150",
            "sort": "date_mod",
            "order": "DESC",
        }

        try:
            with httpx.Client(timeout=20.0) as client:
                response = client.get(url, headers=headers, params=params)
                
                # Se /Ticket padrão retornar 200 ou 206 (Partial Content)
                if response.status_code in (200, 206):
                    items = response.json()
                    if isinstance(items, list):
                        for item in items:
                            ticket = self._parse_api_ticket(item, since, until)
                            if ticket:
                                tickets.append(ticket)
                        return tickets

                # 2. Estratégia alternativa via Search Engine do GLPI (/search/Ticket)
                search_url = f"{self.base_url}/search/Ticket"
                # Critério para tickets com status solucionado(5) ou fechado(6)
                search_params = {
                    "criteria[0][field]": "12",  # 12 = Status no GLPI
                    "criteria[0][searchtype]": "equals",
                    "criteria[0][value]": "5",
                    "criteria[1][link]": "OR",
                    "criteria[1][field]": "12",
                    "criteria[1][searchtype]": "equals",
                    "criteria[1][value]": "6",
                    "range": "0-100",
                    "order": "DESC",
                    "sort": "19",  # 19 = Data de Modificação
                }
                search_res = client.get(search_url, headers=headers, params=search_params)
                if search_res.status_code in (200, 206):
                    data = search_res.json()
                    rows = data.get("data", [])
                    for row in rows:
                        ticket = self._parse_search_row(row, since, until)
                        if ticket:
                            tickets.append(ticket)

        except httpx.RequestError as exc:
            raise GLPIError(f"Erro ao consultar chamados no GLPI: {exc}")

        return tickets

    def _parse_api_ticket(
        self,
        item: Dict[str, Any],
        since: datetime,
        until: Optional[datetime] = None
    ) -> Optional[GLPITicket]:
        """Interpreta um objeto de ticket vindo de /Ticket."""
        solvedate_str = item.get("solvedate")
        closedate_str = item.get("closedate")
        date_mod_str = item.get("date_mod")

        solved_dt = self._parse_datetime(solvedate_str)
        close_dt = self._parse_datetime(closedate_str)
        mod_dt = self._parse_datetime(date_mod_str)

        effective_dt = solved_dt or close_dt or mod_dt
        if not effective_dt:
            return None

        # Filtra pelo período
        if effective_dt < since:
            return None
        if until and effective_dt > until:
            return None

        status_code = item.get("status", 1)
        # Prioriza tickets solucionados (5) ou fechados (6), mas aceita se tiver solvedate
        if status_code not in (5, 6) and not solved_dt:
            return None

        status_name = self.STATUS_MAP.get(int(status_code), f"Status {status_code}")
        ticket_id = str(item.get("id", ""))
        title = item.get("name") or f"Chamado #{ticket_id}"

        # Monta URL amigável para o chamado no GLPI
        base_front_url = self.base_url.replace("/apirest.php", "")
        ticket_url = f"{base_front_url}/front/ticket.form.php?id={ticket_id}"

        return GLPITicket(
            id=ticket_id,
            title=title.strip(),
            status=status_name,
            solved_date=solved_dt,
            closed_date=close_dt,
            category=str(item.get("itilcategories_id", "")) if item.get("itilcategories_id") else None,
            url=ticket_url,
            content_snippet=str(item.get("content", ""))[:200] if item.get("content") else None,
            source="api",
        )

    def _parse_search_row(
        self,
        row: Dict[str, Any],
        since: datetime,
        until: Optional[datetime] = None
    ) -> Optional[GLPITicket]:
        """Interpreta linha vinda de /search/Ticket."""
        ticket_id = str(row.get("2", row.get("id", "")))
        title = str(row.get("1", row.get("name", f"Chamado #{ticket_id}")))
        status_val = row.get("12", "5")
        
        # 17 = solvedate, 16 = closedate, 19 = date_mod
        solved_str = row.get("17") or row.get("solvedate")
        close_str = row.get("16") or row.get("closedate")
        mod_str = row.get("19") or row.get("date_mod")

        solved_dt = self._parse_datetime(solved_str)
        close_dt = self._parse_datetime(close_str)
        mod_dt = self._parse_datetime(mod_str)

        effective_dt = solved_dt or close_dt or mod_dt
        if not effective_dt or effective_dt < since:
            return None
        if until and effective_dt > until:
            return None

        base_front_url = self.base_url.replace("/apirest.php", "")
        ticket_url = f"{base_front_url}/front/ticket.form.php?id={ticket_id}"

        return GLPITicket(
            id=ticket_id,
            title=title.strip(),
            status="Solucionado" if str(status_val) == "5" else "Fechado",
            solved_date=solved_dt,
            closed_date=close_dt,
            url=ticket_url,
            source="api",
        )

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
        Lê e extrai chamados a partir de um arquivo CSV exportado pelo frontend do GLPI.
        Suporta automaticamente delimitadores (;, ,) e codificações (utf-8, latin-1).
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

        # Tenta detectar dialeto do CSV
        sample = text[:4096]
        delimiter = ";" if ";" in sample and sample.count(";") > sample.count(",") else ","

        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        if not reader.fieldnames:
            raise GLPIError("Arquivo CSV vazio ou sem cabeçalhos válidos.")

        # Identifica colunas flexivelmente
        col_map = cls._map_csv_columns(reader.fieldnames)
        tickets: List[GLPITicket] = []

        for row in reader:
            ticket = cls._parse_csv_row(row, col_map, since, until)
            if ticket:
                tickets.append(ticket)

        return tickets

    @classmethod
    def _map_csv_columns(cls, fieldnames: List[str]) -> Dict[str, str]:
        """Mapeia os nomes das colunas do CSV para chaves padronizadas."""
        mapping: Dict[str, str] = {}
        for col in fieldnames:
            clean = col.lower().strip()
            # Remove acentos para comparação
            clean_ascii = re.sub(r"[áàãâä]", "a", clean)
            clean_ascii = re.sub(r"[éèêë]", "e", clean_ascii)
            clean_ascii = re.sub(r"[íìîï]", "i", clean_ascii)
            clean_ascii = re.sub(r"[óòõôö]", "o", clean_ascii)
            clean_ascii = re.sub(r"[úùûü]", "u", clean_ascii)
            clean_ascii = re.sub(r"[ç]", "c", clean_ascii)

            if clean_ascii in ("id", "chamado", "numero", "codigo", "id do chamado"):
                mapping["id"] = col
            elif any(k in clean_ascii for k in ["titulo", "title", "assunto", "nome", "descricao sumaria"]):
                mapping["title"] = col
            elif "status" in clean_ascii or "situacao" in clean_ascii:
                mapping["status"] = col
            elif any(k in clean_ascii for k in ["solucao", "resolvido", "data solucao", "solucao em"]):
                mapping["solved_date"] = col
            elif any(k in clean_ascii for k in ["fechamento", "fechado em", "data fechamento"]):
                mapping["closed_date"] = col
            elif any(k in clean_ascii for k in ["abertura", "data criacao", "data de abertura"]):
                mapping["creation_date"] = col
            elif any(k in clean_ascii for k in ["categoria", "categoria itil"]):
                mapping["category"] = col
            elif any(k in clean_ascii for k in ["tecnico", "atribuido", "responsavel"]):
                mapping["technician"] = col
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

        status_col = col_map.get("status")
        status = (row.get(status_col) or "Resolvido").strip() if status_col else "Resolvido"

        solved_col = col_map.get("solved_date")
        closed_col = col_map.get("closed_date")
        cat_col = col_map.get("category")
        tech_col = col_map.get("technician")

        solved_dt = cls._parse_datetime(row.get(solved_col)) if solved_col else None
        closed_dt = cls._parse_datetime(row.get(closed_col)) if closed_col else None

        effective_dt = solved_dt or closed_dt

        # Filtro de data caso especificado
        if since and effective_dt and effective_dt < since:
            return None
        if until and effective_dt and effective_dt > until:
            return None

        return GLPITicket(
            id=ticket_id,
            title=title,
            status=status,
            solved_date=solved_dt,
            closed_date=closed_dt,
            category=(row.get(cat_col) or "").strip() if cat_col else None,
            technician=(row.get(tech_col) or "").strip() if tech_col else None,
            source="csv",
        )
