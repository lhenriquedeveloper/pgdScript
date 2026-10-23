from __future__ import annotations

import re
from datetime import datetime
from typing import List, Dict, Any, Optional, Set
from pgd_report.models import (
    GLPITicket,
    GitLabIssue,
    GitLabMergeRequest,
    ReportItem,
    ReportData,
)


class ReportProcessor:
    """Processa, cruza referências e categoriza itens do GLPI e GitLab para o PGD."""

    TICKET_REGEX = re.compile(r"(?:#|chamado|ticket|fix|fixes)[\s\-_:]*(\d{4,7})\b", re.IGNORECASE)

    # Tarefa Fixa Semanal Obrigatória
    FIXED_TASK_TITLE = "Extração semanal dos arquivos no SIAPE e upload dos dados no SUAP"
    FIXED_TASK_DESC = "Rotina fixa de sustentação: extração e sincronização dos dados semanais do SIAPE para o SUAP."

    def __init__(self, mapping_config: Optional[Dict[str, Any]] = None):
        self.mapping_config = mapping_config or {}
        self.metas_rules = self.mapping_config.get("metas", {})
        self.default_glpi_meta = self.mapping_config.get(
            "default_glpi_meta", "Atividades Técnicas e Sustentação (AtendeMais)"
        )
        self.default_gitlab_meta = self.mapping_config.get(
            "default_gitlab_meta", "Desenvolvimento e Projetos (GitLab)"
        )
        self.extractor_meta = self.mapping_config.get(
            "extractor_meta", self.default_gitlab_meta
        )

    def process(
        self,
        tickets: List[GLPITicket],
        issues: List[GitLabIssue],
        merge_requests: List[GitLabMergeRequest],
        start_date: datetime,
        end_date: datetime,
    ) -> ReportData:
        """Executa consolidação, cruzamento, inclusão da rotina fixa e mapeamento de metas."""

        # Cruzamento: Mapa de IDs de chamados encontrados nos MRs e Issues
        ticket_to_mrs: Dict[str, List[str]] = {}
        ticket_to_issues: Dict[str, List[str]] = {}

        for mr in merge_requests:
            mr_ref = f"MR !{mr.iid}"
            found_ids = self._extract_ticket_ids(f"{mr.title} {mr.source_branch} {mr.target_branch}")
            for tid in found_ids:
                ticket_to_mrs.setdefault(tid, []).append(mr_ref)

        for issue in issues:
            issue_ref = f"Issue #{issue.iid}"
            found_ids = self._extract_ticket_ids(f"{issue.title} {' '.join(issue.labels)}")
            for tid in found_ids:
                ticket_to_issues.setdefault(tid, []).append(issue_ref)

        items_by_meta: Dict[str, List[ReportItem]] = {}

        # 1. Tarefa Fixa Semanal: Extração SIAPE -> SUAP (Alocada em Desenvolvimento e Projetos)
        fixed_item = ReportItem(
            source_type="fixed_routine",
            identifier="Rotina Fixa",
            title=self.FIXED_TASK_TITLE,
            status_label="Concluída",
            project_or_category="SIAPE / SUAP",
            description=self.FIXED_TASK_DESC,
            meta_name=self.extractor_meta,
            is_fixed_routine=True,
        )
        items_by_meta.setdefault(self.extractor_meta, []).append(fixed_item)


        # 2. Chamados GLPI (AtendeMais)
        for ticket in tickets:
            meta = self._categorize_ticket(ticket)
            linked = []
            if ticket.id in ticket_to_mrs:
                linked.extend(ticket_to_mrs[ticket.id])
            if ticket.id in ticket_to_issues:
                linked.extend(ticket_to_issues[ticket.id])

            date_str = ticket.display_date_str
            if "pendente" in ticket.status.lower():
                status_text = f"Pendente (Aguardando Retorno do Cliente{' em ' + date_str if date_str else ''})"
            elif date_str:
                status_text = f"{ticket.status} em {date_str}"
            else:
                status_text = ticket.status

            item = ReportItem(
                source_type="glpi",
                identifier=f"Chamado #{ticket.id}",
                title=ticket.title,
                status_label=status_text,
                project_or_category=ticket.category or "AtendeMais",
                url=ticket.url or "",
                role=ticket.role,
                description=ticket.description_summary,
                linked_identifiers=linked,
                meta_name=meta,
            )
            items_by_meta.setdefault(meta, []).append(item)

        # 3. GitLab Issues (Abertas com milestone / Fechadas na semana)
        for issue in issues:
            meta = self._categorize_gitlab_item(issue.project_name, issue.labels)

            if issue.closed_this_week:
                closed_dt_str = issue.closed_at.strftime("%d/%m") if issue.closed_at else ""
                status_text = f"Encerrada nesta semana{' em ' + closed_dt_str if closed_dt_str else ''}"
            elif issue.is_ongoing:
                stage_label = issue.stage or "Desenvolvimento"
                ms_info = f" / {issue.milestone_title}" if issue.milestone_title else ""
                status_text = f"Em execução - {stage_label}{ms_info}"
            else:
                status_text = "Em andamento"

            item = ReportItem(
                source_type="gitlab_issue",
                identifier=f"Issue #{issue.iid}",
                title=issue.title,
                status_label=status_text,
                project_or_category=issue.project_name,
                url=issue.web_url,
                stage=issue.stage,
                milestone_title=issue.milestone_title,
                linked_identifiers=[],
                meta_name=meta,
            )
            items_by_meta.setdefault(meta, []).append(item)

        # 4. GitLab Merge Requests
        for mr in merge_requests:
            meta = self._categorize_gitlab_item(mr.project_name, mr.labels)
            item = ReportItem(
                source_type="gitlab_mr",
                identifier=f"MR !{mr.iid}",
                title=mr.title,
                status_label=mr.status_label,
                project_or_category=mr.project_name,
                url=mr.web_url,
                linked_identifiers=[],
                meta_name=meta,
            )
            items_by_meta.setdefault(meta, []).append(item)

        # Estatísticas sumárias
        stats = {
            "total_tickets": len(tickets),
            "tickets_atribuido": sum(1 for t in tickets if t.role == "Atribuído"),
            "tickets_observador": sum(1 for t in tickets if t.role == "Observador"),
            "total_issues": len(issues),
            "issues_encerradas_semana": sum(1 for i in issues if i.closed_this_week),
            "issues_em_execucao": sum(1 for i in issues if i.is_ongoing),
            "total_mrs": len(merge_requests),
            "tarefa_fixa_siape_suap": True,
        }

        return ReportData(
            period_start=start_date,
            period_end=end_date,
            tickets=tickets,
            issues=issues,
            merge_requests=merge_requests,
            items_by_meta=items_by_meta,
            summary_stats=stats,
        )

    def _extract_ticket_ids(self, text: str) -> Set[str]:
        return set(self.TICKET_REGEX.findall(text))

    def _categorize_ticket(self, ticket: GLPITicket) -> str:
        if not self.metas_rules:
            return self.default_glpi_meta

        category = (ticket.category or "").lower()
        title = ticket.title.lower()

        for meta_name, rules in self.metas_rules.items():
            cat_rules = [c.lower() for c in rules.get("glpi_categories", [])]
            for c in cat_rules:
                if c in category or c in title:
                    return meta_name

        return self.default_glpi_meta

    def _categorize_gitlab_item(self, project_name: str, labels: List[str]) -> str:
        if not self.metas_rules:
            return self.default_gitlab_meta

        proj_lower = project_name.lower()
        labels_lower = [l.lower() for l in labels]

        for meta_name, rules in self.metas_rules.items():
            for target_proj in rules.get("gitlab_projects", []):
                if target_proj.lower() in proj_lower:
                    return meta_name
            for target_label in rules.get("gitlab_labels", []):
                if target_label.lower() in labels_lower:
                    return meta_name

        return self.default_gitlab_meta
