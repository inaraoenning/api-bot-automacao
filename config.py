"""Carregamento e validacao das variaveis de ambiente do projeto."""

import json
from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Configuracoes da aplicacao, lidas do ambiente ou de um arquivo .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram (UserBot)
    telegram_api_id: int
    telegram_api_hash: str
    telegram_session_name: str = "shopee_bot_session"
    source_channels: Annotated[list[int], NoDecode]

    # Shopee Affiliate Open API
    shopee_app_key: str
    shopee_app_secret: str
    shopee_api_url: str = "https://open-api.affiliate.shopee.com.br/graphql"

    # WhatsApp (Evolution API / Z-API)
    wa_provider: str = "evolution"
    wa_api_url: str
    wa_api_key: str
    wa_instance_name: str
    wa_group_jid: str
    wa_token: str = ""

    # Geral
    request_timeout: float = 20.0
    log_level: str = "INFO"

    @field_validator("source_channels", mode="before")
    @classmethod
    def parse_source_channels(cls, value):
        """Aceita JSON list ou lista separada por virgulas."""
        if isinstance(value, str):
            text = value.strip()
            if text.startswith("["):
                return json.loads(text)
            return [int(item) for item in text.split(",") if item.strip()]
        return value

    @field_validator("wa_provider")
    @classmethod
    def validate_provider(cls, value: str) -> str:
        provider = value.strip().lower()
        if provider not in {"evolution", "zapi"}:
            raise ValueError("WA_PROVIDER deve ser 'evolution' ou 'zapi'")
        return provider

    @field_validator("wa_api_url", "shopee_api_url")
    @classmethod
    def strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")


@lru_cache
def get_settings() -> Settings:
    """Retorna as configuracoes (cache — o .env e lido uma unica vez)."""
    return Settings()
