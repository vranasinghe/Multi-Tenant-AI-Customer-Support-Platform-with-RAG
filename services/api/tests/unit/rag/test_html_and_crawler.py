"""Main-content extraction and the bounded crawler (against a local test server)."""

from __future__ import annotations

import pytest

from app.rag.crawler import CrawlConfig, CrawledPage, CrawlStats, crawl
from app.rag.errors import IngestionError, TransientIngestionError
from app.rag.html_extract import canonicalize_url, extract_html
from app.rag.safe_fetch import BlockedDestinationError
from tests.support.site import Site, html_page, serve

LOREM = (
    "Our standard shipping takes three to five business days within the continental United States. "
    "Expedited options are available at checkout for an additional fee. "
    "Orders placed before noon Eastern time are dispatched the same day whenever stock allows. "
)


def crawl_all(
    site: Site, config: CrawlConfig, **kwargs: object
) -> tuple[list[CrawledPage], CrawlStats]:
    stats = CrawlStats()
    pages = list(crawl(site.fetcher(), config, stats, sleep=lambda _s: None, **kwargs))  # type: ignore[arg-type]
    return pages, stats


# ------------------------------------------------------------------------ extraction


def test_extracts_main_content_and_drops_boilerplate() -> None:
    html = f"""<html><head><title>Shipping</title><script>var secret = 1;</script>
      <style>.x {{ color: red }}</style></head><body>
      <header><a href="/">Home</a></header>
      <nav><ul><li><a href="/a">Products</a></li><li><a href="/b">Pricing</a></li></ul></nav>
      <div class="cookie-banner">We use cookies. Accept all.</div>
      <main><h1>Shipping</h1><p>{LOREM}</p><h2>Returns</h2><p>Returns are free within 30 days.</p></main>
      <aside>Related: buy more stuff</aside>
      <footer>Copyright 2026 Acme. All rights reserved.</footer>
      <script>track()</script></body></html>"""

    page = extract_html(html, "https://example.com/shipping", min_main_chars=50)
    text = page.text

    assert page.title == "Shipping"
    assert "three to five business days" in text and "Returns are free" in text
    for noise in ("secret", "color: red", "Products", "cookies", "Related", "Copyright", "track()"):
        assert noise not in text
    body = [b for b in page.blocks if not b.is_heading]
    assert body[-1].heading_path == ("Shipping", "Returns")


def test_falls_back_to_the_whole_page_when_there_is_no_main() -> None:
    page = extract_html(f"<html><body><div><p>{LOREM}</p></div></body></html>", "https://e.com/")
    assert "business days" in page.text


def test_link_heavy_blocks_are_treated_as_menus() -> None:
    html = f"<body><div><a href='/a'>One</a> <a href='/b'>Two</a></div><p>{LOREM}</p></body>"
    page = extract_html(html, "https://e.com/")
    assert "One" not in page.text and "business days" in page.text


def test_links_are_absolute_canonical_and_filtered() -> None:
    html = """<body><main><p>x</p>
      <a href="/docs?utm_source=mail&b=2&a=1#frag">a</a>
      <a href="https://other.com/x">b</a><a href="mailto:a@b.com">c</a>
      <a href="javascript:void(0)">d</a><a href="#top">e</a><a rel="nofollow" href="/nf">f</a>
      <a href="/docs?a=1&b=2">dup</a></main></body>"""

    page = extract_html(html, "https://example.com/start")

    assert page.links == ["https://example.com/docs?a=1&b=2", "https://other.com/x"]


def test_robots_meta_and_canonical_are_read() -> None:
    html = (
        '<head><meta name="robots" content="noindex, nofollow">'
        '<link rel="canonical" href="https://e.com/canon"></head><body><p>x</p></body>'
    )
    page = extract_html(html, "https://e.com/page")
    assert (page.noindex, page.nofollow, page.canonical) == (True, True, "https://e.com/canon")


@pytest.mark.parametrize(
    "markup",
    ["<p>unclosed <b>tags", "<<<>>>", "<div" * 50, "<p>" + "<div>" * 3000, "\x00\x01<p>bad", ""],
)
def test_malformed_html_never_raises(markup: str) -> None:
    extract_html(markup, "https://e.com/")


