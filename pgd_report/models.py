from __future__ import annotations

from datetime import datetime
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field


class GLPITicket(BaseModel):
    """Representa um chamado extraído do GLPI (AtendeMais) via API ou CSV."""
    id: str
    title: str
    status: str = "Resolvido"
    solved_date: Optional[datetime] = None
    closed_date: Optional[datetime] = None
    category: Optional[str] = None
    technician: Optional[str] = None
    url: Optional[str] = None
    content_snippet: Optional[str] = None
    time_spent_minutes: Optional[int] = None
    source: Literal["api", "csv"] = "api"

    @property
    def display_date_str(self) -> str:
        dt = self.solved_date or self.closed_date
        if dt:
            return dt.strftime("%d/%m")
        return ""


class GitLabIssue(BaseModel):
    """Representa uma Issue do GitLab."""
    id: int
    iid: int
    title: str
    project_name: str = ""
    state: str = "opened"  # "opened" ou "closed"
    updated_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    web_url: str = ""
    labels: List[str] = Field(default_factory=list)

    @property
    def status_label(self) -> str:
        return "Concluída" if self.state == "closed" else "Em andamento"


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
    """Item consolidado e categorizado pronto para o relatório do PGD."""
    source_type: Literal["glpi", "gitlab_issue", "gitlab_mr"]
    identifier: str  # ex: "Chamado #12345", "Issue #45", "MR !12"
    title: str
    status_label: str  # ex: "Resolvido em 21/10", "Concluída", "Mesclado"
    project_or_category: str = ""
    url: str = ""
    linked_identifiers: List[str] = Field(default_factory=list)  # ex: ["MR !12", "fix/12345"]
    meta_name: str = ""  # Nome da meta atribuída


class ReportData(BaseModel):
    """Dados consolidados para geração do relatório."""
    period_start: datetime
    period_end: datetime
    tickets: List[GLPITicket] = Field(default_factory=list)
    issues: List[GitLabIssue] = Field(default_factory=list)
    merge_requests: List[GitLabMergeRequest] = Field(default_factory=list)
    items_by_meta: Dict[str, List[ReportItem]] = Field(default_factory=dict)
    summary_stats: Dict[str, Any] = Field(default_factory=dict)
