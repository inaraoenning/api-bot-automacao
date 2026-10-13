"""Listener do Telegram baseado em Telethon (modo UserBot).

Escuta ``events.NewMessage`` nos canais/grupos configurados em
``SOURCE_CHANNELS`` e despacha cada mensagem para o pipeline de
processamento e, em seguida, para o WhatsApp.
"""

from loguru import logger
from telethon import TelegramClient, events

from config import Settings
from processor import LinkProcessor
from whatsapp_sender import WhatsAppSender


def build_client(
    settings: Settings,
    processor: LinkProcessor,
    whatsapp: WhatsAppSender,
) -> TelegramClient:
    client = TelegramClient(
        settings.telegram_session_name,
        settings.telegram_api_id,
        settings.telegram_api_hash,
    )

    @client.on(events.NewMessage(chats=settings.source_channels))
    async def on_new_message(event: events.NewMessage.Event) -> None:
        message = event.message
        text = message.message or ""
        chat_id = getattr(event.chat, "id", event.chat_id)
        logger.info("Nova mensagem de {} (id={})", chat_id, message.id)

        try:
            processed_text, converted = await processor.process_text(text)
        except Exception:
            logger.exception("Falha no pipeline de processamento; mensagem ignorada")
            return

        if not processed_text.strip() and not message.media:
            logger.debug("Mensagem {} sem texto/midia; ignorada", message.id)
            return
        if converted:
            logger.info("{} link(s) da Shopee convertidos para afiliado", converted)

        try:
            if message.photo or message.video or message.document:
                media_bytes = await message.download_media(file=bytes)
                mimetype = (message.file.mime_type if message.file else None) or "image/jpeg"
                if media_bytes:
                    await whatsapp.send_media(media_bytes, processed_text, mimetype)
                else:
                    await whatsapp.send_text(processed_text)
            else:
                await whatsapp.send_text(processed_text)
        except Exception:
            logger.exception("Falha ao enviar mensagem {} para o WhatsApp", message.id)

    return client