def test_script_content_is_never_extracted_even_when_unclosed() -> None:
    page = extract_html("<body><p>keep this</p><script>steal(document.cookie)", "https://e.com/")
    assert "steal" not in page.text


def test_canonicalize_url() -> None:
    assert (
        canonicalize_url("HTTP://Example.COM:80/a?b=1&utm_campaign=x#top")
        == "http://example.com/a?b=1"
    )
    assert canonicalize_url("https://example.com") == "https://example.com/"
    assert canonicalize_url("https://example.com:8443/") == "https://example.com:8443/"


# ---------------------------------------------------------------------------- crawling


def build_site(site: Site) -> None:
    site.text("/robots.txt", "User-agent: *\nDisallow: /private/\n")
    site.page("/", "Home", f"<p>{LOREM}</p>", links=["/a", "/b", "/private/secret", "/a#section"])
    site.page("/a", "Page A", f"<p>Alpha policy. {LOREM}</p>", links=["/c", "/"])
    site.page("/b", "Page B", f"<p>Beta policy. {LOREM}</p>", links=["/c"])
    site.page("/c", "Page C", f"<p>Gamma policy. {LOREM}</p>", links=["/d"])
    site.page("/d", "Page D", f"<p>Delta policy. {LOREM}</p>")
    site.page("/private/secret", "Secret", f"<p>Hidden. {LOREM}</p>")


def test_crawl_is_breadth_first_bounded_by_depth_and_honors_robots() -> None:
    with serve() as site:
        build_site(site)

        pages, stats = crawl_all(
            site, CrawlConfig(site.base + "/", max_pages=50, max_depth=2, delay_seconds=0)
        )

        urls = {p.url.removeprefix(site.base) for p in pages}
        assert urls == {"/", "/a", "/b", "/c"}  # /d is depth 3, /private is disallowed
        assert stats.robots_blocked == 1
        assert "/private/secret" not in site.requests
        assert [p.depth for p in pages] == sorted(p.depth for p in pages)  # BFS order


def test_max_pages_stops_the_crawl() -> None:
    with serve() as site:
        build_site(site)

        pages, stats = crawl_all(
            site, CrawlConfig(site.base + "/", max_pages=2, max_depth=5, delay_seconds=0)
        )

        assert len(pages) == 2 and stats.stopped_at_limit is True
        assert len(site.requests) <= 4  # robots + pages fetched, not the whole site


def test_duplicate_content_and_duplicate_urls_are_dropped() -> None:
    with serve() as site:
        site.page(
            "/", "Home", f"<p>{LOREM}</p>", links=["/copy", "/a", "/a?utm_source=x", "/canon-dup"]
        )
        site.page("/copy", "Home", f"<p>{LOREM}</p>")  # identical text to home
        site.page("/a", "A", f"<p>Unique A. {LOREM}</p>")
        site.routes["/canon-dup"] = (
            200,
            {"Content-Type": "text/html"},
            html_page(
                "A again",
                f"<p>Different words entirely. {LOREM * 2}</p>",
                head=f'<link rel="canonical" href="{site.base}/a">',
            ),
        )

        pages, stats = crawl_all(site, CrawlConfig(site.base + "/", delay_seconds=0))

        assert {p.url.removeprefix(site.base) for p in pages} == {"/", "/a"}
        assert stats.duplicate_content == 1
        assert stats.duplicate_url == 1  # tracking-param variant canonicalizes to /a
        assert stats.indexed == 2


def test_known_hashes_skip_content_already_indexed_elsewhere() -> None:
    with serve() as site:
        site.page("/", "Home", f"<p>{LOREM}</p>")
        first, _ = crawl_all(site, CrawlConfig(site.base + "/", delay_seconds=0))

        again, stats = crawl_all(
            site,
            CrawlConfig(site.base + "/", delay_seconds=0),
            known_hashes={first[0].content_hash},
        )

        assert again == [] and stats.duplicate_content == 1


def test_include_and_exclude_patterns() -> None:
    with serve() as site:
        build_site(site)
        config = CrawlConfig(
            site.base + "/", max_depth=3, include=("/a*", "/c"), exclude=("/c",), delay_seconds=0
        )

        pages, stats = crawl_all(site, config)

        assert {p.url.removeprefix(site.base) for p in pages} == {
            "/",
            "/a",
        }  # start URL always allowed
        assert stats.out_of_scope >= 2


