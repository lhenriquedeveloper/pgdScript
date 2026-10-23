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
            role="Atribuído",
            solved_date=datetime(2026, 10, 21, 15, 30),
            description_summary="Acesso regularizado ao perfil do servidor.",
        ),
        GLPITicket(
            id="12389",
            title="Análise de inconsistência de dados na tabela Y",
            status="Pendente (Aguardando Retorno do Cliente)",
            role="Observador",
            modified_date=datetime(2026, 10, 22, 10, 0),
            description_summary="Aguardando envio do arquivo de log pelo demandante.",
        ),
    ]

    issues = [
        GitLabIssue(
            id=101,
            iid=45,
            title="Implementação de filtro de busca por demandante",
            project_name="frotas",
            state="closed",
            closed_this_week=True,
            closed_at=datetime(2026, 10, 19, 14, 0),
            web_url="https://git.uft.edu.br/cds/frotas/issues/45",
        ),
        GitLabIssue(
            id=102,
            iid=52,
            title="Modelagem de novos relatórios de ocupação",
            project_name="frotas",
            state="opened",
            is_ongoing=True,
            milestone={"title": "Sprint 4"},
            stage="Desenvolvimento",
            web_url="https://git.uft.edu.br/cds/frotas/issues/52",
        ),
    ]

    mrs = [
        GitLabMergeRequest(
            id=201,
            iid=12,
            title="Refatoração de endpoints da API de frotas",
            project_name="frotas",
            state="merged",
            web_url="https://git.uft.edu.br/cds/frotas/merge_requests/12",
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
    # Verifica tarefa fixa
    assert "**Extração semanal dos arquivos no SIAPE e upload dos dados no SUAP** (Concluída)" in md
    # Verifica chamados com papel e descrição
    assert "[Chamado #12345] Correção de permissão de acesso ao módulo X [Atribuído] (Solucionado em 21/10)" in md
    assert "*Atendimento: Acesso regularizado ao perfil do servidor.*" in md
    # Verifica issues com link e status
    assert "[Issue #45](https://git.uft.edu.br/cds/frotas/issues/45) Implementação de filtro de busca por demandante (Encerrada nesta semana em 19/10)" in md
    assert "[Issue #52](https://git.uft.edu.br/cds/frotas/issues/52) Modelagem de novos relatórios de ocupação (Em execução - Desenvolvimento / Sprint 4)" in md

    plain = format_plain(report)
    assert "Extração semanal dos arquivos no SIAPE e upload dos dados no SUAP (Concluída)" in plain
    assert "Chamado #12345 [Atribuído]: Correção de permissão de acesso ao módulo X (Solucionado em 21/10)" in plain
    assert "Atendimento: Acesso regularizado ao perfil do servidor." in plain
