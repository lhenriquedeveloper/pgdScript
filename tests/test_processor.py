from datetime import datetime
from pgd_report.models import GLPITicket, GitLabIssue, GitLabMergeRequest
from pgd_report.processor import ReportProcessor


def test_processor_links_ticket_with_mr_and_issue():
    tickets = [
        GLPITicket(
            id="12345",
            title="Correção de permissão de acesso ao módulo X",
            status="Solucionado",
            solved_date=datetime(2026, 10, 21, 15, 30),
            category="Sistemas",
        ),
        GLPITicket(
            id="12389",
            title="Análise de inconsistência de dados na tabela Y",
            status="Solucionado",
            solved_date=datetime(2026, 10, 22, 10, 0),
            category="Sistemas",
        ),
    ]

    issues = [
        GitLabIssue(
            id=101,
            iid=45,
            title="Implementação de filtro de busca por demandante",
            project_name="sistemas/frotas",
            state="closed",
            labels=["feature"],
        ),
        GitLabIssue(
            id=102,
            iid=52,
            title="Modelagem de novos relatórios de ocupação",
            project_name="sistemas/frotas",
            state="opened",
            labels=["feature"],
        ),
    ]

    mrs = [
        GitLabMergeRequest(
            id=201,
            iid=12,
            title="Refatoração de endpoints da API de frotas (fix #12345)",
            project_name="sistemas/frotas-api",
            state="merged",
            source_branch="fix/12345-permissao",
            target_branch="main",
            labels=["refactor"],
        )
    ]

    processor = ReportProcessor()
    report = processor.process(
        tickets=tickets,
        issues=issues,
        merge_requests=mrs,
        start_date=datetime(2026, 10, 16),
        end_date=datetime(2026, 10, 23),
    )

    assert report.summary_stats["total_tickets"] == 2
    assert report.summary_stats["total_issues"] == 2
    assert report.summary_stats["total_mrs"] == 1
    assert report.summary_stats["issues_concluidas"] == 1
    assert report.summary_stats["mrs_mesclados"] == 1

    # Verifica se o chamado #12345 vinculou o MR !12
    glpi_items = report.items_by_meta["Atividades Técnicas e Sustentação (AtendeMais)"]
    ticket_12345 = next(item for item in glpi_items if "12345" in item.identifier)
    assert "MR !12" in ticket_12345.linked_identifiers
