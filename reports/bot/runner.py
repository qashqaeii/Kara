"""Bale bot entrypoint."""

from __future__ import annotations

import logging
import os

from django.conf import settings
from django.db import close_old_connections

logger = logging.getLogger(__name__)


def _bypass_system_proxy_for_bale() -> None:
    """Windows VPN/proxy (e.g. 127.0.0.1:10808) breaks tapi.bale.ai TLS."""
    extra = "tapi.bale.ai,bale.ai"
    current = os.environ.get("NO_PROXY") or os.environ.get("no_proxy") or ""
    parts = [p.strip() for p in f"{current},{extra}".split(",") if p.strip()]
    merged = ",".join(dict.fromkeys(parts))
    os.environ["NO_PROXY"] = merged
    os.environ["no_proxy"] = merged


def create_bot():
    import telebot
    from telebot import apihelper

    from reports.bot.handlers.router import BotRouter

    _bypass_system_proxy_for_bale()
    token = getattr(settings, "BALE_BOT_TOKEN", "")
    if not token:
        raise RuntimeError("BALE_BOT_TOKEN is not configured")
    apihelper.API_URL = getattr(settings, "BALE_API_URL", "https://tapi.bale.ai/bot{0}/{1}")
    apihelper.ENABLE_MIDDLEWARE = True
    apihelper.proxy = {"http": None, "https": None}
    bot = telebot.TeleBot(token, threaded=False, parse_mode=None)

    @bot.middleware_handler(update_types=["message", "callback_query"])
    def _django_middleware(bot_instance, event) -> None:
        close_old_connections()

    BotRouter(bot)
    return bot


def run_polling() -> None:
    if not getattr(settings, "BALE_BOT_ENABLED", False):
        logger.warning("BALE_BOT_ENABLED is False — bot not starting")
        return
    bot = create_bot()
    try:
        bot.delete_webhook(drop_pending_updates=False)
    except Exception:
        logger.exception("delete_webhook failed")
    logging.basicConfig(level=logging.INFO)
    logger.info("Bale bot polling started")
    bot.infinity_polling(
        timeout=30,
        long_polling_timeout=30,
        skip_pending=True,
        allowed_updates=["message", "callback_query"],
    )
