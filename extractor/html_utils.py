from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser
from typing import Dict, List
from urllib.parse import urljoin, urlparse


class LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: List[Dict[str, str]] = []
        self._current_href: str | None = None
        self._text_parts: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attr_map = dict(attrs)
        href = attr_map.get("href")
        if href:
            self._current_href = href
            self._text_parts = []

    def handle_data(self, data: str) -> None:
        if self._current_href is not None:
            self._text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._current_href is None:
            return
        text = collapse_text(" ".join(self._text_parts))
        self.links.append({"href": self._current_href, "text": text})
        self._current_href = None
        self._text_parts = []


def collect_links(html: str, base_url: str) -> List[Dict[str, str]]:
    parser = LinkCollector()
    parser.feed(html)
    results: List[Dict[str, str]] = []
    for link in parser.links:
        href = urljoin(base_url, link["href"])
        if urlparse(href).scheme not in {"http", "https"}:
            continue
        results.append({"href": href, "text": link["text"]})
    return results


def html_to_lines(html: str) -> List[str]:
    text = re.sub(r"<(?:br|/p|/div|/li|/tr|/h1|/h2|/h3|/h4|/h5|/h6|/section|/article|/ul|/ol)[^>]*>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"<li[^>]*>", "\n• ", text, flags=re.IGNORECASE)
    text = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    lines = [collapse_text(line) for line in text.splitlines()]
    return [line for line in lines if line]


def collapse_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()