import json
import logging
import time
from typing import Iterable, List, Optional, Tuple

import requests

from .text import strip_tags

log = logging.getLogger("tg_botkit")


class TelegramError(RuntimeError):
    """Bot API call failed. `status` is the HTTP status (429 = still rate limited after retries)."""

    def __init__(self, method: str, status: int, description: str):
        super().__init__(f"{method}: {description}" if description else f"{method}: HTTP {status}")
        self.method, self.status, self.description = method, status, description


def _silent(flag: bool) -> str:
    return "true" if flag else "false"


def _reply_params(reply_to: Optional[int]) -> Optional[str]:
    """Bot API 7.0+ `reply_parameters` JSON: answer `message_id`, do not fail if that message was deleted."""
    if not reply_to:
        return None
    return json.dumps({"message_id": reply_to, "allow_sending_without_reply": True})


class Bot:
    """Thin client for a (local) Bot API server. `channel` is the default chat for every send/edit helper."""

    def __init__(self, token: str, api_base: str, channel=None, timeout: int = 60, retries: int = 4):
        self.url = f"{api_base}/bot{token}"
        self.file_url = f"{api_base}/file/bot{token}"
        self.channel, self.timeout, self.retries = channel, timeout, retries

    # -- transport ---------------------------------------------------------------------------------------------
    def call(self, method: str, files: Optional[dict] = None, timeout: Optional[int] = None, **data):
        """POST one method; waits and retries on 429. Raises TelegramError on any other failure."""
        for _ in range(self.retries):
            r = requests.post(f"{self.url}/{method}", data=data, files=files, timeout=timeout or self.timeout)
            try:
                j = r.json()
            except ValueError:
                raise TelegramError(method, r.status_code, f"non-JSON response (HTTP {r.status_code})")
            if r.status_code == 429:
                time.sleep(int(j.get("parameters", {}).get("retry_after", 5)) + 1)
                continue
            if not j.get("ok"):
                raise TelegramError(method, r.status_code, j.get("description", ""))
            return j["result"]
        raise TelegramError(method, 429, "rate limited")

    def _chat(self, chat_id):
        chat_id = self.channel if chat_id is None else chat_id
        if chat_id is None:
            raise ValueError("no chat_id and no default channel")
        return chat_id

    # -- info ----------------------------------------------------------------------------------------------------
    def whoami(self) -> dict:
        return self.call("getMe")

    def chat_title(self, chat_id=None) -> str:
        return self.call("getChat", chat_id=self._chat(chat_id)).get("title", "")

    def my_status(self, chat_id=None) -> str:
        """The bot's own role in the chat: administrator, member, left, ..."""
        return self.call("getChatMember", chat_id=self._chat(chat_id), user_id=self.whoami()["id"])["status"]

    # -- send ----------------------------------------------------------------------------------------------------
    def send(self, text: str, chat_id=None, reply_to: Optional[int] = None, silent: bool = False,
             preview: bool = False, html: bool = True, reply_parameters: Optional[str] = None) -> int:
        """Send text; when Telegram rejects the HTML markup (400) it is resent as plain text. Returns the message id.
        `reply_to` uses the legacy `reply_to_message_id`; `reply_parameters` passes a pre-built Bot API 7.0+ reply
        object instead (used by `photos()`'s text fallback)."""
        extra = {"reply_parameters": reply_parameters} if reply_parameters else (
            {"reply_to_message_id": reply_to} if reply_to else {})
        common = dict(chat_id=self._chat(chat_id), disable_notification=_silent(silent), **extra)
        if html:
            try:
                return self.call("sendMessage", text=text, parse_mode="HTML",
                                 disable_web_page_preview=_silent(not preview), **common)["message_id"]
            except TelegramError as e:
                if e.status != 400 or "parse entities" not in e.description:
                    raise
                text = strip_tags(text)
        return self.call("sendMessage", text=text, disable_web_page_preview=_silent(not preview), **common)["message_id"]

    def reply(self, message_id: int, text: str, silent: bool = False, chat_id=None) -> int:
        return self.send(text, chat_id=chat_id, reply_to=message_id, silent=silent)

    def photos(self, caption: str, photos: List[str], silent: bool = False, chat_id=None,
               reply_to: Optional[int] = None) -> int:
        """1-10 photos by URL or file_id as one post, the caption on the first. If Telegram cannot fetch an image
        the post falls back to plain text. `reply_to` answers that message. Returns the id of the first message."""
        reply_parameters = _reply_params(reply_to)
        extra = {"reply_parameters": reply_parameters} if reply_parameters else {}
        common = dict(chat_id=self._chat(chat_id), disable_notification=_silent(silent), **extra)
        try:
            if len(photos) >= 2:
                media = [{"type": "photo", "media": p} for p in photos[:10]]
                media[0].update(caption=caption, parse_mode="HTML")
                return self.call("sendMediaGroup", media=json.dumps(media), **common)[0]["message_id"]
            if photos:
                return self.call("sendPhoto", photo=photos[0], caption=caption, parse_mode="HTML", **common)["message_id"]
        except TelegramError as e:
            log.warning("photo post failed (%s), falling back to text", e)
        return self.send(caption, chat_id=chat_id, silent=silent, preview=True, reply_parameters=reply_parameters)

    def group(self, kind: str, items: List[Tuple[str, object]], caption: str = "", silent: bool = False,
              chat_id=None, timeout: int = 600, reply_to: Optional[int] = None) -> List[int]:
        """Upload photos or documents (kind="photo"|"document"), 10 per media group; a group cannot mix kinds.
        `items` = (file name, bytes or open file). The caption rides on the first item, `reply_to` answers that
        message. Returns all message ids."""
        chat = self._chat(chat_id)
        extra = {"reply_parameters": _reply_params(reply_to)} if reply_to else {}
        ids: List[int] = []
        for n in range(0, len(items), 10):
            chunk = items[n:n + 10]
            cap = {"caption": caption, "parse_mode": "HTML"} if n == 0 and caption else {}
            if len(chunk) == 1:
                res = self.call({"photo": "sendPhoto", "document": "sendDocument"}[kind], files={kind: chunk[0]},
                                timeout=timeout, chat_id=chat, disable_notification=_silent(silent), **cap, **extra)
                ids.append(res["message_id"])
                continue
            files, media = {}, []
            for i, it in enumerate(chunk):
                files[f"f{i}"] = it
                media.append({"type": kind, "media": f"attach://f{i}", **(cap if i == 0 else {})})
            res = self.call("sendMediaGroup", files=files, timeout=timeout, chat_id=chat,
                            media=json.dumps(media), disable_notification=_silent(silent), **extra)
            ids += [m["message_id"] for m in res]
        return ids

    # -- edit / delete / pin ----------------------------------------------------------------------------------
    def edit(self, message_id: int, text: str, chat_id=None) -> None:
        """Edit a text OR photo/album message (caption); "not modified" is ignored, bad markup falls back to plain."""
        chat = self._chat(chat_id)
        for method, field in (("editMessageText", "text"), ("editMessageCaption", "caption")):
            for plain in (False, True):
                payload = {field: strip_tags(text) if plain else text}
                if not plain:
                    payload["parse_mode"] = "HTML"
                if field == "text":
                    payload["disable_web_page_preview"] = "true"
                try:
                    self.call(method, chat_id=chat, message_id=message_id, **payload)
                    return
                except TelegramError as e:
                    d = e.description
                    if "not modified" in d:
                        return
                    if "no text in the message" in d or "there is no text" in d or "no caption" in d:
                        break  # wrong kind of message: try the other method
                    if e.status == 400 and "parse entities" in d and not plain:
                        continue
                    raise
        raise TelegramError("edit", 400, "message has neither text nor caption")

    def delete(self, message_id: int, chat_id=None) -> bool:
        try:
            self.call("deleteMessage", chat_id=self._chat(chat_id), message_id=message_id)
            return True
        except TelegramError as e:
            log.debug("delete %s: %s", message_id, e)
            return False

    def pin(self, message_id: int, chat_id=None, silent: bool = True) -> bool:
        try:
            self.call("pinChatMessage", chat_id=self._chat(chat_id), message_id=message_id,
                      disable_notification=_silent(silent))
            return True
        except TelegramError as e:
            log.warning("pin failed: %s", e)
            return False

    def typing(self, chat_id=None) -> None:
        try:
            self.call("sendChatAction", chat_id=self._chat(chat_id), action="typing")
        except TelegramError:
            pass

    # -- receive ----------------------------------------------------------------------------------------------
    def updates(self, offset: int, wait: int = 30, allowed: Iterable[str] = ("message",)) -> list:
        """Long-poll getUpdates (no 429 retry: the caller loops anyway)."""
        r = requests.post(f"{self.url}/getUpdates", timeout=wait + 15, data={
            "offset": offset, "timeout": wait, "allowed_updates": json.dumps(list(allowed))})
        j = r.json()
        if not j.get("ok"):
            raise TelegramError("getUpdates", r.status_code, j.get("description", ""))
        return j["result"]

    def download(self, file_id: str, dest: str) -> None:
        info = self.call("getFile", file_id=file_id)
        r = requests.get(f"{self.file_url}/{info['file_path'].lstrip('/')}", timeout=120, stream=True)
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(65536):
                f.write(chunk)
