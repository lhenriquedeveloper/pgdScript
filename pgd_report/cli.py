from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown

from pgd_report import __version__
from pgd_report.config import get_settings, Settings
from pgd_report.models import GLPITicket, GitLabIssue, GitLabMergeRequest
from pgd_report.clients.glpi_client import GLPIClient, GLPIError
from pgd_report.clients.gitlab_client import GitLabClient, GitLabError
from pgd_report.processor import ReportProcessor
from pgd_report.formatters import format_markdown, format_plain, format_html

app = typer.Typer(
    name="pgd-report",
    help="Automação CLI para coleta e consolidação de entregas semanais do PGD (GLPI & GitLab UFT).",
    add_completion=False,
)
console = Console()
err_console = Console(stderr=True)


def copy_to_clipboard(text: str, is_html: bool = False) -> bool:
    """Tenta copiar o texto para o clipboard usando utilitários do sistema."""
    import os
    env = os.environ.copy()
    user_local_bin = str(Path.home() / ".local" / "bin")
    miniconda_bin = str(Path.home() / "miniconda3" / "bin")
    env["PATH"] = f"{user_local_bin}:{miniconda_bin}:{env.get('PATH', '')}"

    if is_html:
        commands = [
            ["wl-copy", "-t", "text/html"],
            ["xclip", "-selection", "clipboard", "-target", "text/html"],
        ]
    else:
        commands = [
            ["wl-copy"],
            ["xclip", "-selection", "clipboard"],
            ["xsel", "--clipboard", "--input"],
            ["pbcopy"],
        ]
    for cmd in commands:
        try:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, env=env, close_fds=True)
            proc.communicate(input=text.encode("utf-8"))
            if proc.returncode == 0:
                return True
        except (FileNotFoundError, OSError):
            continue
    return False


