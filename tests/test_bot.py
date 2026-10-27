import json

import pytest

from tg_botkit import Bot, TelegramError, missing_secrets, split_message, strip_tags
from tg_botkit import bot as botmod


class Resp:
    def __init__(self, body, status=200):
        self._b, self.status_code = body, status

    def json(self):
        return self._b


class Fake:
    """Replaces requests.post: `script` maps method -> list of responses (last one repeats)."""

    def __init__(self, script):
        self.script, self.calls = script, []

    def __call__(self, url, data=None, files=None, timeout=None):
        m = url.rsplit("/", 1)[1]
        self.calls.append((m, dict(data or {}), files))
        q = self.script[m]
        return q.pop(0) if len(q) > 1 else q[0]


def ok(result):
    return Resp({"ok": True, "result": result})


def err(desc, status=400):
    return Resp({"ok": False, "description": desc}, status)


@pytest.fixture
def bot():
    return Bot("T", "http://api", channel="-100")


def use(monkeypatch, script):
    f = Fake(script)
    monkeypatch.setattr(botmod.requests, "post", f)
    monkeypatch.setattr(botmod.time, "sleep", lambda s: None)
    return f


def test_429_is_retried(monkeypatch, bot):
    f = use(monkeypatch, {"getMe": [Resp({"ok": False, "parameters": {"retry_after": 1}}, 429), ok({"id": 1})]})
    assert bot.whoami() == {"id": 1} and len(f.calls) == 2


def test_rate_limited_forever_raises(monkeypatch, bot):
    use(monkeypatch, {"getMe": [Resp({"ok": False}, 429)]})
    with pytest.raises(TelegramError) as e:
        bot.whoami()
    assert e.value.status == 429


def test_send_falls_back_to_plain_on_bad_markup(monkeypatch, bot):
    f = use(monkeypatch, {"sendMessage": [err("Bad Request: can't parse entities: x"), ok({"message_id": 7})]})
    assert bot.send("<b>hi</b> <i>x") == 7
    assert "parse_mode" not in f.calls[1][1] and f.calls[1][1]["text"] == "hi x"


def test_send_other_400_is_raised(monkeypatch, bot):
    use(monkeypatch, {"sendMessage": [err("Bad Request: chat not found")]})
    with pytest.raises(TelegramError):
        bot.send("x")


def test_reply_and_silent_flags(monkeypatch, bot):
    f = use(monkeypatch, {"sendMessage": [ok({"message_id": 9})]})
    bot.reply(5, "r", silent=True)
    d = f.calls[0][1]
    assert d["reply_to_message_id"] == 5 and d["disable_notification"] == "true" and d["chat_id"] == "-100"


def test_photos_album_caption_on_first(monkeypatch, bot):
    f = use(monkeypatch, {"sendMediaGroup": [ok([{"message_id": 11}, {"message_id": 12}])]})
    assert bot.photos("cap", ["a", "b", "c"]) == 11
    media = json.loads(f.calls[0][1]["media"])
    assert media[0]["caption"] == "cap" and "caption" not in media[1]


def test_photos_falls_back_to_text(monkeypatch, bot):
    use(monkeypatch, {"sendPhoto": [err("Bad Request: failed to get HTTP URL content")], "sendMessage": [ok({"message_id": 3})]})
    assert bot.photos("cap", ["a"]) == 3


def test_photos_reply_to_on_album_and_single(monkeypatch, bot):
    f = use(monkeypatch, {"sendMediaGroup": [ok([{"message_id": 11}, {"message_id": 12}])],
                          "sendPhoto": [ok({"message_id": 3})]})
    assert bot.photos("cap", ["a", "b"], reply_to=5) == 11
    assert f.calls[0][1]["reply_to_message_id"] == 5
    assert f.calls[0][1]["allow_sending_without_reply"] == "true"
    assert bot.photos("cap", ["a"], reply_to=6) == 3
    assert f.calls[1][1]["reply_to_message_id"] == 6
    assert f.calls[1][1]["allow_sending_without_reply"] == "true"


def test_photos_without_reply_to_omits_field(monkeypatch, bot):
    f = use(monkeypatch, {"sendMediaGroup": [ok([{"message_id": 11}, {"message_id": 12}])]})
    bot.photos("cap", ["a", "b"])
    assert "reply_to_message_id" not in f.calls[0][1]
    assert "allow_sending_without_reply" not in f.calls[0][1]


def test_photos_fallback_keeps_reply_to(monkeypatch, bot):
    f = use(monkeypatch, {"sendPhoto": [err("Bad Request: failed to get HTTP URL content")],
                          "sendMessage": [ok({"message_id": 3})]})
    bot.photos("cap", ["a"], reply_to=5)
    assert f.calls[1][1]["reply_to_message_id"] == 5


def test_edit_photo_caption_after_text_refusal(monkeypatch, bot):
    f = use(monkeypatch, {"editMessageText": [err("Bad Request: there is no text in the message to edit")],
                          "editMessageCaption": [ok(True)]})
    bot.edit(4, "<b>x</b>")
    assert [c[0] for c in f.calls] == ["editMessageText", "editMessageCaption"]


def test_edit_not_modified_is_ignored(monkeypatch, bot):
    use(monkeypatch, {"editMessageText": [err("Bad Request: message is not modified: same")]})
    bot.edit(4, "x")


def test_pin_failure_is_soft(monkeypatch, bot):
    use(monkeypatch, {"pinChatMessage": [err("Bad Request: not enough rights")]})
    assert bot.pin(1) is False


def test_group_chunks_by_ten(monkeypatch, bot):
    f = use(monkeypatch, {"sendMediaGroup": [ok([{"message_id": i} for i in range(10)])], "sendDocument": [ok({"message_id": 99})]})
    ids = bot.group("document", [(f"f{i}", b"x") for i in range(11)], caption="c")
    assert [c[0] for c in f.calls] == ["sendMediaGroup", "sendDocument"] and ids[-1] == 99


def test_group_reply_to_on_every_chunk(monkeypatch, bot):
    f = use(monkeypatch, {"sendMediaGroup": [ok([{"message_id": i} for i in range(10)])], "sendDocument": [ok({"message_id": 99})]})
    bot.group("document", [(f"f{i}", b"x") for i in range(11)], reply_to=5)
    assert [c[1]["reply_to_message_id"] for c in f.calls] == [5, 5]
    assert [c[1]["allow_sending_without_reply"] for c in f.calls] == ["true", "true"]


def test_group_without_reply_to_omits_field(monkeypatch, bot):
    f = use(monkeypatch, {"sendMediaGroup": [ok([{"message_id": i} for i in range(10)])], "sendDocument": [ok({"message_id": 99})]})
    bot.group("document", [(f"f{i}", b"x") for i in range(11)])
    assert [c[0] for c in f.calls] == ["sendMediaGroup", "sendDocument"]
    assert all("reply_to_message_id" not in c[1] and "allow_sending_without_reply" not in c[1] for c in f.calls)


def test_no_chat_raises():
    with pytest.raises(ValueError):
        Bot("T", "http://api").send("x")


def test_text_helpers():
    assert strip_tags("<b>a &amp; b</b>") == "a & b"
    parts = split_message("p1\n\n" + "x" * 5000 + "\n\np3", limit=1000)
    assert all(len(p) <= 1000 for p in parts) and "".join(parts).count("x") == 5000


def test_missing_secrets():
    assert missing_secrets(["A", "B", "C"], {"A": "ok", "B": "CHANGEME"}) == ["B", "C"]
