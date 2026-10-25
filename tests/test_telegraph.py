import json

import pytest

from tg_botkit import Telegraph, TelegraphError, html_to_nodes
from tg_botkit import telegraph as telmod


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
def telegraph():
    return Telegraph("TEST_TOKEN", "http://api", timeout=30)


def use(monkeypatch, script):
    f = Fake(script)
    monkeypatch.setattr(telmod.requests, "post", f)
    monkeypatch.setattr(telmod.time, "sleep", lambda s: None)
    return f


def test_create_page_happy_path(monkeypatch, telegraph):
    f = use(monkeypatch, {"createPage": [ok({"url": "https://telegra.ph/test-10-01", "path": "test-10-01"})]})
    res = telegraph.create_page("Title", [{"tag": "p", "children": ["Hello"]}])
    assert res["url"] == "https://telegra.ph/test-10-01"
    assert res["path"] == "test-10-01"
    assert f.calls[0][1]["access_token"] == "TEST_TOKEN"
    assert f.calls[0][1]["title"] == "Title"


def test_create_page_from_html_string(monkeypatch, telegraph):
    f = use(monkeypatch, {"createPage": [ok({"url": "https://telegra.ph/test-10-01", "path": "test-10-01"})]})
    res = telegraph.create_page("Title", "<p>Hello <b>world</b></p>")
    assert res["url"] == "https://telegra.ph/test-10-01"
    # content should be JSON-encoded nodes
    content_arg = f.calls[0][1]["content"]
    nodes = json.loads(content_arg)
    assert any(n.get("tag") == "p" for n in nodes)


def test_edit_page(monkeypatch, telegraph):
    f = use(monkeypatch, {"editPage": [ok({"url": "https://telegra.ph/test-10-01", "path": "test-10-01"})]})
    res = telegraph.edit_page("test-10-01", title="New Title", content=[{"tag": "p", "children": ["Updated"]}])
    assert res["path"] == "test-10-01"
    assert f.calls[0][1]["path"] == "test-10-01"
    assert f.calls[0][1]["title"] == "New Title"


def test_get_page_list(monkeypatch, telegraph):
    f = use(monkeypatch, {"getPageList": [ok({"pages": [{"path": "p1"}, {"path": "p2"}], "total_count": 2})]})
    res = telegraph.get_page_list(offset=0, limit=50)
    assert len(res["pages"]) == 2
    assert f.calls[0][1]["offset"] == 0
    assert f.calls[0][1]["limit"] == 50


def test_get_page(monkeypatch, telegraph):
    f = use(monkeypatch, {"getPage": [ok({"path": "test-10-01", "title": "Title", "content": [{"tag": "p", "children": ["Hi"]}]})]})
    res = telegraph.get_page("test-10-01")
    assert res["path"] == "test-10-01"
    assert f.calls[0][1]["path"] == "test-10-01"


def test_create_page_api_error_raises(monkeypatch, telegraph):
    use(monkeypatch, {"createPage": [err("INVALID_TOKEN")]})
    with pytest.raises(TelegraphError) as e:
        telegraph.create_page("Title", "content")
    assert e.value.method == "createPage"
    assert "INVALID_TOKEN" in e.value.description


def test_429_retry(monkeypatch, telegraph):
    f = use(monkeypatch, {"createPage": [Resp({"ok": False, "description": "rate limited"}, 429), ok({"url": "https://telegra.ph/test", "path": "test"})]})
    res = telegraph.create_page("Title", "content")
    assert res["path"] == "test"
    assert len(f.calls) == 2


def test_5xx_retry(monkeypatch, telegraph):
    f = use(monkeypatch, {"createPage": [Resp({"ok": False, "description": "server error"}, 500), ok({"url": "https://telegra.ph/test", "path": "test"})]})
    res = telegraph.create_page("Title", "content")
    assert res["path"] == "test"
    assert len(f.calls) == 2


def test_create_account_stores_token(monkeypatch, telegraph):
    f = use(monkeypatch, {"createAccount": [ok({"access_token": "NEW_TOKEN", "author_name": "Test"})]})
    token = telegraph.create_account("ShortName", author_name="Author")
    assert token == "NEW_TOKEN"
    assert telegraph.access_token == "NEW_TOKEN"


# HTML to nodes conversion tests

