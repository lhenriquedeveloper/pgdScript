from __future__ import annotations

import html
from pgd_report.models import ReportData


def format_html(
    report_data: ReportData,
    include_header: bool = False,
    include_links: bool = True,
    include_stats: bool = False,
) -> str:
    """
    Formata o relatório em HTML (Rich Text) ideal para colar diretamente em
    editores visuais/WYSIWYG do sistema do PGD (SUAP, etc.) com links azuis e clicáveis.
    """
    lines = []

    dt_start = report_data.period_start.strftime("%d/%m/%Y")
    dt_end = report_data.period_end.strftime("%d/%m/%Y")

    if include_header:
        lines.append(f"<h2>Relatório de Atividades PGD ({dt_start} a {dt_end})</h2>")

    if include_stats:
        stats = report_data.summary_stats
        lines.append(
            f"<p><em>Resumo semanal: {stats.get('total_tickets', 0)} chamados "
            f"({stats.get('tickets_atribuido', 0)} atribuído, {stats.get('tickets_observador', 0)} observador) | "
            f"{stats.get('issues_encerradas_semana', 0)} issues encerradas | "
            f"{stats.get('issues_em_execucao', 0)} issues em execução | "
            f"Rotina SIAPE→SUAP concluída</em></p>"
        )

    if not report_data.items_by_meta:
        lines.append("<p><em>Nenhuma atividade encontrada no período selecionado.</em></p>")
        return "\n".join(lines)

    for meta_name, items in report_data.items_by_meta.items():
        if not items:
            continue

        lines.append(f"<p><strong>{html.escape(meta_name)}</strong></p>")
        lines.append("<ul>")
        for item in items:
            # 1. Tarefa Fixa
            if item.is_fixed_routine:
                desc_html = f"<br>&nbsp;&nbsp;<em>{html.escape(item.description)}</em>" if item.description else ""
                lines.append(
                    f"  <li><strong>{html.escape(item.title)}</strong> ({html.escape(item.status_label)}){desc_html}</li>"
                )
                continue

            # 2. Identificador com ou sem link
            escaped_ident = html.escape(item.identifier)
            if item.url and include_links:
                ident_html = f'<a href="{html.escape(item.url)}" target="_blank" rel="noopener noreferrer">{escaped_ident}</a>'
            else:
                ident_html = f"<strong>{escaped_ident}</strong>"

            role_str = f" [{html.escape(item.role)}]" if item.role else ""
            status_str = f" ({html.escape(item.status_label)})" if item.status_label else ""
            ref_str = f" [Ref: {html.escape(', '.join(item.linked_identifiers))}]" if item.linked_identifiers else ""
            title_str = html.escape(item.title)

            item_line = f"  <li>{ident_html} {title_str}{role_str}{status_str}{ref_str}"

            if item.description and item.source_type == "glpi":
                item_line += f"<br>&nbsp;&nbsp;<em>Atendimento: {html.escape(item.description)}</em>"

            item_line += "</li>"
            lines.append(item_line)

        lines.append("</ul>")

    return "\n".join(lines)