@app.command("generate")
def generate(
    days: Annotated[int, typer.Option("--days", "-d", help="Quantidade de dias retroativos a consultar.")] = 7,
    since: Annotated[Optional[str], typer.Option("--since", "-s", help="Data inicial personalizada (formato AAAA-MM-DD).")] = None,
    until: Annotated[Optional[str], typer.Option("--until", "-u", help="Data final personalizada (formato AAAA-MM-DD).")] = None,
    glpi_csv: Annotated[Optional[Path], typer.Option("--glpi-csv", help="Caminho para arquivo CSV exportado do AtendeMais (contingência se a API estiver desativada).")] = None,
    output: Annotated[Optional[Path], typer.Option("--output", "-o", help="Salva o relatório no arquivo indicado.")] = None,
    copy: Annotated[bool, typer.Option("--copy", "-c", help="Copia o relatório gerado diretamente para a área de transferência.")] = False,
    copy_html: Annotated[bool, typer.Option("--copy-html", help="Copia o relatório em formato HTML (Rich Text) para colar com links clicáveis em editores web do PGD.")] = False,
    fmt: Annotated[str, typer.Option("--format", "-f", help="Formato de saída: 'markdown', 'plain', 'html' ou 'json'.")] = "markdown",
    with_links: Annotated[bool, typer.Option("--with-links/--no-links", help="Inclui links web nos identificadores do Markdown.")] = True,
    with_header: Annotated[bool, typer.Option("--with-header", help="Inclui cabeçalho com período e resumo no relatório.")] = False,
    preview: Annotated[bool, typer.Option("--preview/--no-preview", help="Exibe preview estilizado no terminal.")] = True,
):

    """
    Gera o relatório semanal consolidado do PGD a partir do GLPI e GitLab.
    """
    settings = get_settings()

    # 1. Definição do intervalo de datas
    now = datetime.now()
    if since:
        try:
            start_dt = datetime.strptime(since, "%Y-%m-%d")
        except ValueError:
            err_console.print("[red]Erro: Data inicial inválida. Use o formato AAAA-MM-DD.[/red]")
            raise typer.Exit(code=1)
    else:
        start_dt = now - timedelta(days=days)

    if until:
        try:
            end_dt = datetime.strptime(until, "%Y-%m-%d")
        except ValueError:
            err_console.print("[red]Erro: Data final inválida. Use o formato AAAA-MM-DD.[/red]")
            raise typer.Exit(code=1)
    else:
        end_dt = now

    console.print(
        f"[bold cyan]🔍 PGD Report v{__version__}[/bold cyan] | "
        f"Período: [bold]{start_dt.strftime('%d/%m/%Y')}[/bold] até [bold]{end_dt.strftime('%d/%m/%Y')}[/bold]"
    )

    tickets: list[GLPITicket] = []
    issues: list[GitLabIssue] = []
    mrs: list[GitLabMergeRequest] = []

    # 2. Coleta de Chamados do GLPI (AtendeMais)
    if glpi_csv:
        try:
            with console.status(f"[yellow]Importando chamados do CSV '{glpi_csv}'...[/yellow]"):
                tickets = GLPIClient.parse_csv(glpi_csv, since=start_dt, until=end_dt)
            console.print(f"[green]✓[/green] Importados [bold]{len(tickets)}[/bold] chamados do arquivo CSV.")
        except Exception as exc:
            err_console.print(f"[red]Erro ao importar CSV do GLPI:[/red] {exc}")
            raise typer.Exit(code=1)
    elif settings.check_glpi_configured():
        try:
            with console.status("[yellow]Consultando chamados no AtendeMais (GLPI REST API)...[/yellow]"):
                glpi_client = GLPIClient(
                    base_url=settings.glpi_base_url,
                    user_token=settings.glpi_user_token,
                    app_token=settings.glpi_app_token,
                    user_id=settings.glpi_user_id,
                )
                with glpi_client:
                    tickets = glpi_client.get_solved_tickets(since=start_dt, until=end_dt)
            console.print(f"[green]✓[/green] Obtidos [bold]{len(tickets)}[/bold] chamados resolvidos do AtendeMais.")
        except GLPIError as exc:
            err_console.print(f"[bold yellow]Aviso GLPI:[/bold yellow] {exc}")
            console.print(
                "[dim]💡 Dica: Se a API estiver bloqueada institucionalmente, "
                "você pode exportar os chamados em CSV no AtendeMais e usar: --glpi-csv chamados.csv[/dim]"
            )
    else:
        console.print(
            "[yellow]ℹ GLPI não configurado ou token ausente. Pulando consulta ao AtendeMais. "
            "(Configure o .env ou use --glpi-csv)[/yellow]"
        )

    # 3. Coleta de Atividades do GitLab Institucional
    if settings.check_gitlab_configured():
        try:
            with console.status("[yellow]Consultando Issues e MRs no GitLab UFT...[/yellow]"):
                gitlab_client = GitLabClient(
                    base_url=settings.gitlab_base_url,
                    token=settings.gitlab_token,
                    username=settings.gitlab_user,
                )
                issues = gitlab_client.get_issues(since=start_dt, until=end_dt)
                mrs = gitlab_client.get_merge_requests(since=start_dt, until=end_dt)
            console.print(
                f"[green]✓[/green] Obtidas [bold]{len(issues)}[/bold] issues e [bold]{len(mrs)}[/bold] MRs do GitLab."
            )
        except GitLabError as exc:
            err_console.print(f"[bold yellow]Aviso GitLab:[/bold yellow] {exc}")
    else:
        console.print("[yellow]ℹ GitLab não configurado ou token ausente. Pulando consulta ao GitLab.[/yellow]")

    # 4. Processamento, categorização e cruzamento
    mapping_config = settings.load_goals_mapping()
    processor = ReportProcessor(mapping_config=mapping_config)
    report_data = processor.process(
        tickets=tickets,
        issues=issues,
        merge_requests=mrs,
        start_date=start_dt,
        end_date=end_dt,
    )

    # 5. Formatação do Relatório
    if fmt.lower() == "plain":
        final_text = format_plain(report_data)
    elif fmt.lower() == "json":
        final_text = report_data.model_dump_json(indent=2)
    elif fmt.lower() == "html":
        final_text = format_html(
            report_data,
            include_header=with_header,
            include_links=with_links,
            include_stats=with_header,
        )
    else:
        final_text = format_markdown(
            report_data,
            include_header=with_header,
            include_links=with_links,
            include_stats=with_header,
        )

    # 6. Exibição / Preview
    if preview:
        console.print("\n")
        if fmt.lower() == "markdown" or fmt.lower() == "html":
            # Para o preview no terminal, exibe a visualização Markdown elegante
            preview_md = format_markdown(
                report_data,
                include_header=with_header,
                include_links=with_links,
                include_stats=with_header,
            )
            panel_content = Markdown(preview_md)
        else:
            panel_content = final_text
        console.print(
            Panel(
                panel_content,
                title="[bold green]📋 Relatório Gerado para o PGD[/bold green]",
                subtitle="Pronto para colar no sistema do PGD",
                border_style="green",
            )
        )

    # 7. Cópia para Clipboard
    if copy_html or (copy and fmt.lower() == "html"):
        html_content = format_html(
            report_data,
            include_header=with_header,
            include_links=with_links,
            include_stats=with_header,
        )
        if copy_to_clipboard(html_content, is_html=True):
            console.print("[bold green]✔ Relatório copiado em Rich Text (HTML) para a área de transferência! (Ao colar em editores do PGD/SUAP, os links serão clicáveis)[/bold green]")
        else:
            console.print(
                "[yellow]⚠ Não foi possível copiar automaticamente para o clipboard. "
                "Certifique-se de que o xclip ou wl-copy está disponível.[/yellow]"
            )
    elif copy:
        if copy_to_clipboard(final_text, is_html=False):
            console.print("[bold green]✔ Relatório copiado para a área de transferência![/bold green]")
        else:
            console.print(
                "[yellow]⚠ Não foi possível copiar automaticamente para o clipboard. "
                "Certifique-se de que o xclip ou wl-copy está disponível.[/yellow]"
            )

    # 8. Salvamento em arquivo se solicitado
    if output:
        try:
            output.write_text(final_text, encoding="utf-8")
            console.print(f"[bold green]✔ Relatório salvo com sucesso em:[/bold green] {output.resolve()}")
        except Exception as exc:
            err_console.print(f"[red]Erro ao salvar no arquivo '{output}':[/red] {exc}")


