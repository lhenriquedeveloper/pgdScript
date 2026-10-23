from __future__ import annotations

from pgd_report.models import ReportData


def format_plain(report_data: ReportData) -> str:
    """
    Formata o relatório em texto puro sem formatação markdown (para campos restritos do PGD).
    """
    lines = []
    for meta_name, items in report_data.items_by_meta.items():
        if not items:
            continue

        lines.append(f"[{meta_name.upper()}]")
        for item in items:
            if item.is_fixed_routine:
                lines.append(f"• {item.title} ({item.status_label})")
                if item.description:
                    lines.append(f"  Obs: {item.description}")
                continue

            role_str = f" [{item.role}]" if item.role else ""
            status = f" ({item.status_label})" if item.status_label else ""
            ref = f" [Ref: {', '.join(item.linked_identifiers)}]" if item.linked_identifiers else ""
            url_str = f" <{item.url}>" if item.url else ""

            lines.append(f"• {item.identifier}{role_str}: {item.title}{status}{ref}{url_str}")
            if item.description and item.source_type == "glpi":
                lines.append(f"  Atendimento: {item.description}")

        lines.append("")

    return "\n".join(lines).strip()
