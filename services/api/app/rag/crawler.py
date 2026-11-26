"""Polite, bounded breadth-first crawler for one site.

Scope and limits (all enforced here, none delegated to the caller):

* Stays on the start URL's host (``www.`` and apex are treated as the same site).
* Honors ``robots.txt`` (RFC 9309): 4xx = no restrictions, 5xx/unreachable = crawl refused;
  ``Crawl-delay`` is respected up to a cap.
* ``max_pages`` and ``max_depth`` bound the work; include/exclude globs narrow it.
* Every request goes through ``SafeFetcher`` (SSRF, redirect, size and time limits).
* Duplicate pages are dropped by canonical URL and by content hash.
* One bad page never fails the crawl: it is counted and skipped.
"""

from __future__ import annotations

import fnmatch
import hashlib
import time
from collections import deque
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from urllib import robotparser
from urllib.parse import urlsplit

from app.core.config import MAX_CRAWL_DELAY_SECONDS
from app.rag.errors import IngestionError, TransientIngestionError
from app.rag.extract import Block
from app.rag.html_extract import HtmlPage, canonicalize_url
from app.rag.parser_runner import ParserLimits, ParserRunner
from app.rag.safe_fetch import BlockedDestinationError, FetchStatusError, SafeFetcher

HTML_TYPES = frozenset({"text/html", "application/xhtml+xml"})
MIN_PAGE_CHARS = 200
ROBOTS_MAX_BYTES = 512 * 1024

#: ``(body, charset, url) -> page``. Implementations must parse outside this process.
PageParser = Callable[[bytes, str, str], HtmlPage]


def _parse_isolated(body: bytes, charset: str, url: str) -> HtmlPage:
    return ParserRunner(ParserLimits()).html(body, url, charset)


@dataclass(frozen=True)
class CrawlConfig:
    start_url: str
    max_pages: int = 50
    max_depth: int = 2
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    delay_seconds: float = 0.5


@dataclass
class CrawlStats:
    fetched: int = 0
    indexed: int = 0
    duplicate_url: int = 0
    duplicate_content: int = 0
    robots_blocked: int = 0
    out_of_scope: int = 0
    low_content: int = 0
    noindex: int = 0
    unsupported_type: int = 0
    errors: int = 0
    blocked: int = 0
    stopped_at_limit: bool = False
    error_samples: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class CrawledPage:
    url: str  # canonical URL (identity of the document)
    title: str | None
    blocks: list[Block]
    content_hash: bytes
    etag: str | None
    depth: int
    raw_html: bytes


def _site_key(host: str) -> str:
    host = host.lower().rstrip(".")
    return host.removeprefix("www.")


def content_hash(text: str) -> bytes:
    return hashlib.sha256(text.encode()).digest()


def _matches(path_and_query: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatchcase(path_and_query, pattern) for pattern in patterns)


