"""Cliente HTTP para envio de mensagens ao WhatsApp.

Suporta dois provedores:

- ``evolution``: Evolution API v2 (endpoints /message/sendText e
  /message/sendMedia, autenticacao via header ``apikey``).
- ``zapi``: Z-API (endpoints /send-text e /send-image, autenticacao via
  header ``Client-Token`` e token na rota).
"""

import base64
import mimetypes

import httpx
from loguru import logger
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)


class WhatsAppSender:
    def __init__(
        self,
        provider: str,
        api_url: str,
        api_key: str,
        instance: str,
        group_jid: str,
        token: str = "",
        timeout: float = 20.0,
    ):
        self._provider = provider
        self._api_url = api_url
        self._api_key = api_key
        self._instance = instance
        self._group_jid = group_jid
        self._token = token
        self._client = httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    def _headers(self) -> dict[str, str]:
        if self._provider == "zapi":
            return {"Client-Token": self._api_key, "Content-Type": "application/json"}
        return {"apikey": self._api_key, "Content-Type": "application/json"}

    def _text_request(self, text: str) -> tuple[str, dict]:
        if self._provider == "zapi":
            url = (
                f"{self._api_url}/instances/{self._instance}"
                f"/token/{self._token}/send-text"
            )
            return url, {"phone": self._group_jid, "message": text}
        url = f"{self._api_url}/message/sendText/{self._instance}"
        return url, {"number": self._group_jid, "text": text}

    def _media_request(
        self, media_b64: str, caption: str, mimetype: str
    ) -> tuple[str, dict]:
        if self._provider == "zapi":
            route = "send-image" if mimetype.startswith("image/") else "send-document"
            url = (
                f"{self._api_url}/instances/{self._instance}"
                f"/token/{self._token}/{route}"
            )
            media_field = "image" if route == "send-image" else "document"
            return url, {
                "phone": self._group_jid,
                media_field: f"data:{mimetype};base64,{media_b64}",
                "caption": caption,
            }
        kind = (
            "image" if mimetype.startswith("image/")
            else "video" if mimetype.startswith("video/")
            else "document"
        )
        url = f"{self._api_url}/message/sendMedia/{self._instance}"
        return url, {
            "number": self._group_jid,
            "mediatype": kind,
            "mimetype": mimetype,
            "media": media_b64,
            "caption": caption,
            "fileName": f"promocao.{mimetypes.guess_extension(mimetype) or 'bin'}",
        }

    @retry(
        retry=retry_if_exception_type(httpx.HTTPError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    async def _post(self, url: str, payload: dict) -> None:
        response = await self._client.post(url, json=payload, headers=self._headers())
        response.raise_for_status()
        logger.debug("WhatsApp respondeu {}: {}", response.status_code, response.text[:200])

    async def send_text(self, text: str) -> None:
        url, payload = self._text_request(text)
        await self._post(url, payload)
        logger.info("Mensagem de texto enviada ao grupo {}", self._group_jid)

    async def send_media(self, media: bytes, caption: str, mimetype: str) -> None:
        media_b64 = base64.b64encode(media).decode("ascii")
        url, payload = self._media_request(media_b64, caption, mimetype)
        await self._post(url, payload)
        logger.info("Midia ({}) enviada ao grupo {}", mimetype, self._group_jid)
