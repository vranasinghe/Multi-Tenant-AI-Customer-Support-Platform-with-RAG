"""Main-content extraction from HTML without third-party parsers.

The goal is the article text, not the page chrome. The extractor ignores scripts, styles,
navigation, headers/footers, sidebars, forms, cookie banners and link-heavy blocks, prefers
``<main>``/``<article>`` when present, and keeps headings so chunks carry a ``heading_path``.
It also collects links for the crawler, the canonical URL and robots meta directives.

HTML is untrusted: nothing is executed or rendered; the output is plain text blocks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from app.rag.extract import Block, normalize_text

_VOID = frozenset(("area base br col embed hr img input link meta param source track wbr").split())
_SKIP_TAGS = frozenset(
    (
        "script style noscript template svg iframe canvas form select button nav footer "
        "aside head object embed dialog"
    ).split()
)
_SKIP_ROLES = frozenset({"navigation", "banner", "contentinfo", "complementary", "search"})
_SKIP_WORDS = re.compile(
    r"(?:^|[\s_-])(cookie|consent|gdpr|banner|sidebar|breadcrumb|advert|ads?|promo|newsletter|"
    r"social|share|popup|modal|menu|navbar|toolbar|footer|skip-link)(?:$|[\s_-])",
    re.I,
)
_BLOCK_TAGS = frozenset(
    (
        "p li h1 h2 h3 h4 h5 h6 pre blockquote td th dt dd figcaption caption summary div section"
    ).split()
)
_HEADINGS = {f"h{i}": i for i in range(1, 7)}
_TRACKING = re.compile(r"^(utm_|fbclid$|gclid$|msclkid$|mc_|ref$|ref_src$)", re.I)
MAX_LINKS = 3000


@dataclass
class HtmlPage:
    title: str | None = None
    blocks: list[Block] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    canonical: str | None = None
    noindex: bool = False
    nofollow: bool = False

    @property
    def text(self) -> str:
        return "\n\n".join(b.text for b in self.blocks)


@dataclass
class _Frame:
    tag: str
    skip: bool
    main: bool
    block: bool


def canonicalize_url(url: str) -> str:
    """Stable form for dedupe: lowercase scheme/host, no fragment, default port or tracking."""
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    port = parts.port
    netloc = host if port in (None, 80 if scheme == "http" else 443) else f"{host}:{port}"
    query = urlencode(
        sorted(
            (k, v)
            for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if not _TRACKING.match(k)
        )
    )
    path = parts.path or "/"
    return urlunsplit((scheme, netloc, path, query, ""))


class _Extractor(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.page = HtmlPage()
        self._stack: list[_Frame] = []
        self._in_title = False
        self._title_parts: list[str] = []
        self._buf: list[str] = []
        self._buf_link_chars = 0
        self._anchor_depth = 0
        self._heading_stack: list[tuple[int, str]] = []
        self._current_heading: int | None = None
        # Two candidates: everything outside chrome, and only what is inside <main>/<article>.
        self.general: list[Block] = []
        self.main: list[Block] = []
        self._seen_links: set[str] = set()

    # -- helpers --------------------------------------------------------------------------
    def _skipping(self) -> bool:
        return any(f.skip for f in self._stack)

    def _in_main(self) -> bool:
        return any(f.main for f in self._stack)

    def _flush(self) -> None:
        raw = "".join(self._buf)
        link_chars = self._buf_link_chars
        self._buf, self._buf_link_chars = [], 0
        text = normalize_text(re.sub(r"\s+", " ", raw))
        if not text:
            return
        is_heading = self._current_heading is not None
        if not is_heading and len(text) < 80 and link_chars > 0.7 * len(text):
            return  # short, link-dominated block: menu/related-links boilerplate
        if is_heading:
            level = self._current_heading or 1
            self._heading_stack[:] = [(lvl, t) for lvl, t in self._heading_stack if lvl < level]
            self._heading_stack.append((level, text[:200]))
        path = tuple(t for _, t in self._heading_stack)
        block = Block(text=text, heading_path=path, is_heading=is_heading)
        self.general.append(block)
        if self._in_main():
            self.main.append(block)

    # -- parser callbacks -----------------------------------------------------------------
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: (v or "") for k, v in attrs}
        if tag == "link" and "canonical" in a.get("rel", "").lower().split():
            self.page.canonical = a.get("href") or None
        if tag == "meta" and a.get("name", "").lower() == "robots":
            content = a.get("content", "").lower()
            self.page.noindex = self.page.noindex or "noindex" in content
            self.page.nofollow = self.page.nofollow or "nofollow" in content
        if tag in _VOID:
            return
        if tag == "title":
            self._in_title = True
        skip = (
            tag in _SKIP_TAGS
            or a.get("role", "").lower() in _SKIP_ROLES
            or "hidden" in a
            or a.get("aria-hidden", "").lower() == "true"
            or bool(_SKIP_WORDS.search(f"{a.get('class', '')} {a.get('id', '')}"))
        )
        # <main>/<article> win over class-name heuristics ("article-share" is skipped, the
        # article itself is not).
        main = tag in {"main", "article"} or a.get("role", "").lower() == "main"
        if main and tag != "nav":
            skip = skip and tag in _SKIP_TAGS
        is_block = tag in _BLOCK_TAGS or tag == "br"
        if is_block and tag != "br" and not self._skipping():
            self._flush()
            self._current_heading = _HEADINGS.get(tag)
        if tag == "a":
            self._anchor_depth += 1
            if not self._skipping() and not skip:
                self._collect_link(a.get("href", ""), a.get("rel", ""))
        self._stack.append(_Frame(tag, skip, main, is_block))

    def handle_endtag(self, tag: str) -> None:
        if tag in _VOID:
            return
        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index].tag == tag:
                closing = self._stack[index:]
                skipping_before = any(f.skip for f in self._stack[:index])
                del self._stack[index:]
                if (
                    any(f.block for f in closing)
                    and not skipping_before
                    and not any(f.skip for f in closing)
                ):
                    self._flush()
                    self._current_heading = None
                break
        if tag == "title":
            self._in_title = False
        if tag == "a":
            self._anchor_depth = max(0, self._anchor_depth - 1)

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)
            return
        if self._skipping():
            return
        self._buf.append(data)
        if self._anchor_depth:
            self._buf_link_chars += len(data.strip())

    def _collect_link(self, href: str, rel: str) -> None:
        if (
            not href
            or len(self._seen_links) >= MAX_LINKS
            or "nofollow" in rel.lower()
            or href.startswith(("#", "mailto:", "tel:", "javascript:", "data:"))
        ):
            return
        absolute = urljoin(self.base_url, href)
        if urlsplit(absolute).scheme in {"http", "https"}:
            canon = canonicalize_url(absolute)
            if canon not in self._seen_links:
                self._seen_links.add(canon)
                self.page.links.append(canon)


def extract_html(html: str, base_url: str, *, min_main_chars: int = 200) -> HtmlPage:
    parser = _Extractor(base_url)
    try:
        parser.feed(html)
        parser.close()
    except (AssertionError, RecursionError):  # html.parser can choke on pathological markup
        pass
    parser._flush()
    page = parser.page
    page.title = normalize_text(" ".join("".join(parser._title_parts).split()))[:300] or None
    main_chars = sum(len(b.text) for b in parser.main if not b.is_heading)
    page.blocks = parser.main if main_chars >= min_main_chars else parser.general
    if page.title is None:
        page.title = next((b.text for b in page.blocks if b.is_heading), None)
    return page