def load_robots(
    fetcher: SafeFetcher, start_url: str, host_ok: Callable[[str], bool]
) -> robotparser.RobotFileParser:
    parts = urlsplit(start_url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    parser = robotparser.RobotFileParser()
    try:
        result = fetcher.fetch(
            robots_url, accept="text/plain,*/*;q=0.1", host_ok=host_ok, max_bytes=ROBOTS_MAX_BYTES
        )
    except FetchStatusError as exc:
        if 400 <= exc.status < 500:
            parser.parse([])  # RFC 9309: robots.txt "unavailable" means no restrictions
            return parser
        raise TransientIngestionError("fetch_failed", f"robots.txt HTTP {exc.status}") from exc
    parser.parse(result.body.decode("utf-8", errors="replace").splitlines())
    return parser


def crawl(
    fetcher: SafeFetcher,
    config: CrawlConfig,
    stats: CrawlStats,
    *,
    known_hashes: set[bytes] | None = None,
    should_continue: Callable[[], bool] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    parse: PageParser = _parse_isolated,
) -> Iterator[CrawledPage]:
    """Yield each distinct, indexable page. ``stats`` is updated as the crawl proceeds."""
    start = canonicalize_url(config.start_url)
    site = _site_key(urlsplit(start).hostname or "")

    def host_ok(host: str) -> bool:
        return _site_key(host) == site

    robots = load_robots(fetcher, start, host_ok)
    agent = fetcher.user_agent.split("/", 1)[0]
    delay = config.delay_seconds
    declared = robots.crawl_delay(agent)
    if declared is not None:
        delay = max(delay, min(float(declared), MAX_CRAWL_DELAY_SECONDS))

    queue: deque[tuple[str, int]] = deque([(start, 0)])
    seen_urls = {start}
    seen_hashes = set(known_hashes or ())
    done_identities: set[str] = set()
    first = True
    while queue:
        if stats.indexed >= config.max_pages:
            stats.stopped_at_limit = True
            return
        if should_continue is not None and not should_continue():
            return
        url, depth = queue.popleft()
        parts = urlsplit(url)
        target = parts.path + (f"?{parts.query}" if parts.query else "")
        if not robots.can_fetch(agent, url):
            stats.robots_blocked += 1
            continue
        if config.include and not _matches(target, config.include) and url != start:
            stats.out_of_scope += 1
            continue
        if _matches(target, config.exclude):
            stats.out_of_scope += 1
            continue
        if not first and delay > 0:
            sleep(delay)
        first = False
        try:
            result = fetcher.fetch(url, host_ok=host_ok)
        except BlockedDestinationError as exc:
            stats.blocked += 1
            if url == start:
                raise  # the whole crawl was pointed somewhere forbidden
            _note(stats, exc)
            continue
        except IngestionError as exc:
            stats.errors += 1
            _note(stats, exc)
            if url == start and not exc.retryable:
                raise
            continue
        stats.fetched += 1
        if result.content_type not in HTML_TYPES:
            stats.unsupported_type += 1
            continue
        final = canonicalize_url(result.url)
        try:
            page = parse(result.body, _charset(result.headers), final)
        except IngestionError as exc:
            stats.errors += 1
            _note(stats, exc)
            if url == start:
                raise  # nothing can be crawled; the job decides whether to retry
            continue
        if page.noindex:
            stats.noindex += 1
        if depth < config.max_depth and not page.nofollow:
            for link in page.links:
                if link not in seen_urls and host_ok(urlsplit(link).hostname or ""):
                    seen_urls.add(link)
                    queue.append((link, depth + 1))
        if page.noindex:
            continue
        identity = _identity(page, final, host_ok)
        if identity in done_identities:
            stats.duplicate_url += 1
            continue
        done_identities.add(identity)
        text = page.text
        if len(text) < MIN_PAGE_CHARS:
            stats.low_content += 1
            continue
        digest = content_hash(text)
        if digest in seen_hashes:
            stats.duplicate_content += 1
            continue
        seen_hashes.add(digest)
        stats.indexed += 1
        yield CrawledPage(
            url=identity,
            title=page.title,
            blocks=page.blocks,
            content_hash=digest,
            etag=result.etag,
            depth=depth,
            raw_html=result.body,
        )


def _identity(page: HtmlPage, fetched_url: str, host_ok: Callable[[str], bool]) -> str:
    """The page's canonical URL if it names the same site, else the URL we fetched."""
    if page.canonical:
        candidate = canonicalize_url(page.canonical if "://" in page.canonical else fetched_url)
        if host_ok(urlsplit(candidate).hostname or ""):
            return candidate
    return fetched_url


def _charset(headers: dict[str, str]) -> str:
    content_type = headers.get("content-type", "")
    if "charset=" in content_type:
        name = content_type.split("charset=", 1)[1].split(";", 1)[0].strip().strip("\"'")
        try:
            "".encode(name)
        except LookupError:
            return "utf-8"
        return name
    return "utf-8"


def _note(stats: CrawlStats, exc: IngestionError) -> None:
    if len(stats.error_samples) < 5:
        stats.error_samples.append(f"{exc.code}: {exc.detail or ''}"[:160])
