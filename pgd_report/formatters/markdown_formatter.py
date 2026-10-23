from __future__ import annotations

from typing import Optional
from pgd_report.models import ReportData, ReportItem


def format_markdown(
    report_data: ReportData,
    include_header: bool = False,
    include_links: bool = True,  # Padrão True conforme pedido: "sobre as issues, coloque o link da issue"
    include_stats: bool = False,
) -> str:
    """
    Gera o relatório formatado em Markdown pronto para cópia ou exibição.

    Inclui:
    - Pequena descrição do que foi feito em cada chamado.
    - Link markdown de cada issue do GitLab com seu estágio do fluxo (análise, dev, betas, produção).
    - Tarefa fixa semanal (SIAPE -> SUAP).
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
            f"> **Resumo semanal:** {stats.get('total_tickets', 0)} chamados ({stats.get('tickets_atribuido', 0)} atribuído, "
            f"{stats.get('tickets_observador', 0)} observador) | "
            f"{stats.get('issues_encerradas_semana', 0)} issues encerradas | "
            f"{stats.get('issues_em_execucao', 0)} issues em execução | "
            f"Rotina SIAPE→SUAP concluída"
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

            # 1. Tarefa Fixa
            if item.is_fixed_routine:
                line_parts.append(f"- **{item.title}** ({item.status_label})")
                lines.append(" ".join(line_parts))
                if item.description:
                    lines.append(f"  > *{item.description}*")
                continue

            # 2. Formatação do Identificador (com link para GitLab)
            if item.url and (include_links or item.source_type == "gitlab_issue"):
                ident = f"[{item.identifier}]({item.url})"
            else:
                ident = f"[{item.identifier}]"

            line_parts.append(f"- {ident} {item.title}")

            # Papel no chamado (Atribuído ou Observador)
            if item.role:
                line_parts.append(f"[{item.role}]")

            # Status (ex: Solucionado, Encerrada nesta semana, Em execução)
            if item.status_label:
                line_parts.append(f"({item.status_label})")

            # Vinculações cruzadas (ex: MR !12)
            if item.linked_identifiers:
                line_parts.append(f"[Ref: {', '.join(item.linked_identifiers)}]")

            lines.append(" ".join(line_parts))

            # Pequena descrição do que foi feito no chamado
            if item.description and item.source_type == "glpi":
                lines.append(f"  > *Atendimento: {item.description}*")

        lines.append("")

    return "\n".join(lines).strip()
