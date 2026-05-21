import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request

from app.bot import create_bot_and_dispatcher, feed_update
from app.config import get_settings


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not settings.telegram_bot_token:
        logger.warning("TELEGRAM_BOT_TOKEN is not configured; webhook processing will fail until it is set.")
        app.state.bot = None
        app.state.dispatcher = None
    else:
        bot, dispatcher = create_bot_and_dispatcher(settings)
        app.state.bot = bot
        app.state.dispatcher = dispatcher
    yield
    bot = getattr(app.state, "bot", None)
    if bot is not None:
        await bot.session.close()


app = FastAPI(title="Telegram AI Bot", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/webhook/{secret}")
async def telegram_webhook(secret: str, request: Request) -> dict[str, bool]:
    if not settings.webhook_secret or secret != settings.webhook_secret:
        raise HTTPException(status_code=403, detail="Invalid webhook secret")

    bot = getattr(request.app.state, "bot", None)
    dispatcher = getattr(request.app.state, "dispatcher", None)
    if bot is None or dispatcher is None:
        raise HTTPException(status_code=503, detail="Bot is not configured")

    update_data = await request.json()
    await feed_update(bot, dispatcher, update_data)
    return {"ok": True}
