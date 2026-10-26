# 📊 PGD Report (GLPI AtendeMais & GitLab UFT)

Automação em linha de comando (CLI) em Python para consolidar entregas semanais de atividades para o **PGD (Programa de Gestão e Desempenho)** a partir do **GLPI (AtendeMais)** e do **GitLab Institucional da UFT**.

O script consome as APIs REST de ambas as ferramentas, correlaciona chamados com issues/merge requests, categoriza as entregas conforme as metas do seu plano de trabalho e gera o texto pronto em formato Markdown ou texto puro para copiar e colar no PGD.

---

## 🏛 Arquitetura da Solução

```
[ GLPI REST API ]    ---> Chamados solucionados/fechados na semana
(AtendeMais UFT)     \
                      ---> [ CLI: pgd-report ] ---> [ Relatório Formatado ]
                     /                              (Markdown / Texto PGD)
[ GitLab REST API ]  ---> Issues fechadas/atualizadas + MRs
(git.uft.edu.br)
```

- **GLPI (AtendeMais)**: Filtra estritamente chamados onde **LUIS HENRIQUE SOUSA RODRIGUES** é **Atribuído** ou **Observador**, com status **Solucionado**, **Fechado** ou **Pendente (Aguardando Retorno do Cliente)**, extraindo automaticamente a descrição da ação/solução realizada.
- **GitLab (git.uft.edu.br)**: Filtra issues com **Author Luis Henrique Sousa Rodrigues** (`luishenrique.sr`), incluindo em execução **somente** se vinculadas a uma **milestone** ativa/ongoing (mapeando o fluxo: *Análise*, *Desenvolvimento*, *Disponibilidade no Betas*, *Disponibilidade em Produção* com link clicável), e issues encerradas **somente** se fechadas naquela semana específica.
- **Tarefa Fixa Semanal**: Inclui automaticamente em todo relatório a rotina fixa de **Extração semanal dos arquivos no SIAPE e upload dos dados no SUAP**.


---

## 🚀 Instalação Rápida

No diretório do projeto:

```bash
# Instalação do pacote em modo editável
pip install -e .
```

Isso disponibiliza os comandos `pgd-report` e `pgd` no seu terminal.

---

## ⚙️ Configuração das Credenciais

Crie um arquivo `.env` na raiz do projeto ou em `~/.config/pgd/.env`:

```bash
cp .env.example .env
```

Edite o arquivo `.env` com seus dados:

```ini
# GLPI (AtendeMais UFT)
GLPI_BASE_URL="https://sistemas.uft.edu.br/atendemais/apirest.php"
GLPI_USER_TOKEN="seu_token_glpi_aqui"
GLPI_APP_TOKEN="" # se exigido pela instância

# GitLab (git.uft.edu.br)
GITLAB_BASE_URL="https://git.uft.edu.br/api/v4"
GITLAB_TOKEN="seu_personal_access_token_aqui"
GITLAB_USER="seu_username_uft"
```

### Como obter os tokens:

1. **GitLab**:
   - Acesse `https://git.uft.edu.br/-/profile/personal_access_tokens` (ou *User Settings* > *Access Tokens*).
   - Crie um token com nome `pgd-token` e marque apenas o escopo **`read_api`**.
   - Copie o token e cole no campo `GITLAB_TOKEN`.
2. **GLPI (AtendeMais)**:
   - Acesse o AtendeMais > Clique no seu avatar/nome no canto superior direito > **Preferências** > aba **Tokens**.
   - Gere o **Token de API** pessoal e salve no campo `GLPI_USER_TOKEN`.
   - *Nota de contingência:* Se a API REST do GLPI institucional estiver com acesso restrito, utilize o recurso de importação CSV (`--glpi-csv`).

---

## 📋 Como Usar

### 1. Testar credenciais e conexões
```bash
pgd-report status
```

### 2. Gerar o relatório semanal padrão (últimos 7 dias)
```bash
pgd generate
# ou simplesmente:
pgd
```

### 3. Copiar com Links para Colar no PGD

Dependendo de como é o campo de texto do seu sistema PGD/SUAP:

- **Para colar em editor visual (Rich Text / WYSIWYG) com links azuis clicáveis:**
  ```bash
  pgd generate --copy-html
  ```
  > *Dica: Ao pressionar Ctrl+V no editor do sistema, os títulos e links (`Issue #44`, `Chamado #19888`) já serão colados formatados com hiperlinks reais e clicáveis!*

- **Para copiar em Markdown:**
  ```bash
  pgd generate --copy
  # ou abreviado:
  pgd generate -c
  ```

- **Para colar em campo de texto puro (sem suporte a Markdown, com URL por extenso):**
  ```bash
  pgd generate -c -f plain
  ```

### 4. Salvar o relatório em arquivo
```bash
# Salvar em Markdown
pgd generate --days 7 --output relatorio_semanal.md

# Salvar em HTML
pgd generate --format html --output relatorio_semanal.html
```

### 5. Consultar período específico (ex: quinzenal ou datas customizadas)
```bash
pgd generate --since 2026-10-15 --until 2026-10-22
```

### 6. Contingência: Utilizar arquivo CSV exportado do AtendeMais
Caso a API do GLPI não esteja acessível, basta exportar a busca de chamados em CSV no AtendeMais e rodar:
```bash
pgd generate --glpi-csv chamados_semana.csv
```


---

## 🎯 Mapeamento de Metas do PGD

Para organizar automaticamente as entregas por Meta do seu Plano de Trabalho, edite ou crie o arquivo `config/goals_mapping.json`:

```json
{
  "metas": {
    "Meta 1: Sustentação de Sistemas Institucionais": {
      "gitlab_projects": ["atendemais-plugins", "portal-uft", "sie-integrador"],
      "gitlab_labels": ["sustentacao", "bug", "hotfix"],
      "glpi_categories": ["Sistemas", "Correção de Erro"]
    },
    "Meta 2: Desenvolvimento de Novos Módulos": {
      "gitlab_projects": ["frotas-api", "novo-portal"],
      "gitlab_labels": ["feature", "melhoria"],
      "glpi_categories": ["Novo Módulo"]
    }
  },
  "default_glpi_meta": "Atividades Técnicas e Sustentação (AtendeMais)",
  "default_gitlab_meta": "Desenvolvimento e Projetos (GitLab)"
}
```

---

## 💡 Boas Práticas Operacionais

- **Nome de Branches e Commits**: Ao trabalhar no GitLab, inclua o número do chamado (ex: `fix/12345-ajuste-login` ou no título do MR `Fix #12345`). O script correlaciona automaticamente e adiciona a referência no relatório!
- **Alias no `.bashrc`**:
  ```bash
  alias pgd-semana='pgd --days 7 --copy'
  ```
  Assim, toda sexta-feira basta digitar `pgd-semana` no terminal para já ter o relatório pronto no clipboard para colar no sistema PGD.
