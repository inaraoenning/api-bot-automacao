# Bot de Automação de Promoções — Telegram → Shopee Afiliados → WhatsApp

Pipeline totalmente assíncrono (`asyncio`) que escuta canais/grupos do
Telegram como **UserBot**, converte links da Shopee em links de afiliado
via Shopee Open API e republica a mensagem (texto + mídia) em um grupo
de WhatsApp via Evolution API ou Z-API.

## Fluxo

```
Telegram (SOURCE_CHANNELS)
   │  Telethon events.NewMessage
   ▼
processor.py ─ regex extrai links shopee.com.br / s.shopee.com.br / shope.ee
   │  httpx segue redirects nos links encurtados
   ▼
shopee_api.py ─ mutation GraphQL generateShortLink
   │  auth: HMAC-SHA256(secret, appKey + timestamp + payload)
   ▼
whatsapp_sender.py ─ POST sendText / sendMedia
   ▼
Grupo WhatsApp (WA_GROUP_JID)
```

## Estrutura

| Arquivo                | Responsabilidade                                      |
| ---------------------- | ----------------------------------------------------- |
| `config.py`            | Variáveis de ambiente via `pydantic-settings`         |
| `telegram_listener.py` | Telethon UserBot + handler `NewMessage`               |
| `processor.py`         | Regex de links, resolução de encurtados, substituição |
| `shopee_api.py`        | Requisição assinada à Open API GraphQL da Shopee      |
| `whatsapp_sender.py`   | Envio de texto/mídia (Evolution API / Z-API)          |
| `main.py`              | Orquestração e ciclo de vida                          |

## Configuração

1. Copie `.env.example` para `.env` e preencha:
   - `TELEGRAM_API_ID` / `TELEGRAM_API_HASH`: em https://my.telegram.org/apps
   - `SOURCE_CHANNELS`: IDs dos canais (JSON list ou separados por vírgula)
   - `SHOPEE_APP_KEY` / `SHOPEE_APP_SECRET`: painel de Afiliados Shopee (Open API)
   - `WA_*`: dados da sua instância Evolution API (ou Z-API com `WA_PROVIDER=zapi` e `WA_TOKEN`)

## Execução local

```bash
python -m venv .venv
.venv/Scripts/activate        # Windows (ou: source .venv/bin/activate)
pip install -r requirements.txt
python main.py
```

Na **primeira execução** o Telethon pede telefone + código de verificação
no terminal e salva a sessão em `*.session`.

## Deploy com Docker (VPS)

```bash
cp .env.example .env   # preencha as variáveis
docker compose run --rm bot   # 1ª vez: login interativo do Telegram
docker compose up -d          # depois: execução contínua
```

A sessão fica persistida em `./sessions`, então o login só é pedido uma vez.

## Resiliência

- Retentativas com backoff exponencial (`tenacity`) nas chamadas HTTP.
- Falha na API da Shopee → link original é mantido (a mensagem não é perdida).
- Falha no envio → erro logado em `logs/` e no console.
