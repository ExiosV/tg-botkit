"""Shared Telegram Bot API client for the ExiosV tg-* projects (vendored into each project, see README)."""
from .bot import Bot, TelegramError
from .env import missing_secrets
from .telegraph import Telegraph, TelegraphError, html_to_nodes
from .text import split_message, strip_tags

__version__ = "0.2.0"
__all__ = ["Bot", "Telegraph", "TelegramError", "TelegraphError", "html_to_nodes", "missing_secrets", "split_message", "strip_tags", "__version__"]