def test_html_to_nodes_paragraph():
    nodes = html_to_nodes("<p>Hello world</p>")
    assert len(nodes) == 1
    assert nodes[0]["tag"] == "p"
    assert nodes[0]["children"] == ["Hello world"]


def test_html_to_nodes_bold():
    nodes = html_to_nodes("<p>Hello <b>bold</b> world</p>")
    assert len(nodes) == 1
    assert nodes[0]["tag"] == "p"
    children = nodes[0]["children"]
    assert "Hello " in children
    assert any(isinstance(c, dict) and c.get("tag") == "b" and c.get("children") == ["bold"] for c in children)
    assert " world" in children


def test_html_to_nodes_link():
    nodes = html_to_nodes('<p><a href="https://example.com">link</a></p>')
    assert len(nodes) == 1
    assert nodes[0]["tag"] == "p"
    children = nodes[0]["children"]
    assert any(isinstance(c, dict) and c.get("tag") == "a" and c.get("attrs", {}).get("href") == "https://example.com" and c.get("children") == ["link"] for c in children)


def test_html_to_nodes_nested():
    nodes = html_to_nodes("<p><b><i>nested</i></b></p>")
    assert len(nodes) == 1
    assert nodes[0]["tag"] == "p"
    b_node = nodes[0]["children"][0]
    assert b_node["tag"] == "b"
    i_node = b_node["children"][0]
    assert i_node["tag"] == "i"
    assert i_node["children"] == ["nested"]


def test_html_to_nodes_line_break():
    nodes = html_to_nodes("<p>line1<br>line2</p>")
    assert len(nodes) == 1
    assert nodes[0]["tag"] == "p"
    children = nodes[0]["children"]
    assert "line1" in children
    assert "\n" in children
    assert "line2" in children


def test_html_to_nodes_headings():
    nodes = html_to_nodes("<h1>Title</h1><h2>Subtitle</h2><h6>Small</h6>")
    # Telegraph only supports h3/h4, so h1/h2 collapse to h3 and h5/h6 to h4.
    assert [n["tag"] for n in nodes] == ["h3", "h3", "h4"]
    assert nodes[0]["children"] == ["Title"]
    assert nodes[1]["children"] == ["Subtitle"]
    assert nodes[2]["children"] == ["Small"]


def test_html_to_nodes_code():
    nodes = html_to_nodes("<p><code>code</code></p>")
    assert len(nodes) == 1
    assert nodes[0]["tag"] == "p"
    children = nodes[0]["children"]
    assert any(isinstance(c, dict) and c.get("tag") == "code" and c.get("children") == ["code"] for c in children)


def test_html_to_nodes_blockquote():
    nodes = html_to_nodes("<blockquote>Quote</blockquote>")
    assert len(nodes) == 1
    assert nodes[0]["tag"] == "blockquote"
    assert nodes[0]["children"] == ["Quote"]


def test_html_to_nodes_hr():
    nodes = html_to_nodes("<hr>")
    assert len(nodes) == 1
    assert nodes[0]["tag"] == "hr"
    assert nodes[0]["children"] == []


def test_html_to_nodes_lists():
    nodes = html_to_nodes("<ul><li>item1</li><li>item2</li></ul>")
    assert len(nodes) == 1
    assert nodes[0]["tag"] == "ul"
    li_nodes = nodes[0]["children"]
    assert len(li_nodes) == 2
    assert li_nodes[0]["tag"] == "li"
    assert li_nodes[0]["children"] == ["item1"]
    assert li_nodes[1]["tag"] == "li"
    assert li_nodes[1]["children"] == ["item2"]


def test_html_to_nodes_entities():
    nodes = html_to_nodes("<p>&amp; &lt; &gt; &quot; &apos; &nbsp;</p>")
    assert len(nodes) == 1
    children = nodes[0]["children"]
    text = children[0]
    assert "&" in text
    assert "<" in text
    assert ">" in text
    assert '"' in text
    assert "'" in text
    assert "\xa0" in text


def test_html_to_nodes_empty_content():
    nodes = html_to_nodes("")
    assert nodes == []


def test_html_to_nodes_multiple_root_elements():
    nodes = html_to_nodes("<p>One</p><p>Two</p>")
    assert len(nodes) == 2
    assert nodes[0]["tag"] == "p"
    assert nodes[1]["tag"] == "p"