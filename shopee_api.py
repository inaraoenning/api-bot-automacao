"""Cliente assinado para a Shopee Affiliate Open API (GraphQL).

Autenticacao: header ``Authorization`` no formato

    SHA256 Credential=<APP_KEY>, Timestamp=<unix_ts>, Signature=<hex>

onde ``Signature`` = HMAC-SHA256(secret, APP_KEY + timestamp + payload).

A mutation ``generateShortLink`` e a que retorna a URL de promocao de
afiliado (short link comissionado) a partir de uma URL de produto/oferta.
"""

import hashlib
import hmac
import json
import time

import httpx
from loguru import logger
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

GENERATE_SHORT_LINK_MUTATION = """
mutation GenerateShortLink($originUrl: String!) {
  generateShortLink(input: {originUrl: $originUrl}) {
    shortLink
  }
}
"""


class ShopeeAPIError(Exception):
    """Erro retornado pela API da Shopee ou falha de comunicacao."""


class ShopeeAffiliateAPI:
    def __init__(self, app_key: str, app_secret: str, endpoint: str, timeout: float = 20.0):
        self._app_key = app_key
        self._app_secret = app_secret
        self._endpoint = endpoint
        self._client = httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    def _build_headers(self, payload: str) -> dict[str, str]:
        timestamp = int(time.time())
        base_string = f"{self._app_key}{timestamp}{payload}"
        signature = hmac.new(
            self._app_secret.encode("utf-8"),
            base_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return {
            "Authorization": (
                f"SHA256 Credential={self._app_key}, "
                f"Timestamp={timestamp}, "
                f"Signature={signature}"
            ),
            "Content-Type": "application/json",
        }

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, ShopeeAPIError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    async def generate_affiliate_link(self, origin_url: str) -> str:
        """Gera o short link de afiliado para uma URL da Shopee.

        Raises:
            ShopeeAPIError: quando a API nao retorna um link valido.
        """
        body = {"query": GENERATE_SHORT_LINK_MUTATION, "variables": {"originUrl": origin_url}}
        payload = json.dumps(body, separators=(",", ":"))

        response = await self._client.post(
            self._endpoint,
            content=payload.encode("utf-8"),
            headers=self._build_headers(payload),
        )
        response.raise_for_status()
        data = response.json()

        if data.get("errors"):
            raise ShopeeAPIError(f"GraphQL errors: {data['errors']}")

        short_link = (
            data.get("data", {})
            .get("generateShortLink", {})
            .get("shortLink")
        )
        if not short_link:
            raise ShopeeAPIError(f"Resposta sem shortLink: {data}")

        logger.debug("Afiliado gerado: {} -> {}", origin_url, short_link)
        return short_link

    async def convert_url(self, url: str) -> str:
        """Tenta converter a URL; em caso de falha retorna a URL original."""
        try:
            return await self.generate_affiliate_link(url)
        except Exception as exc:
            logger.warning("Falha ao gerar link de afiliado para {}: {}", url, exc)
            return url
