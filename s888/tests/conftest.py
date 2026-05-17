"""Test fixtures. Ensures CFG loads even without real .env values."""

from __future__ import annotations

import os

# Provide dummy secrets so config loads cleanly in CI / dev environments
# that don't have a real .env.
os.environ.setdefault("FMP_API_KEY", "test-fmp-key")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-telegram-token")
os.environ.setdefault("TELEGRAM_CHAT_ID", "0")
