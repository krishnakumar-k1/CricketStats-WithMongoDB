#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import asdict
from pathlib import Path
from urllib.error import HTTPError, URLError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from cricketstats.cricketarchive_wayback_crawler import (  # noqa: E402
    DEFAULT_USER_AGENT,
    LinkParser,
    ScorecardData,
    ScorecardParser,
    extract_links,
    extract_links_with_text,
    extract_scorecard_id,
    extract_scorecard_summary,
    fetch_url,
    is_cricketarchive_wayback_url,
    is_scorecard_url,
)


START_URL = (
    "https://web.archive.org/web/20150923012547/"
    "http://cricketarchive.com/Archive/Records/Test/Overall/Team/List_of_Matches.html"
)
OUTPUT_DIR = PROJECT_ROOT / "men_tests"


def pull_scorecards(
    start_url: str,
    output_dir: Path,
    *,
    max_scorecards: int | None,
    delay: float,
    retry_delay: float,
    retries: int,
    start_year: int | None,
    end_year: int | None,
    user_agent: str,
    overwrite: bool,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    html = fetch_url(start_url, user_agent=user_agent)
    scorecards = discover_scorecards(html, start_url)

    result: dict[str, object] = {
        "start_url": start_url,
        "discovered_scorecards": len(scorecards),
        "saved_scorecards": [],
        "skipped_existing": [],
        "skipped_year_filter": [],
        "failed_scorecards": [],
    }
    saved: list[str] = result["saved_scorecards"]  # type: ignore[assignment]
    skipped: list[str] = result["skipped_existing"]  # type: ignore[assignment]
    skipped_year: list[dict[str, object]] = result["skipped_year_filter"]  # type: ignore[assignment]
    failed: list[dict[str, str]] = result["failed_scorecards"]  # type: ignore[assignment]

    for scorecard in scorecards:
        url = scorecard["url"]
        listed_year = scorecard.get("season_year")
        listed_countries = str(scorecard.get("countries") or "unknown countries")
        listed_season = str(scorecard.get("season") or "unknown")
        if not season_can_match_filter(listed_season, start_year=start_year, end_year=end_year):
            skipped_year.append(
                {
                    "path": url,
                    "scorecard_id": extract_scorecard_id(url),
                    "year": listed_year,
                    "season": listed_season,
                    "countries": listed_countries,
                }
            )
            continue

        if max_scorecards is not None and len(saved) >= max_scorecards:
            break
        scorecard_id = extract_scorecard_id(url)
        if not scorecard_id:
            failed.append({"url": url, "error": "Could not extract scorecard id"})
            continue

        try:
            data = fetch_scorecard_with_retries(
                url,
                scorecard_id=scorecard_id,
                listed_year=listed_year,
                listed_countries=listed_countries,
                user_agent=user_agent,
                retries=retries,
                retry_delay=retry_delay,
            )
        except (HTTPError, URLError, TimeoutError) as exc:
            failed.append({"url": url, "error": f"Failed after {retries} tries: {exc}"})
            time.sleep(delay)
            continue

        year = extract_match_year(data.summary) or "unknown_year"
        countries = str(data.summary.get("match_title") or "unknown countries")
        if not year_matches_filter(year, start_year=start_year, end_year=end_year):
            print(
                f"Skipping year/season={year} countries={countries} scorecard={scorecard_id} "
                f"outside requested range",
                flush=True,
            )
            skipped_year.append(
                {"path": url, "scorecard_id": scorecard_id, "year": year, "countries": countries}
            )
            time.sleep(delay)
            continue
        print(
            f"Saving year/season={year} countries={countries} scorecard={scorecard_id}",
            flush=True,
        )
        year_dir = output_dir / str(year)
        year_dir.mkdir(parents=True, exist_ok=True)
        output_path = year_dir / f"{scorecard_id}.json"
        if output_path.exists() and not overwrite:
            skipped.append(str(output_path))
        else:
            output_path.write_text(
                json.dumps(asdict(data), indent=2, sort_keys=True),
                encoding="utf-8",
            )
            saved.append(str(output_path))
        time.sleep(delay)

    index_path = output_dir / "crawl_index.json"
    index_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return result


def discover_scorecard_urls(html: str, base_url: str) -> list[str]:
    seen: set[str] = set()
    scorecard_urls: list[str] = []
    for link in extract_links(html, base_url):
        if (
            is_cricketarchive_wayback_url(link)
            and is_scorecard_url(link)
            and link not in seen
        ):
            seen.add(link)
            scorecard_urls.append(link)
    return scorecard_urls


def discover_scorecards(html: str, base_url: str) -> list[dict[str, object]]:
    urls = discover_scorecard_urls(html, base_url)
    list_rows = extract_match_list_rows(html)
    scorecards: list[dict[str, object]] = []
    for index, url in enumerate(urls):
        row = list_rows[index] if index < len(list_rows) else []
        season = row[2] if len(row) > 2 else ""
        scorecards.append(
            {
                "url": url,
                "countries": row[0] if row else "",
                "ground": row[1] if len(row) > 1 else "",
                "season": season,
                "season_year": season_end_year(season),
            }
        )
    return scorecards


def extract_match_list_rows(html: str) -> list[list[str]]:
    parser = ScorecardParser()
    parser.feed(html)
    if not parser.tables:
        return []
    return max(parser.tables, key=len)


def fetch_scorecard(url: str, *, user_agent: str) -> ScorecardData:
    html = fetch_url(url, user_agent=user_agent)
    link_parser = LinkParser()
    link_parser.feed(html)
    scorecard_parser = ScorecardParser()
    scorecard_parser.feed(html)
    links = [
        {"url": link, "text": text}
        for link, text in extract_links_with_text(html, url)
        if is_cricketarchive_wayback_url(link)
    ]
    return ScorecardData(
        url=url,
        scorecard_id=extract_scorecard_id(url),
        title=link_parser.title,
        summary=extract_scorecard_summary(scorecard_parser.tables),
        headings=scorecard_parser.headings,
        tables=scorecard_parser.tables,
        notes=scorecard_parser.notes,
        links=links,
    )


def fetch_scorecard_with_retries(
    url: str,
    *,
    scorecard_id: str,
    listed_year: object,
    listed_countries: str,
    user_agent: str,
    retries: int,
    retry_delay: float,
) -> ScorecardData:
    last_exc: HTTPError | URLError | TimeoutError | None = None
    for attempt in range(1, retries + 1):
        print(
            f"Fetching year/season={listed_year or 'unknown'} countries={listed_countries} "
            f"scorecard={scorecard_id} try={attempt}/{retries}",
            flush=True,
        )
        try:
            data = fetch_scorecard(url, user_agent=user_agent)
        except (HTTPError, URLError, TimeoutError) as exc:
            last_exc = exc
            print(
                f"Failed year/season={listed_year or 'unknown'} countries={listed_countries} "
                f"scorecard={scorecard_id} "
                f"try={attempt}/{retries}: {exc}",
                flush=True,
            )
            if attempt < retries:
                time.sleep(retry_delay)
            continue

        year = extract_match_year(data.summary) or "unknown"
        countries = str(data.summary.get("match_title") or "unknown countries")
        print(
            f"Fetched year/season={year} countries={countries} "
            f"scorecard={scorecard_id} try={attempt}/{retries}",
            flush=True,
        )
        return data
    if last_exc is None:
        raise TimeoutError(f"Failed scorecard {scorecard_id}")
    raise last_exc


def extract_match_year(summary: dict[str, object]) -> int | None:
    venue = str(summary.get("venue") or "")
    years = re.findall(r"\b(?:18|19|20)\d{2}\b", venue)
    if years:
        return int(years[-1])

    scorecard_code = str(summary.get("scorecard_code") or "")
    code_year = re.search(r"\b(?:18|19|20)\d{2}\b", scorecard_code)
    if code_year:
        return int(code_year.group(0))
    return None


def season_end_year(season: str) -> int | None:
    season = season.strip()
    if not season:
        return None
    if "/" not in season:
        match = re.search(r"\b(?:18|19|20)\d{2}\b", season)
        return int(match.group(0)) if match else None
    start_text, end_text = season.split("/", 1)
    start_match = re.search(r"\b((?:18|19|20)\d{2})\b", start_text)
    end_match = re.search(r"\d{2,4}", end_text)
    if not start_match or not end_match:
        return None
    start_year = int(start_match.group(1))
    end_value = end_match.group(0)
    if len(end_value) == 4:
        return int(end_value)
    century = start_year // 100 * 100
    end_year = century + int(end_value)
    if end_year < start_year:
        end_year += 100
    return end_year


def season_can_match_filter(
    season: str, *, start_year: int | None, end_year: int | None
) -> bool:
    season_year = season_end_year(season)
    if season_year is None:
        return True
    if start_year is not None and season_year < start_year:
        return False
    if end_year is not None:
        season_start = season_start_year(season) or season_year
        if season_start > end_year:
            return False
    return True


def season_start_year(season: str) -> int | None:
    match = re.search(r"\b((?:18|19|20)\d{2})\b", season)
    return int(match.group(1)) if match else None


def year_matches_filter(
    year: int | str, *, start_year: int | None, end_year: int | None
) -> bool:
    if not isinstance(year, int):
        return start_year is None and end_year is None
    if start_year is not None and year < start_year:
        return False
    if end_year is not None and year > end_year:
        return False
    return True


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Pull men's Test scorecards from CricketArchive's archived List of Matches "
            "page and save JSON files under year subdirectories."
        )
    )
    parser.add_argument("--start-url", default=START_URL)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--max-scorecards", type=int, default=None)
    parser.add_argument(
        "--start-year",
        type=int,
        default=1995,
        help="Only save scorecards from this year onward. Default resumes at 1995.",
    )
    parser.add_argument(
        "--end-year",
        type=int,
        default=None,
        help="Only save scorecards up to this year.",
    )
    parser.add_argument("--delay", type=float, default=2.5)
    parser.add_argument("--retry-delay", type=float, default=5.0)
    parser.add_argument("--retries", type=int, default=5)
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Rewrite existing scorecard JSON files instead of skipping them.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    result = pull_scorecards(
        args.start_url,
        args.output_dir,
        max_scorecards=args.max_scorecards,
        delay=args.delay,
        retry_delay=args.retry_delay,
        retries=args.retries,
        start_year=args.start_year,
        end_year=args.end_year,
        user_agent=args.user_agent,
        overwrite=args.overwrite,
    )
    print(f"Discovered scorecards: {result['discovered_scorecards']}")
    print(f"Saved scorecards: {len(result['saved_scorecards'])}")
    print(f"Skipped existing: {len(result['skipped_existing'])}")
    print(f"Skipped by year filter: {len(result['skipped_year_filter'])}")
    print(f"Failed scorecards: {len(result['failed_scorecards'])}")
    print(f"Index: {args.output_dir / 'crawl_index.json'}")
    for failed in result["failed_scorecards"][:10]:  # type: ignore[index]
        print(f"- {failed['url']}: {failed['error']}")


if __name__ == "__main__":
    main()
