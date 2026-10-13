"""Pipeline de processamento de mensagens.

Responsavel por localizar links da Shopee em um texto, expandir links
encurtados e substituir tudo pelos links de afiliado gerados pela API.
"""

import asyncio
import re
from urllib.parse import urlparse

import httpx
from loguru import logger
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from shopee_api import ShopeeAffiliateAPI

# Casa shopee.com.br (com ou sem subdominios, ex.: s.shopee.com.br)
# e o encurtador oficial shope.ee
SHOPEE_LINK_RE = re.compile(
    r"https?://(?:[\w-]+\.)*shopee\.com\.br/[^\s<>()\[\]\"']*"
    r"|https?://shope\.ee/[^\s<>()\[\]\"']*",
    re.IGNORECASE,
)

SHORT_LINK_HOSTS = {"s.shopee.com.br", "shope.ee"}


def extract_shopee_links(text: str) -> list[str]:
    """Retorna todos os links da Shopee encontrados no texto."""
    if not text:
        return []
    return SHOPEE_LINK_RE.findall(text)


def is_short_link(url: str) -> bool:
    return urlparse(url).netloc.lower() in SHORT_LINK_HOSTS


class LinkProcessor:
    def __init__(self, shopee_api: ShopeeAffiliateAPI, timeout: float = 20.0):
        self._shopee = shopee_api
        # Cliente que segue redirects para expandir links encurtados
        self._http = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0 Safari/537.36"
                )
            },
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    @retry(
        retry=retry_if_exception_type(httpx.HTTPError),
        stop=stop_after_attempt(3),
        wait=wait_fixed(1),
        reraise=True,
    )
    async def resolve_url(self, url: str) -> str:
        """Segue redirecionamentos HTTP e retorna a URL final."""
        response = await self._http.get(url)
        final_url = str(response.url)
        if final_url != url:
            logger.debug("Encurtado resolvido: {} -> {}", url, final_url)
        return final_url

    async def _convert_one(self, url: str) -> tuple[str, str]:
        """Retorna (url_original, url_afiliado)."""
        target = url
        if is_short_link(url):
            try:
                target = await self.resolve_url(url)
            except Exception as exc:
                logger.warning("Falha ao expandir {}: {}", url, exc)
        affiliate = await self._shopee.convert_url(target)
        return url, affiliate

    async def process_text(self, text: str) -> tuple[str, int]:
        """Substitui os links da Shopee por links de afiliado.

        Returns:
            (texto_processado, quantidade_de_links_convertidos)
        """
        links = extract_shopee_links(text)
        if not links:
            return text, 0

        unique_links = list(dict.fromkeys(links))
        results = await asyncio.gather(
            *(self._convert_one(link) for link in unique_links),
            return_exceptions=True,
        )

        processed = text
        converted = 0
        for original, result in zip(unique_links, results):
            if isinstance(result, Exception):
                logger.warning("Erro ao processar {}: {}", original, result)
                continue
            original_url, affiliate_url = result
            if affiliate_url != original_url:
                converted += 1
            processed = processed.replace(original_url, affiliate_url)

        return processed, converted
