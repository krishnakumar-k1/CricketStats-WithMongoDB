from __future__ import annotations

import argparse
import json
import re
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.request import Request, urlopen


START_URL = "https://www.espncricinfo.com/records/decade/1990s-199"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
)
SCORECARD_PATTERNS = (
    re.compile(r"/series/.+?/scorecard/\d+"),
    re.compile(r"/series/.+?/full-scorecard"),
)
MATCH_ID_PATTERN = re.compile(r"/(?:scorecard|full-scorecard)/(\d+)|-(\d+)(?:/|$)")


@dataclass
class CrawlResult:
    start_url: str
    crawled_pages: list[str] = field(default_factory=list)
    failed_pages: list[dict[str, str]] = field(default_factory=list)
    discovered_scorecards: list[str] = field(default_factory=list)
    saved_scorecards: list[str] = field(default_factory=list)


@dataclass
class ScorecardData:
    url: str
    match_id: str | None
    title: str | None
    headings: list[str]
    tables: list[list[list[str]]]
    next_data: dict[str, Any] | None


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.title_parts: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "title":
            self._in_title = True
        if tag != "a":
            return
        attrs_dict = dict(attrs)
        href = attrs_dict.get("href")
        if href:
            self.links.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data.strip())

    @property
    def title(self) -> str | None:
        title = " ".join(part for part in self.title_parts if part)
        return title or None


class ScorecardParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.headings: list[str] = []
        self.tables: list[list[list[str]]] = []
        self._tag_stack: list[str] = []
        self._current_heading: list[str] | None = None
        self._current_table: list[list[str]] | None = None
        self._current_row: list[str] | None = None
        self._current_cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._tag_stack.append(tag)
        if tag in {"h1", "h2", "h3"}:
            self._current_heading = []
        elif tag == "table":
            self._current_table = []
        elif tag == "tr" and self._current_table is not None:
            self._current_row = []
        elif tag in {"td", "th"} and self._current_row is not None:
            self._current_cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"h1", "h2", "h3"} and self._current_heading is not None:
            text = _clean_text(" ".join(self._current_heading))
            if text:
                self.headings.append(text)
            self._current_heading = None
        elif tag in {"td", "th"} and self._current_cell is not None:
            self._current_row.append(_clean_text(" ".join(self._current_cell)))
            self._current_cell = None
        elif tag == "tr" and self._current_row is not None:
            if any(cell for cell in self._current_row):
                self._current_table.append(self._current_row)
            self._current_row = None
        elif tag == "table" and self._current_table is not None:
            if self._current_table:
                self.tables.append(self._current_table)
            self._current_table = None
        if self._tag_stack:
            self._tag_stack.pop()

    def handle_data(self, data: str) -> None:
        if self._current_cell is not None:
            self._current_cell.append(data)
        elif self._current_heading is not None:
            self._current_heading.append(data)


def crawl_scorecards(
    start_url: str,
    output_dir: Path,
    *,
    max_pages: int,
    max_depth: int,
    max_scorecards: int | None,
    delay: float,
    user_agent: str,
    cookie: str | None,
) -> CrawlResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    scorecard_dir = output_dir / "scorecards"
    scorecard_dir.mkdir(exist_ok=True)

    result = CrawlResult(start_url=start_url)
    seen_pages: set[str] = set()
    seen_scorecards: set[str] = set()
    queue: deque[tuple[str, int]] = deque([(normalize_url(start_url, start_url), 0)])

    while queue and len(result.crawled_pages) < max_pages:
        url, depth = queue.popleft()
        if url in seen_pages or depth > max_depth:
            continue
        seen_pages.add(url)

        try:
            html = fetch_url(url, user_agent=user_agent, cookie=cookie)
        except (HTTPError, URLError, TimeoutError) as exc:
            result.failed_pages.append({"url": url, "error": str(exc)})
            continue

        result.crawled_pages.append(url)
        links = extract_links(html, url)
        for link in links:
            if not is_espncricinfo_url(link):
                continue
            if is_scorecard_url(link):
                if link not in seen_scorecards:
                    seen_scorecards.add(link)
                    result.discovered_scorecards.append(link)
                    if max_scorecards is None or len(result.saved_scorecards) < max_scorecards:
                        saved_path = save_scorecard(
                            link,
                            scorecard_dir,
                            user_agent=user_agent,
                            cookie=cookie,
                        )
                        if saved_path is not None:
                            result.saved_scorecards.append(str(saved_path))
                        time.sleep(delay)
            elif depth < max_depth and should_follow_link(link):
                queue.append((link, depth + 1))
        time.sleep(delay)

    index_path = output_dir / "crawl_index.json"
    index_path.write_text(json.dumps(asdict(result), indent=2, sort_keys=True), encoding="utf-8")
    return result


