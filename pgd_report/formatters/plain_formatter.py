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
            status = f" ({item.status_label})" if item.status_label else ""
            ref = f" [Ref: {', '.join(item.linked_identifiers)}]" if item.linked_identifiers else ""
            lines.append(f"• {item.identifier}: {item.title}{status}{ref}")
        lines.append("")

    return "\n".join(lines).strip()
