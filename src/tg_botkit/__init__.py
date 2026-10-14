"""Shared Telegram Bot API client for the ExiosV tg-* projects (vendored into each project, see README)."""
from .bot import Bot, TelegramError
from .env import missing_secrets
from .text import split_message, strip_tags

__version__ = "0.1.0"
__all__ = ["Bot", "TelegramError", "missing_secrets", "split_message", "strip_tags", "__version__"]
