from __future__ import annotations

from datetime import datetime
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field


class GLPITicket(BaseModel):
    """Representa um chamado do GLPI (AtendeMais)."""
    id: str
    title: str
    status: str = "Solucionado"  # "Solucionado", "Fechado", "Pendente (Aguardando Retorno do Cliente)"
    role: Literal["Atribuído", "Observador"] = "Atribuído"
    solved_date: Optional[datetime] = None
    closed_date: Optional[datetime] = None
    modified_date: Optional[datetime] = None
    category: Optional[str] = None
    technician: Optional[str] = None
    url: Optional[str] = None
    description_summary: Optional[str] = None  # Pequena descrição do que foi feito no chamado
    time_spent_minutes: Optional[int] = None
    source: Literal["api", "csv"] = "api"

    @property
    def display_date_str(self) -> str:
        dt = self.solved_date or self.closed_date or self.modified_date
        if dt:
            return dt.strftime("%d/%m")
        return ""


class GitLabIssue(BaseModel):
    """Representa uma Issue do GitLab criada por Luis Henrique."""
    id: int
    iid: int
    title: str
    project_name: str = ""
    author_username: str = ""
    state: str = "opened"  # "opened" ou "closed"
    updated_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    web_url: str = ""
    labels: List[str] = Field(default_factory=list)
    milestone: Optional[Dict[str, Any]] = None
    stage: Optional[str] = None  # "Análise", "Desenvolvimento", "Disponibilidade no Betas", "Disponibilidade em Produção"
    is_ongoing: bool = False
    closed_this_week: bool = False

    @property
    def milestone_title(self) -> Optional[str]:
        if isinstance(self.milestone, dict):
            return self.milestone.get("title")
        return None


class GitLabMergeRequest(BaseModel):
    """Representa um Merge Request do GitLab."""
    id: int
    iid: int
    title: str
    project_name: str = ""
    state: str = "opened"  # "opened", "merged", "closed"
    target_branch: str = ""
    source_branch: str = ""
    updated_at: Optional[datetime] = None
    merged_at: Optional[datetime] = None
    web_url: str = ""
    labels: List[str] = Field(default_factory=list)

    @property
    def status_label(self) -> str:
        if self.state == "merged":
            return "Mesclado"
        elif self.state == "closed":
            return "Fechado"
        return "Aberto/Revisão"


class ReportItem(BaseModel):
    """Item consolidado e categorizado para o relatório do PGD."""
    source_type: Literal["glpi", "gitlab_issue", "gitlab_mr", "fixed_routine"]
    identifier: str  # ex: "Chamado #12345", "Issue #45", "MR !12", "Rotina Fixa"
    title: str
    status_label: str  # ex: "Solucionado em 20/10", "Encerrada nesta semana em 19/10", "Em execução - Desenvolvimento"
    project_or_category: str = ""
    url: str = ""
    role: Optional[str] = None  # "Atribuído" ou "Observador"
    description: Optional[str] = None  # Pequena descrição do que foi feito
    stage: Optional[str] = None  # Fluxo: Análise, Desenvolvimento, Betas, Produção
    milestone_title: Optional[str] = None
    linked_identifiers: List[str] = Field(default_factory=list)
    meta_name: str = ""
    is_fixed_routine: bool = False


class ReportData(BaseModel):
    """Dados consolidados para geração do relatório."""
    period_start: datetime
    period_end: datetime
    tickets: List[GLPITicket] = Field(default_factory=list)
    issues: List[GitLabIssue] = Field(default_factory=list)
    merge_requests: List[GitLabMergeRequest] = Field(default_factory=list)
    items_by_meta: Dict[str, List[ReportItem]] = Field(default_factory=dict)
    summary_stats: Dict[str, Any] = Field(default_factory=dict)