def test_crawl_stays_on_the_start_host() -> None:
    with serve() as site:
        site.page(
            "/", "Home", f"<p>{LOREM}</p>", links=[f"http://elsewhere.test:{site.port}/x", "/a"]
        )
        site.page("/a", "A", f"<p>Alpha. {LOREM}</p>")
        site.page("/x", "X", f"<p>Elsewhere. {LOREM}</p>")

        pages, _ = crawl_all(site, CrawlConfig(site.base + "/", delay_seconds=0))

        assert {p.url.removeprefix(site.base) for p in pages} == {"/", "/a"}


def test_noindex_pages_and_low_content_and_non_html_are_skipped() -> None:
    with serve() as site:
        site.routes["/"] = (
            200,
            {"Content-Type": "text/html"},
            html_page(
                "Home", f"<p>{LOREM}</p>", links=["/noindex", "/tiny", "/doc.pdf", "/missing"]
            ),
        )
        site.routes["/noindex"] = (
            200,
            {"Content-Type": "text/html"},
            html_page(
                "N", f"<p>{LOREM} noindex</p>", head='<meta name="robots" content="noindex">'
            ),
        )
        site.page("/tiny", "Tiny", "<p>Hi.</p>")
        site.routes["/doc.pdf"] = (200, {"Content-Type": "application/pdf"}, b"%PDF-1.4 ...")

        pages, stats = crawl_all(site, CrawlConfig(site.base + "/", delay_seconds=0))

        assert [p.url.removeprefix(site.base) for p in pages] == ["/"]
        assert (stats.noindex, stats.low_content, stats.unsupported_type, stats.errors) == (
            1,
            1,
            1,
            1,
        )


def test_robots_unreachable_refuses_the_crawl_but_missing_robots_allows_it() -> None:
    with serve() as site:
        site.page("/", "Home", f"<p>{LOREM}</p>")
        pages, _ = crawl_all(site, CrawlConfig(site.base + "/", delay_seconds=0))  # robots 404
        assert len(pages) == 1

        site.routes["/robots.txt"] = (503, {}, b"")
        with pytest.raises(TransientIngestionError):
            crawl_all(site, CrawlConfig(site.base + "/", delay_seconds=0))


def test_crawl_delay_from_robots_is_applied() -> None:
    with serve() as site:
        site.text("/robots.txt", "User-agent: *\nCrawl-delay: 3\n")
        site.page("/", "Home", f"<p>{LOREM}</p>", links=["/a"])
        site.page("/a", "A", f"<p>Alpha. {LOREM}</p>")
        sleeps: list[float] = []

        stats = CrawlStats()
        list(
            crawl(
                site.fetcher(),
                CrawlConfig(site.base + "/", delay_seconds=0.5),
                stats,
                sleep=sleeps.append,
            )
        )

        assert sleeps == [3.0]


def test_crawl_of_a_forbidden_start_url_fails_and_later_blocked_links_are_skipped() -> None:
    with serve() as site:
        site.page("/", "Home", f"<p>{LOREM}</p>", links=["/a"])
        site.page("/a", "A", f"<p>Alpha. {LOREM}</p>")
        strict = site.fetcher(ip_policy=lambda _ip: False)  # nothing is public

        with pytest.raises(BlockedDestinationError):
            list(crawl(strict, CrawlConfig(site.base + "/", delay_seconds=0), CrawlStats()))
        assert site.requests == []  # blocked before any request was made


def test_a_failing_start_page_raises_but_a_failing_inner_page_does_not() -> None:
    with serve() as site:
        site.page("/", "Home", f"<p>{LOREM}</p>", links=["/gone", "/a"])
        site.page("/a", "A", f"<p>Alpha. {LOREM}</p>")

        pages, stats = crawl_all(site, CrawlConfig(site.base + "/", delay_seconds=0))
        assert (
            len(pages) == 2
            and stats.errors == 1
            and stats.error_samples == ["fetch_failed: HTTP 404"]
        )

        with pytest.raises(IngestionError):
            crawl_all(site, CrawlConfig(site.base + "/nope", delay_seconds=0))