@app.command("status")
def status():
    """
    Verifica o status das configurações (.env) e testa conexão com GLPI e GitLab.
    """
    settings = get_settings()

    table = Table(title="🔧 Diagnóstico de Conexão e Credenciais PGD", show_lines=True)
    table.add_column("Serviço / Ferramenta", style="cyan", no_wrap=True)
    table.add_column("URL Base", style="blue")
    table.add_column("Credenciais", style="magenta")
    table.add_column("Status de Conexão", style="green")

    # Diagnóstico GLPI
    glpi_cred = "Token configurado" if settings.glpi_user_token else "Não configurado"
    glpi_status = "Não testado"
    if settings.check_glpi_configured():
        try:
            client = GLPIClient(
                base_url=settings.glpi_base_url,
                user_token=settings.glpi_user_token,
                app_token=settings.glpi_app_token,
                user_id=settings.glpi_user_id,
            )
            with client:
                glpi_status = "[green]✓ Conectado com sucesso (Sessão OK)[/green]"
        except Exception as exc:
            glpi_status = f"[red]✗ Erro ({exc})[/red]"
    else:
        glpi_status = "[yellow]Token pendente no .env[/yellow]"

    table.add_row("GLPI (AtendeMais)", settings.glpi_base_url, glpi_cred, glpi_status)

    # Diagnóstico GitLab
    gitlab_cred = "Token configurado" if settings.gitlab_token else "Não configurado"
    gitlab_status = "Não testado"
    if settings.check_gitlab_configured():
        try:
            client = GitLabClient(
                base_url=settings.gitlab_base_url,
                token=settings.gitlab_token,
                username=settings.gitlab_user,
            )
            user_data = client.verify_auth_and_get_user()
            uname = user_data.get("username", "ok")
            gitlab_status = f"[green]✓ Conectado ({uname})[/green]"
        except Exception as exc:
            gitlab_status = f"[red]✗ Erro ({exc})[/red]"
    else:
        gitlab_status = "[yellow]Token pendente no .env[/yellow]"

    table.add_row("GitLab UFT", settings.gitlab_base_url, gitlab_cred, gitlab_status)

    console.print(table)

    # Mapeamento de Metas
    mapping = settings.load_goals_mapping()
    metas_count = len(mapping.get("metas", {}))
    console.print(f"\n[bold]Metas configuradas:[/bold] {metas_count} metas no arquivo de mapeamento.")


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: Annotated[bool, typer.Option("--version", "-v", help="Exibe a versão do pgd-report.")] = False,
):

    """
    Ponto de entrada padrão. Se nenhum subcomando for passado, executa 'generate'.
    """
    if version:
        console.print(f"pgd-report v{__version__}")
        raise typer.Exit()

    if ctx.invoked_subcommand is None:
        ctx.invoke(generate)


if __name__ == "__main__":
    app()
