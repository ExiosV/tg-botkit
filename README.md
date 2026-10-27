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

## Use in a project

The repo is public, so a project pins a tag in `pyproject.toml` and pip fetches the GitHub tarball (no git, no
credentials, works in the Docker builds on devicex2):

```toml
dependencies = ["tg-botkit @ https://github.com/ExiosV/tg-botkit/archive/refs/tags/v0.2.0.tar.gz", ...]
```

To change the client edit **this** repo, bump `__version__` + `pyproject.toml`, merge, tag `vX.Y.Z`, then bump the tag
in each consumer (PR per project). `scripts/vendor.sh` is kept only for a consumer that cannot reach GitHub at build
time; do not vendor otherwise.

## Dev
`pip install -e '.[dev]' && pytest`

## Changelog

### 0.3.0
- `photos()` and `group()` accept an optional `reply_to` message id, so a photo/album/media group can answer a
  message inside a channel discussion thread (same `reply_to_message_id` field as `send()`)

### 0.2.0
- Added `Telegraph` client for telegra.ph API (create/edit pages, get page list)
- Added `TelegraphError` for API failures
- Added `html_to_nodes()` converter (stdlib `html.parser`, no new dependencies)

## License

Apache-2.0, see LICENSE.
