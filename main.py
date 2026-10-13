"""Ponto de entrada do bot de automacao de promocoes.

Fluxo:
    Telegram (canais de origem)
        -> extracao/resolucao de links Shopee
        -> Shopee Affiliate Open API (links comissionados)
        -> WhatsApp (grupo de destino via Evolution API / Z-API)

Na primeira execucao, o Telethon solicitara o numero de telefone e o
codigo de verificacao no terminal (execute com TTY: `python main.py`
ou `docker compose run --rm bot`).
"""

import asyncio
import sys

from loguru import logger

from config import get_settings
from processor import LinkProcessor
from shopee_api import ShopeeAffiliateAPI
from telegram_listener import build_client
from whatsapp_sender import WhatsAppSender


def setup_logging(level: str) -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        level=level.upper(),
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>{name}:{line}</cyan> | {message}",
    )
    logger.add(
        "logs/bot_{time:YYYY-MM-DD}.log",
        level="DEBUG",
        rotation="1 day",
        retention="14 days",
        encoding="utf-8",
    )


async def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)

    logger.info("Canais de origem: {}", settings.source_channels)
    logger.info("Destino WhatsApp: {} via {}", settings.wa_group_jid, settings.wa_provider)

    shopee = ShopeeAffiliateAPI(
        app_key=settings.shopee_app_key,
        app_secret=settings.shopee_app_secret,
        endpoint=settings.shopee_api_url,
        timeout=settings.request_timeout,
    )
    processor = LinkProcessor(shopee_api=shopee, timeout=settings.request_timeout)
    whatsapp = WhatsAppSender(
        provider=settings.wa_provider,
        api_url=settings.wa_api_url,
        api_key=settings.wa_api_key,
        instance=settings.wa_instance_name,
        group_jid=settings.wa_group_jid,
        token=settings.wa_token,
        timeout=settings.request_timeout,
    )

    client = build_client(settings, processor, whatsapp)

    try:
        # start() abre a sessao; na 1a vez pede telefone + codigo no terminal
        await client.start()
        me = await client.get_me()
        logger.success("UserBot autenticado como {} (@{})", me.first_name, me.username)
        logger.info("Bot em execucao. Aguardando mensagens...")
        await client.run_until_disconnected()
    finally:
        await asyncio.gather(
            shopee.aclose(),
            processor.aclose(),
            whatsapp.aclose(),
            return_exceptions=True,
        )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Encerrado pelo usuario")
