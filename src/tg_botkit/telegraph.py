"""Telegraph (telegra.ph) client: create pages, edit pages, list/get pages."""

from __future__ import annotations

import html.parser
import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple, Union

import requests


log = logging.getLogger("tg_botkit.telegraph")


class TelegraphError(RuntimeError):
    """Telegraph API call failed. `.description` contains the error message."""

    def __init__(self, method: str, description: str):
        super().__init__(f"{method}: {description}")
        self.method, self.description = method, description


class Telegraph:
    """Client for the Telegraph API (telegra.ph).

    `content` parameter accepts either a ready node list or an HTML string.
    """

    def __init__(
        self,
        access_token: Optional[str] = None,
        base_url: str = "https://api.telegra.ph",
        timeout: int = 30,
    ):
        self.access_token = access_token
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _call(
        self,
        method: str,
        data: Optional[Dict[str, Any]] = None,
        retries: int = 2,
    ) -> Dict[str, Any]:
        """POST one method; waits and retries once on 429/5xx. Raises TelegraphError on failure."""
        data = data or {}
        for attempt in range(retries):
            r = requests.post(
                f"{self.base_url}/{method}",
                data=data,
                timeout=self.timeout,
            )
            if r.status_code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(1)
                continue
            try:
                j = r.json()
            except ValueError:
                raise TelegraphError(method, f"non-JSON response (HTTP {r.status_code})")
            if not j.get("ok"):
                raise TelegraphError(method, j.get("description", f"HTTP {r.status_code}"))
            return j["result"]
        raise TelegraphError(method, "request failed after retries")

    def create_account(
        self,
        short_name: str,
        author_name: Optional[str] = None,
        author_url: Optional[str] = None,
    ) -> str:
        """Create a Telegraph account; stores and returns the access token."""
        data = {"short_name": short_name[:32]}
        if author_name:
            data["author_name"] = author_name[:128]
        if author_url:
            data["author_url"] = author_url[:256]
        result = self._call("createAccount", data)
        self.access_token = result.get("access_token")
        return self.access_token

    def _nodes_to_content(self, content: Union[List[Dict[str, Any]], str]) -> List[Dict[str, Any]]:
        """Ensure content is a node list, converting HTML if needed."""
        if isinstance(content, str):
            return html_to_nodes(content)
        return content

    def create_page(
        self,
        title: str,
        content: Union[List[Dict[str, Any]], str],
        author_name: Optional[str] = None,
        author_url: Optional[str] = None,
        return_content: bool = False,
    ) -> Dict[str, Any]:
        """Create a Telegraph page. Returns the API result."""
        node_content = self._nodes_to_content(content)
        content_json = json.dumps(node_content, ensure_ascii=False)
        data: Dict[str, Any] = {
            "access_token": self.access_token,
            "title": title[:256],
            "content": content_json,
            "return_content": "true" if return_content else "false",
        }
        if author_name:
            data["author_name"] = author_name[:128]
        if author_url:
            data["author_url"] = author_url[:256]
        return self._call("createPage", data)

    def edit_page(
        self,
        path: str,
        title: Optional[str] = None,
        content: Optional[Union[List[Dict[str, Any]], str]] = None,
        author_name: Optional[str] = None,
        author_url: Optional[str] = None,
        return_content: bool = False,
    ) -> Dict[str, Any]:
        """Edit an existing Telegraph page. Returns the API result."""
        data: Dict[str, Any] = {
            "access_token": self.access_token,
            "path": path,
            "return_content": "true" if return_content else "false",
        }
        if title:
            data["title"] = title[:256]
        if content is not None:
            node_content = self._nodes_to_content(content)
            data["content"] = json.dumps(node_content, ensure_ascii=False)
        if author_name:
            data["author_name"] = author_name[:128]
        if author_url:
            data["author_url"] = author_url[:256]
        return self._call("editPage", data)

    def get_page_list(self, offset: int = 0, limit: int = 50) -> Dict[str, Any]:
        """Get list of pages. Returns the API result."""
        data = {
            "access_token": self.access_token,
            "offset": offset,
            "limit": limit,
        }
        return self._call("getPageList", data)

    def get_page(self, path: str, return_content: bool = True) -> Dict[str, Any]:
        """Get a single page by path. Returns the API result."""
        data = {
            "access_token": self.access_token,
            "path": path,
            "return_content": "true" if return_content else "false",
        }
        return self._call("getPage", data)


def html_to_nodes(html: str) -> List[Dict[str, Any]]:
    """Convert an HTML string into a Telegraph node list (stdlib ``html.parser``)."""
    parser = _HTMLToNodesParser()
    parser.feed(html)
    parser.close()
    return parser.get_result()


# Tags that carry no children and never get a closing tag.
_VOID_TAGS = {"br", "hr", "img"}
# Telegraph only understands h3/h4, so bigger/smaller headings collapse into them.
_HEADING_MAP = {"h1": "h3", "h2": "h3", "h5": "h4", "h6": "h4"}
# Attributes Telegraph accepts, per tag; everything else (class, style, id) is dropped.
_ALLOWED_ATTRS = {"a": ("href",), "img": ("src",), "iframe": ("src",), "video": ("src",)}


class _HTMLToNodesParser(html.parser.HTMLParser):
    """Turn a flat stream of HTML start/end tags into nested Telegraph nodes."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.nodes: List[Any] = []
        # Each frame is (tag, children, attrs) for an element that is still open.
        self.stack: List[Tuple[str, List[Any], Dict[str, Any]]] = []
        self._text: List[str] = []

    def get_result(self) -> List[Dict[str, Any]]:
        self._flush()
        while self.stack:
            self._close_top()
        # Telegraph wants a list of nodes; wrap stray top-level text in a paragraph.
        return [{"tag": "p", "children": [n]} if isinstance(n, str) else n for n in self.nodes]

    def _append(self, item: Any) -> None:
        if self.stack:
            self.stack[-1][1].append(item)
        else:
            self.nodes.append(item)

    def _flush(self) -> None:
        if not self._text:
            return
        text = "".join(self._text)
        self._text = []
        if not self.stack and not text.strip():
            return  # whitespace between top-level blocks is irrelevant
        if text:
            self._append(text)

    def _close_top(self) -> None:
        tag, children, attrs = self.stack.pop()
        node: Dict[str, Any] = {"tag": tag, "children": children}
        if attrs:
            node["attrs"] = attrs
        self._append(node)

    def handle_starttag(self, tag: str, attrs: list) -> None:
        self._flush()
        tag = _HEADING_MAP.get(tag, tag)
        attrs_dict = {k: v for k, v in attrs if k in _ALLOWED_ATTRS.get(tag, ()) and v}
        if tag == "br":
            self._append("\n")
        elif tag == "hr":
            self._append({"tag": "hr", "children": []})
        elif tag == "img":
            node: Dict[str, Any] = {"tag": "img", "children": []}
            if attrs_dict:
                node["attrs"] = attrs_dict
            self._append(node)
        else:
            self.stack.append((tag, [], attrs_dict))

    def handle_startendtag(self, tag: str, attrs: list) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in _VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        self._flush()
        tag = _HEADING_MAP.get(tag, tag)
        if tag in _VOID_TAGS:
            return
        # Auto-close anything left open above the matching tag.
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                while len(self.stack) > i:
                    self._close_top()
                return

    def handle_data(self, data: str) -> None:
        self._text.append(data)

    def forget(self) -> None:
        self.nodes, self.stack, self._text = [], [], []