"""Minimal async Telegram Bot API sender."""

from __future__ import annotations

import logging

import httpx

from ..config import CFG

log = logging.getLogger(__name__)


class TelegramError(RuntimeError):
    pass


async def send_message(text: str, parse_mode: str | None = None,
                       disable_web_preview: bool = True) -> bool:
    """Send a Telegram message. Returns True on success.

    Telegram caps messages at 4096 chars. If text is longer, it's split on
    line boundaries into multiple sends.
    """
    token = CFG.telegram_bot_token
    chat_id = CFG.telegram_chat_id
    if not token or not chat_id:
        raise TelegramError("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set")

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    parts = _split(text, 4096)
    async with httpx.AsyncClient(timeout=30.0) as client:
        for part in parts:
            data = {"chat_id": chat_id, "text": part,
                    "disable_web_page_preview": "true" if disable_web_preview else "false"}
            if parse_mode:
                data["parse_mode"] = parse_mode
            r = await client.post(url, data=data)
            if r.status_code != 200:
                log.error("Telegram HTTP %d: %s", r.status_code, r.text[:200])
                return False
            body = r.json()
            if not body.get("ok"):
                log.error("Telegram error: %s", body)
                return False
    return True


def _split(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts, buf = [], ""
    for line in text.split("\n"):
        if len(buf) + len(line) + 1 > limit:
            parts.append(buf)
            buf = line
        else:
            buf = f"{buf}\n{line}" if buf else line
    if buf:
        parts.append(buf)
    return parts
