# tg-botkit

Shared Telegram Bot API client for the ExiosV `tg-*` projects. It replaces the ~60-line `Telegram` class that every
bot used to copy (429 retry, HTML with plain-text fallback, photo posts, edit/pin/delete, uploads, long-poll, download).
Depends only on `requests`.

```python
from tg_botkit import Bot, Telegraph, TelegramError, missing_secrets

bot = Bot(token, "http://telegram-bot-api-prod.infra.svc:8081", channel="-100123")
mid = bot.photos("<b>caption</b>", [url1, url2], silent=True)   # post with 1-10 photos, text fallback
bot.reply(mid, "price dropped"); bot.edit(mid, "new caption"); bot.pin(mid)
bot.send("hello", chat_id=42)            # HTML, falls back to plain text on bad markup
bot.group("document", [("a.pdf", fh)])   # uploads, 10 per media group
bot.updates(offset)                      # long poll;  bot.download(file_id, path)
missing_secrets(["TELEGRAM_BOT_TOKEN"])  # names unset or still CHANGEME

# Telegraph (telegra.ph) publishing
tg = Telegraph(access_token="...")
url = tg.create_page("Title", "<p>HTML or <b>nodes</b></p>")["url"]
tg.edit_page("path", title="New", content="<p>Updated</p>")
pages = tg.get_page_list(limit=100)
```

`TelegramError` subclasses `RuntimeError` (`.status`, `.description`), so old `except RuntimeError` code keeps working.

## Use in a project (vendoring)
App images are built on devicex2 without a registry and without credentials, so a private git dependency cannot be
installed in the Dockerfile. Each project commits a copy instead:

```bash
cd tg-botkit && scripts/vendor.sh ../tg-propertyfate   # writes src/tg_botkit/ (+ VENDORED.txt)
```

The project's setuptools `packages.find` (`where = ["src"]`) then ships it; add `requests` to its dependencies. To
change the client edit **this** repo, bump `__version__`, rerun `vendor.sh` in every project (PR per project).

## Dev
`pip install -e '.[dev]' && pytest`

## Changelog

### 0.2.0
- Added `Telegraph` client for telegra.ph API (create/edit pages, get page list)
- Added `TelegraphError` for API failures
- Added `html_to_nodes()` converter (stdlib `html.parser`, no new dependencies)

## License

Apache-2.0, see LICENSE.
