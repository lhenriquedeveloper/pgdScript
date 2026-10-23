from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Dict, Any, List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações da aplicação PGD Report."""
    model_config = SettingsConfigDict(
        env_file=(".env", Path.home() / ".config" / "pgd" / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # GLPI (AtendeMais UFT)
    glpi_base_url: str = Field(
        default="https://sistemas.uft.edu.br/atendemais/apirest.php",
        alias="GLPI_BASE_URL"
    )
    glpi_user_token: Optional[str] = Field(default=None, alias="GLPI_USER_TOKEN")
    glpi_app_token: Optional[str] = Field(default=None, alias="GLPI_APP_TOKEN")
    glpi_user_id: Optional[str] = Field(default=None, alias="GLPI_USER_ID")

    # GitLab Institucional (git.uft.edu.br)
    gitlab_base_url: str = Field(
        default="https://git.uft.edu.br/api/v4",
        alias="GITLAB_BASE_URL"
    )
    gitlab_token: Optional[str] = Field(default=None, alias="GITLAB_TOKEN")
    gitlab_user: Optional[str] = Field(default=None, alias="GITLAB_USER")

    # Configurações Gerais
    default_days: int = Field(default=7, alias="DEFAULT_DAYS")
    default_format: str = Field(default="markdown", alias="DEFAULT_FORMAT")
    goals_mapping_file: Optional[str] = Field(default="config/goals_mapping.json", alias="GOALS_MAPPING_FILE")

    def load_goals_mapping(self) -> Dict[str, Any]:
        """Carrega regras de mapeamento de metas do PGD a partir do JSON se existir."""
        candidate_paths = [
            Path(self.goals_mapping_file) if self.goals_mapping_file else None,
            Path("config/goals_mapping.json"),
            Path("config/goals_mapping.example.json"),
            Path.home() / ".config" / "pgd" / "goals_mapping.json",
        ]

        for p in candidate_paths:
            if p and p.exists() and p.is_file():
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception:
                    pass

        # Configuração padrão embutida
        return {
            "metas": {
                "Atividades Técnicas e Sustentação (AtendeMais)": {
                    "gitlab_projects": ["atendemais", "suporte", "sustentacao"],
                    "gitlab_labels": ["sustentacao", "bug", "suporte", "hotfix"],
                    "glpi_categories": []
                },
                "Desenvolvimento e Projetos (GitLab)": {
                    "gitlab_projects": [],
                    "gitlab_labels": ["feature", "melhoria", "desenvolvimento"],
                    "glpi_categories": []
                }
            },
            "default_glpi_meta": "Atividades Técnicas e Sustentação (AtendeMais)",
            "default_gitlab_meta": "Desenvolvimento e Projetos (GitLab)"
        }

    def check_glpi_configured(self) -> bool:
        return bool(self.glpi_user_token and self.glpi_base_url)

    def check_gitlab_configured(self) -> bool:
        return bool(self.gitlab_token and self.gitlab_base_url)


def get_settings() -> Settings:
    """Instancia as configurações lendo .env."""
    return Settings()
