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

    # Expressão regular para encontrar referências a chamados (ex: #12345, chamado 12345, fix 12345)
    TICKET_REGEX = re.compile(r"(?:#|chamado|ticket|fix|fixes)[\s\-_:]*(\d{4,7})\b", re.IGNORECASE)

    def __init__(self, mapping_config: Optional[Dict[str, Any]] = None):
        self.mapping_config = mapping_config or {}
        self.metas_rules = self.mapping_config.get("metas", {})
        self.default_glpi_meta = self.mapping_config.get(
            "default_glpi_meta", "Atividades Técnicas e Sustentação (AtendeMais)"
        )
        self.default_gitlab_meta = self.mapping_config.get(
            "default_gitlab_meta", "Desenvolvimento e Projetos (GitLab)"
        )

    def process(
        self,
        tickets: List[GLPITicket],
        issues: List[GitLabIssue],
        merge_requests: List[GitLabMergeRequest],
        start_date: datetime,
        end_date: datetime,
    ) -> ReportData:
        """Executa consolidação, cruzamento e mapeamento de metas."""

        # Mapa de IDs de chamados encontrados nos MRs e Issues
        ticket_to_mrs: Dict[str, List[str]] = {}
        ticket_to_issues: Dict[str, List[str]] = {}

        # 1. Analisa Merge Requests para detectar menções a chamados
        for mr in merge_requests:
            mr_ref = f"MR !{mr.iid}"
            found_ids = self._extract_ticket_ids(f"{mr.title} {mr.source_branch} {mr.target_branch}")
            for tid in found_ids:
                ticket_to_mrs.setdefault(tid, []).append(mr_ref)

        # 2. Analisa Issues para detectar menções a chamados
        for issue in issues:
            issue_ref = f"Issue #{issue.iid}"
            found_ids = self._extract_ticket_ids(f"{issue.title} {' '.join(issue.labels)}")
            for tid in found_ids:
                ticket_to_issues.setdefault(tid, []).append(issue_ref)

        items_by_meta: Dict[str, List[ReportItem]] = {}

        # 3. Transforma Tickets em ReportItems
        for ticket in tickets:
            meta = self._categorize_ticket(ticket)
            linked = []
            if ticket.id in ticket_to_mrs:
                linked.extend(ticket_to_mrs[ticket.id])
            if ticket.id in ticket_to_issues:
                linked.extend(ticket_to_issues[ticket.id])

            date_str = ticket.display_date_str
            status_text = f"Resolvido em {date_str}" if date_str else ticket.status

            item = ReportItem(
                source_type="glpi",
                identifier=f"Chamado #{ticket.id}",
                title=ticket.title,
                status_label=status_text,
                project_or_category=ticket.category or "AtendeMais",
                url=ticket.url or "",
                linked_identifiers=linked,
                meta_name=meta,
            )
            items_by_meta.setdefault(meta, []).append(item)

        # 4. Transforma GitLab Issues em ReportItems
        for issue in issues:
            meta = self._categorize_gitlab_item(issue.project_name, issue.labels)
            item = ReportItem(
                source_type="gitlab_issue",
                identifier=f"Issue #{issue.iid}",
                title=issue.title,
                status_label=issue.status_label,
                project_or_category=issue.project_name,
                url=issue.web_url,
                linked_identifiers=[],
                meta_name=meta,
            )
            items_by_meta.setdefault(meta, []).append(item)

        # 5. Transforma GitLab Merge Requests em ReportItems
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
            "total_issues": len(issues),
            "issues_concluidas": sum(1 for i in issues if i.state == "closed"),
            "total_mrs": len(merge_requests),
            "mrs_mesclados": sum(1 for m in merge_requests if m.state == "merged"),
            "total_entregas": len(tickets) + len(issues) + len(merge_requests),
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
        """Extrai números de chamados mencionados no texto ou branch."""
        matches = self.TICKET_REGEX.findall(text)
        return set(matches)

    def _categorize_ticket(self, ticket: GLPITicket) -> str:
        """Determina em qual meta do PGD o chamado do GLPI se encaixa."""
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
        """Determina em qual meta do PGD a issue ou MR do GitLab se encaixa."""
        if not self.metas_rules:
            return self.default_gitlab_meta

        proj_lower = project_name.lower()
        labels_lower = [l.lower() for l in labels]

        for meta_name, rules in self.metas_rules.items():
            # Checa correspondência por projeto
            for target_proj in rules.get("gitlab_projects", []):
                if target_proj.lower() in proj_lower:
                    return meta_name
            # Checa correspondência por labels
            for target_label in rules.get("gitlab_labels", []):
                if target_label.lower() in labels_lower:
                    return meta_name

        return self.default_gitlab_meta
