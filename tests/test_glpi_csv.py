from datetime import datetime
from pathlib import Path
from pgd_report.clients.glpi_client import GLPIClient


def test_glpi_csv_parsing(tmp_path: Path):
    # Simula exportação padrão do GLPI com ponto-e-vírgula e acentos
    csv_content = (
        "ID;Título;Status;Data de solução;Técnico atribuído;Categoria\n"
        "12345;Correção de permissão de acesso ao módulo X;Solucionado;21/10/2026 14:30;João Silva;Sistemas\n"
        "12389;Análise de inconsistência de dados na tabela Y;Fechado;22/10/2026 16:15;João Silva;Banco de Dados\n"
    )
    csv_file = tmp_path / "chamados.csv"
    csv_file.write_text(csv_content, encoding="utf-8")

    tickets = GLPIClient.parse_csv(csv_file)
    assert len(tickets) == 2
    assert tickets[0].id == "12345"
    assert tickets[0].title == "Correção de permissão de acesso ao módulo X"
    assert tickets[0].solved_date == datetime(2026, 10, 21, 14, 30)
    assert tickets[0].display_date_str == "21/10"
    assert tickets[1].id == "12389"
    assert tickets[1].status == "Fechado"
