from datetime import datetime
from pathlib import Path
from pgd_report.clients.glpi_client import GLPIClient


def test_glpi_csv_parsing(tmp_path: Path):
    # Simula exportação padrão do GLPI com Luis Henrique como Atribuído e Observador
    csv_content = (
        "ID;Título;Status;Data de solução;Técnico atribuído;Observador;Categoria;Descrição\n"
        "12345;Correção de permissão de acesso ao módulo X;Solucionado;21/10/2026 14:30;Luis Henrique Sousa Rodrigues;;Sistemas;Acesso liberado no módulo\n"
        "12389;Análise de inconsistência de dados na tabela Y;Pendente;22/10/2026 16:15;Outro Técnico;Luis Henrique Sousa Rodrigues;Banco de Dados;Aguardando validação do setor\n"
        "99999;Chamado de outro setor;Solucionado;20/10/2026 10:00;Carlos Souza;Ana Paula;Geral;Não deve entrar\n"
    )
    csv_file = tmp_path / "chamados.csv"
    csv_file.write_text(csv_content, encoding="utf-8")

    tickets = GLPIClient.parse_csv(csv_file)
    # Apenas os 2 chamados vinculados a Luis Henrique devem ser importados
    assert len(tickets) == 2
    assert tickets[0].id == "12345"
    assert tickets[0].role == "Atribuído"
    assert tickets[0].title == "Correção de permissão de acesso ao módulo X"
    assert tickets[0].solved_date == datetime(2026, 10, 21, 14, 30)
    assert tickets[0].display_date_str == "21/10"
    assert "Acesso liberado" in tickets[0].description_summary

    assert tickets[1].id == "12389"
    assert tickets[1].role == "Observador"
    assert tickets[1].status == "Pendente"