def save_scorecard(
    url: str,
    scorecard_dir: Path,
    *,
    user_agent: str,
    cookie: str | None,
) -> Path | None:
    try:
        html = fetch_url(url, user_agent=user_agent, cookie=cookie)
    except (HTTPError, URLError, TimeoutError):
        return None

    link_parser = LinkParser()
    link_parser.feed(html)
    scorecard_parser = ScorecardParser()
    scorecard_parser.feed(html)
    match_id = extract_match_id(url)
    data = ScorecardData(
        url=url,
        match_id=match_id,
        title=link_parser.title,
        headings=scorecard_parser.headings,
        tables=scorecard_parser.tables,
        next_data=extract_next_data(html),
    )
    file_stem = match_id or safe_file_stem(url)
    output_path = scorecard_dir / f"{file_stem}.json"
    output_path.write_text(json.dumps(asdict(data), indent=2, sort_keys=True), encoding="utf-8")
    return output_path


def fetch_url(url: str, *, user_agent: str, cookie: str | None) -> str:
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    if cookie:
        headers["Cookie"] = cookie
    request = Request(url, headers=headers)
    with urlopen(request, timeout=30) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def extract_links(html: str, base_url: str) -> list[str]:
    parser = LinkParser()
    parser.feed(html)
    links = []
    for href in parser.links:
        link = normalize_url(base_url, href)
        if link:
            links.append(link)
    return links


def extract_next_data(html: str) -> dict[str, Any] | None:
    match = re.search(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        html,
        flags=re.DOTALL,
    )
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def extract_match_id(url: str) -> str | None:
    match = MATCH_ID_PATTERN.search(urlparse(url).path)
    if not match:
        return None
    return next(group for group in match.groups() if group)


def normalize_url(base_url: str, href: str) -> str:
    if href.startswith("mailto:") or href.startswith("javascript:"):
        return ""
    absolute = urljoin(base_url, href)
    absolute, _fragment = urldefrag(absolute)
    parsed = urlparse(absolute)
    if parsed.scheme not in {"http", "https"}:
        return ""
    return absolute


def is_espncricinfo_url(url: str) -> bool:
    return urlparse(url).netloc.endswith("espncricinfo.com")


def is_scorecard_url(url: str) -> bool:
    path = urlparse(url).path
    return any(pattern.search(path) for pattern in SCORECARD_PATTERNS)


def should_follow_link(url: str) -> bool:
    path = urlparse(url).path
    return path.startswith(("/records/", "/series/", "/ci/engine/"))


def safe_file_stem(url: str) -> str:
    stem = re.sub(r"[^a-zA-Z0-9]+", "-", urlparse(url).path).strip("-")
    return stem[-120:] or "scorecard"


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def read_cookie_file(path: Path | None) -> str | None:
    if path is None:
        return None
    return path.read_text(encoding="utf-8").strip()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Crawl ESPNcricinfo record pages and save discovered scorecards as JSON."
    )
    parser.add_argument("--start-url", default=START_URL)
    parser.add_argument("--output-dir", type=Path, default=Path("espn_scorecards"))
    parser.add_argument("--max-pages", type=int, default=100)
    parser.add_argument("--max-depth", type=int, default=2)
    parser.add_argument("--max-scorecards", type=int, default=None)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    parser.add_argument(
        "--cookie-file",
        type=Path,
        default=None,
        help="Optional file containing a browser Cookie header for ESPNcricinfo.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    result = crawl_scorecards(
        args.start_url,
        args.output_dir,
        max_pages=args.max_pages,
        max_depth=args.max_depth,
        max_scorecards=args.max_scorecards,
        delay=args.delay,
        user_agent=args.user_agent,
        cookie=read_cookie_file(args.cookie_file),
    )
    print(f"Crawled pages: {len(result.crawled_pages)}")
    print(f"Failed pages: {len(result.failed_pages)}")
    print(f"Discovered scorecards: {len(result.discovered_scorecards)}")
    print(f"Saved scorecards: {len(result.saved_scorecards)}")
    print(f"Index: {args.output_dir / 'crawl_index.json'}")
    if result.failed_pages:
        print("Failures:")
        for failed_page in result.failed_pages[:10]:
            print(f"- {failed_page['url']}: {failed_page['error']}")
        if any("403" in failed_page["error"] for failed_page in result.failed_pages):
            print(
                "ESPNcricinfo is blocking this request with HTTP 403. "
                "Open the page in your browser, copy the request Cookie header "
                "into a text file, and rerun with --cookie-file cookies.txt."
            )


if __name__ == "__main__":
    main()
