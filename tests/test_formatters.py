from datetime import datetime
from pgd_report.models import GLPITicket, GitLabIssue, GitLabMergeRequest
from pgd_report.processor import ReportProcessor
from pgd_report.formatters import format_markdown, format_plain


def test_markdown_and_plain_formatters():
    tickets = [
        GLPITicket(
            id="12345",
            title="Correção de permissão de acesso ao módulo X",
            status="Solucionado",
            solved_date=datetime(2026, 10, 21, 15, 30),
        ),
        GLPITicket(
            id="12389",
            title="Análise de inconsistência de dados na tabela Y",
            status="Solucionado",
            solved_date=datetime(2026, 10, 22, 10, 0),
        ),
    ]

    issues = [
        GitLabIssue(
            id=101,
            iid=45,
            title="Implementação de filtro de busca por demandante",
            project_name="frotas",
            state="closed",
        ),
        GitLabIssue(
            id=102,
            iid=52,
            title="Modelagem de novos relatórios de ocupação",
            project_name="frotas",
            state="opened",
        ),
    ]

    mrs = [
        GitLabMergeRequest(
            id=201,
            iid=12,
            title="Refatoração de endpoints da API de frotas",
            project_name="frotas",
            state="merged",
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

    md = format_markdown(report)
    assert "### Atividades Técnicas e Sustentação (AtendeMais)" in md
    assert "- [Chamado #12345] Correção de permissão de acesso ao módulo X (Resolvido em 21/10)" in md
    assert "- [Chamado #12389] Análise de inconsistência de dados na tabela Y (Resolvido em 22/10)" in md
    assert "### Desenvolvimento e Projetos (GitLab)" in md
    assert "- [Issue #45] Implementação de filtro de busca por demandante (Concluída)" in md
    assert "- [MR !12] Refatoração de endpoints da API de frotas (Mesclado)" in md
    assert "- [Issue #52] Modelagem de novos relatórios de ocupação (Em andamento)" in md

    plain = format_plain(report)
    assert "[ATIVIDADES TÉCNICAS E SUSTENTAÇÃO (ATENDEMAIS)]" in plain
    assert "• Chamado #12345: Correção de permissão de acesso ao módulo X (Resolvido em 21/10)" in plain
