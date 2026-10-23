from typer.testing import CliRunner
from pgd_report.cli import app

runner = CliRunner()


def test_cli_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Automação CLI para coleta e consolidação" in result.stdout


def test_cli_status():
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "Diagnóstico de Conexão e Credenciais PGD" in result.stdout


def test_cli_generate_with_csv(tmp_path):
    csv_file = tmp_path / "glpi_export.csv"
    csv_file.write_text(
        "ID;Título;Status;Data de solução\n"
        "9999;Ajuste emergencial em servidor;Solucionado;20/10/2026 10:00\n",
        encoding="utf-8"
    )

    output_file = tmp_path / "pgd_out.md"
    result = runner.invoke(
        app,
        ["generate", "--glpi-csv", str(csv_file), "--output", str(output_file), "--no-preview"]
    )
    assert result.exit_code == 0
    assert output_file.exists()
    content = output_file.read_text(encoding="utf-8")
    assert "[Chamado #9999] Ajuste emergencial em servidor (Resolvido em 20/10)" in content
