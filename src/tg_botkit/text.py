import html
import re

LIMIT = 4000  # a message holds 4096 characters; keep headroom


def strip_tags(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text))


def split_message(text: str, limit: int = LIMIT) -> list:
    """Split on blank lines, then lines, then hard cuts; every piece stays below `limit`."""
    pieces, cur = [], ""
    for para in text.split("\n\n"):
        for part in _hard_split(para, limit):
            if cur and len(cur) + 2 + len(part) > limit:
                pieces.append(cur)
                cur = part
            else:
                cur = f"{cur}\n\n{part}" if cur else part
    if cur:
        pieces.append(cur)
    return pieces or [""]


def _hard_split(para: str, limit: int) -> list:
    out = []
    while len(para) > limit:
        cut = para.rfind("\n", 0, limit)
        cut = cut if cut > limit // 2 else limit
        out.append(para[:cut])
        para = para[cut:].lstrip("\n")
    out.append(para)
    return out
