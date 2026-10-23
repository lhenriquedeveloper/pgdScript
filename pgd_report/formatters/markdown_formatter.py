from __future__ import annotations

from typing import Optional
from pgd_report.models import ReportData, ReportItem


def format_markdown(
    report_data: ReportData,
    include_header: bool = False,
    include_links: bool = False,
    include_stats: bool = False,
) -> str:
    """
    Gera o relatório formatado em Markdown pronto para cópia ou exibição.

    Exemplo de formato gerado:
    ### Atividades Técnicas e Sustentação (AtendeMais)
    - [Chamado #12345] Correção de permissão de acesso ao módulo X (Resolvido em 21/10)
    - [Chamado #12389] Análise de inconsistência de dados na tabela Y (Resolvido em 22/10)

    ### Desenvolvimento e Projetos (GitLab)
    - [Issue #45] Implementação de filtro de busca por demandante (Concluída)
    - [MR !12] Refatoração de endpoints da API de frotas (Mesclado)
    - [Issue #52] Modelagem de novos relatórios de ocupação (Em andamento)
    """
    lines = []

    dt_start = report_data.period_start.strftime("%d/%m/%Y")
    dt_end = report_data.period_end.strftime("%d/%m/%Y")

    if include_header:
        lines.append(f"## Relatório de Atividades PGD ({dt_start} a {dt_end})")
        lines.append("")

    if include_stats:
        stats = report_data.summary_stats
        lines.append(
            f"> **Resumo semanal:** {stats.get('total_tickets', 0)} chamados atendidos | "
            f"{stats.get('issues_concluidas', 0)}/{stats.get('total_issues', 0)} issues concluídas | "
            f"{stats.get('mrs_mesclados', 0)}/{stats.get('total_mrs', 0)} MRs mesclados"
        )
        lines.append("")

    if not report_data.items_by_meta:
        lines.append("_Nenhuma atividade encontrada no período selecionado._")
        return "\n".join(lines)

    for meta_name, items in report_data.items_by_meta.items():
        if not items:
            continue

        lines.append(f"### {meta_name}")
        for item in items:
            line_parts = []
            
            # Formatação do identificador com link opcional
            if include_links and item.url:
                ident = f"[{item.identifier}]({item.url})"
            else:
                ident = f"[{item.identifier}]"

            # Título e Status
            line_parts.append(f"- {ident} {item.title}")
            if item.status_label:
                line_parts.append(f"({item.status_label})")

            # Vinculações (ex: cruzamento com MR/Issue)
            if item.linked_identifiers:
                line_parts.append(f"[Ref: {', '.join(item.linked_identifiers)}]")

            lines.append(" ".join(line_parts))

        lines.append("")

    return "\n".join(lines).strip()
