#!/usr/bin/env python3
"""Download APKs from Wandoujia history pages.

Output file name format:
    package-version-year.apk

The package/version are verified by app-rename/apprename when available, with
Wandoujia HTML metadata as fallback.
"""

from __future__ import annotations

import argparse
import html
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urljoin, urlparse
from urllib.request import Request, urlopen

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126 Safari/537.36"
)

DETAIL_RE = re.compile(
    r"https?://(?:www\.)?wandoujia\.com/apps/\d+/history_v\d+"
    r"|/apps/\d+/history_v\d+"
)
APP_ID_RE = re.compile(r"/apps/(\d+)")
HISTORY_DETAIL_RE = re.compile(r"/history_v\d+/?$")
HISTORY_YEAR_RE = re.compile(r"history_y(\d{4})")
UPDATE_YEAR_RE = re.compile(r"更新时间\s*[:：]\s*(\d{4})年|history_y(\d{4})")
DATA_HREF_RE = re.compile(r"data-href=[\"']([^\"']+\.apk[^\"']*)[\"']", re.I)
HREF_APK_RE = re.compile(r"href=[\"']([^\"']+\.apk[^\"']*)[\"']", re.I)
APP_PNAME_RE = re.compile(
    r"data-(?:app-)?pname=[\"']([^\"']+)[\"']"
    r"|data-pn=[\"']([^\"']+)[\"']"
)
APP_VNAME_RE = re.compile(r"data-app-vname=[\"']v?([^\"']+)[\"']")
VERSION_TEXT_RE = re.compile(
    r"官方版本号\s*[:：]\s*<span>\s*<a[^>]*>\s*v?([^<]+)",
    re.I,
)
TITLE_RE = re.compile(
    r"<span[^>]+class=[\"']title[\"'][^>]*>(.*?)</span>|<title>(.*?)</title>",
    re.I | re.S,
)


@dataclass(frozen=True)
class ApkJob:
    """One resolved APK download task."""

    detail_url: str
    download_url: str
    package_hint: str | None
    version_hint: str | None
    year: str | None
    app_name: str | None


@dataclass(frozen=True)
class Options:
    """Runtime options shared by workers."""

    out_dir: Path
    timeout: int
    overwrite: bool
    no_app_rename: bool
    concurrency: int


def print_line(message: str) -> None:
    """Print one flushed log line."""

    print(message, flush=True)


def fetch_text(url: str, timeout: int) -> str:
    """Fetch a text page."""

    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        body = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
    return body.decode(charset, errors="replace")


def normalize_url(url: str, base_url: str) -> str:
    """Unescape and absolutize a URL."""

    return html.unescape(urljoin(base_url, url.strip()))


def unique_items(items: Iterable[str]) -> list[str]:
    """Return items in original order with duplicates removed."""

    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def first_group(match: re.Match[str] | None) -> str | None:
    """Return the first non-empty regex capture group."""

    if match is None:
        return None
    for group in match.groups():
        if group:
            return html.unescape(re.sub(r"<.*?>", "", group).strip())
    return None


def safe_name_part(value: str | None, fallback: str) -> str:
    """Make one filename segment safe."""

    text = html.unescape(value or "").strip()
    text = re.sub(r"[\\/:*?\"<>|\s]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("._-")
    return text or fallback


def clean_version(version: str | None) -> str | None:
    """Normalize a version name from HTML or app-rename."""

    if version is None:
        return None
    text = html.unescape(version).strip()
    text = text.removeprefix("v").removeprefix("V")
    text = re.sub(r"[^0-9A-Za-z._+-]+", "_", text).strip("._-+")
    return text or None


def extract_detail_urls(page_url: str, page_body: str) -> list[str]:
    """Extract all history detail page URLs.

    Wandoujia's "查看更多" button only reveals hidden <li> nodes already in the
    initial HTML. There is no extra paging request for the observed
    history page.
    """

    urls = (
        normalize_url(match.group(0), page_url)
        for match in DETAIL_RE.finditer(page_body)
    )
    return unique_items(urls)


def extract_package(page_body: str) -> str | None:
    """Extract package name from page metadata."""

    return first_group(APP_PNAME_RE.search(page_body))


def extract_version(page_body: str) -> str | None:
    """Extract version name from page metadata."""

    version = first_group(APP_VNAME_RE.search(page_body))
    if version is None:
        version = first_group(VERSION_TEXT_RE.search(page_body))
    return clean_version(version)


def extract_year(page_body: str, page_url: str) -> str | None:
    """Extract release year from update time or history_y URL."""

    year = first_group(UPDATE_YEAR_RE.search(page_body))
    if year is not None:
        return year
    match = HISTORY_YEAR_RE.search(page_url)
    if match:
        return match.group(1)
    return None


def extract_app_name(page_body: str) -> str | None:
    """Extract the app display name, mostly for future logs."""

    title = first_group(TITLE_RE.search(page_body))
    if title is None:
        return None
    title = re.sub(r"[_-].*$", "", title).strip()
    return title or None


def extract_download_url(detail_url: str, page_body: str) -> str:
    """Extract the APK URL from a Wandoujia detail page."""

    for regex in (DATA_HREF_RE, HREF_APK_RE):
        match = regex.search(page_body)
        if match:
            return normalize_url(match.group(1), detail_url)

    match = re.search(r"downloadUrl=([^\"'&]+)", page_body)
    if match:
        return html.unescape(unquote(match.group(1)))

    raise ValueError(f"no APK download URL found: {detail_url}")


def build_year_url(input_url: str, year: str | None) -> str:
    """Build /history_yYYYY URL when --year is provided."""

    if not year:
        return input_url
    match = APP_ID_RE.search(input_url)
    if match is None:
        raise ValueError("--year requires a Wandoujia /apps/<id> URL")
    return f"https://www.wandoujia.com/apps/{match.group(1)}/history_y{year}"


def resolve_one_job(detail_url: str, timeout: int) -> ApkJob:
    """Resolve one detail page into one APK job."""

    page_body = fetch_text(detail_url, timeout)
    return ApkJob(
        detail_url=detail_url,
        download_url=extract_download_url(detail_url, page_body),
        package_hint=extract_package(page_body),
        version_hint=extract_version(page_body),
        year=extract_year(page_body, detail_url),
        app_name=extract_app_name(page_body),
    )


def resolve_jobs(
    input_url: str,
    timeout: int,
    latest: bool,
    limit: int | None,
    concurrency: int,
) -> list[ApkJob]:
    """Resolve an input URL to APK download jobs."""

    page_body = fetch_text(input_url, timeout)
    parsed = urlparse(input_url)
    is_detail = HISTORY_DETAIL_RE.search(parsed.path) is not None

    if is_detail:
        detail_urls = [input_url]
    else:
        detail_urls = extract_detail_urls(input_url, page_body)

    if not detail_urls:
        try:
            return [
                ApkJob(
                    detail_url=input_url,
                    download_url=extract_download_url(input_url, page_body),
                    package_hint=extract_package(page_body),
                    version_hint=extract_version(page_body),
                    year=extract_year(page_body, input_url),
                    app_name=extract_app_name(page_body),
                )
            ]
        except ValueError as error:
            message = f"no history detail links found: {input_url}"
            raise ValueError(message) from error

    if latest:
        detail_urls = detail_urls[:1]
    if limit is not None:
        detail_urls = detail_urls[:max(0, limit)]

    if is_detail:
        return [
            ApkJob(
                detail_url=input_url,
                download_url=extract_download_url(input_url, page_body),
                package_hint=extract_package(page_body),
                version_hint=extract_version(page_body),
                year=extract_year(page_body, input_url),
                app_name=extract_app_name(page_body),
            )
        ]

    max_workers = max(1, concurrency)
    indexed_jobs: dict[int, ApkJob] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(resolve_one_job, url, timeout): index
            for index, url in enumerate(detail_urls)
        }
        for future in as_completed(futures):
            indexed_jobs[futures[future]] = future.result()

    return [indexed_jobs[index] for index in sorted(indexed_jobs)]


def download_file(
    url: str,
    destination: Path,
    timeout: int,
    progress_prefix: str,
) -> None:
    """Download a URL to a local file."""

    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Referer": "https://www.wandoujia.com/",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        total = int(response.headers.get("Content-Length") or "0")
        done = 0
        with destination.open("wb") as output:
            while True:
                chunk = response.read(1024 * 256)
                if not chunk:
                    break
                output.write(chunk)
                done += len(chunk)
                if total:
                    percent = done / total
                    print(
                        f"\r{progress_prefix} {percent:6.1%} {done}/{total}",
                        end="",
                        file=sys.stderr,
                    )
        if total:
            print(file=sys.stderr)


def find_app_rename() -> str | None:
    """Find app-rename/apprename on PATH."""

    return shutil.which("app-rename") or shutil.which("apprename")


def run_app_rename(apk_path: Path) -> tuple[Path, str | None, str | None]:
    """Run app-rename and infer package/version from its output filename."""

    tool = find_app_rename()
    if tool is None:
        return apk_path, None, None

    before = {item.resolve() for item in apk_path.parent.iterdir()}
    try:
        subprocess.run(
            [tool, str(apk_path)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        print(f"[warn] app-rename failed: {error}", file=sys.stderr)
        return apk_path, None, None

    candidates = [
        item
        for item in apk_path.parent.iterdir()
        if item.suffix.lower() in {".apk", ".xapk"}
    ]
    renamed = next(
        (
            item
            for item in candidates
            if (
                item.resolve() not in before
                or item.resolve() != apk_path.resolve()
            )
        ),
        None,
    )
    if renamed is None:
        renamed = apk_path if apk_path.exists() else candidates[0]

    match = re.match(r"(.+)_([0-9][0-9A-Za-z._+-]*)$", renamed.stem)
    if match is None:
        return renamed, None, None
    package_name = safe_name_part(match.group(1), "unknown.package")
    version = clean_version(match.group(2))
    return renamed, package_name, version


def final_path(
    out_dir: Path,
    package_name: str | None,
    version: str | None,
    year: str | None,
    overwrite: bool,
) -> Path:
    """Build a unique final APK path."""

    name = "{}-{}-{}.apk".format(
        safe_name_part(package_name, "unknown.package"),
        safe_name_part(version, "unknown_version"),
        safe_name_part(year, "unknown_year"),
    )
    path = out_dir / name
    if overwrite or not path.exists():
        return path

    index = 1
    while True:
        candidate = out_dir / f"{path.stem}__{index}{path.suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def download_job(index: int, job: ApkJob, options: Options) -> Path:
    """Download and rename one APK."""

    options.out_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"[{index}]"
    print_line(f"{prefix} {job.detail_url}")
    print_line(f"    download: {job.download_url}")

    with tempfile.TemporaryDirectory(prefix="wdj-apk-") as temp_dir:
        temp_path = Path(temp_dir) / "download.apk"
        progress_prefix = f"{prefix} download"
        download_file(
            job.download_url,
            temp_path,
            options.timeout,
            progress_prefix,
        )

        package_name = job.package_hint
        version = job.version_hint
        source_path = temp_path
        if not options.no_app_rename:
            rename_result = run_app_rename(temp_path)
            source_path, package_from_apk, version_from_apk = rename_result
            package_name = package_from_apk or package_name
            version = version_from_apk or version

        destination = final_path(
            options.out_dir,
            package_name,
            version,
            job.year,
            options.overwrite,
        )
        if destination.exists() and options.overwrite:
            destination.unlink()
        shutil.move(str(source_path), destination)
        print_line(f"    saved: {destination}")
        return destination


def download_jobs(jobs: list[ApkJob], options: Options) -> list[Path]:
    """Download jobs concurrently and return paths in job order."""

    indexed_paths: dict[int, Path] = {}
    max_workers = max(1, options.concurrency)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(download_job, index, job, options): index
            for index, job in enumerate(jobs, 1)
        }
        for future in as_completed(futures):
            indexed_paths[futures[future]] = future.result()
    return [indexed_paths[index] for index in sorted(indexed_paths)]


def print_dry_run(jobs: list[ApkJob]) -> None:
    """Print resolved jobs without downloading files."""

    for index, job in enumerate(jobs, 1):
        package_name = job.package_hint or "<app-rename>"
        version = job.version_hint or "<app-rename>"
        year = job.year or "unknown_year"
        print_line(f"[{index}] detail:   {job.detail_url}")
        print_line(f"    download: {job.download_url}")
        print_line(f"    name:     {package_name}-{version}-{year}.apk")


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse command line arguments."""

    parser = argparse.ArgumentParser(
        description="Download Wandoujia APKs as package-version-year.apk",
    )
    parser.add_argument(
        "url",
        help="Wandoujia /history, /history_yYYYY, or /history_vNNNNN URL",
    )
    parser.add_argument(
        "-o",
        "--out-dir",
        default=".",
        help="output directory, default: current directory",
    )
    parser.add_argument(
        "--year",
        help="force a year page, e.g. --year 2026",
    )
    parser.add_argument(
        "--latest",
        action="store_true",
        help="only download the first/latest version found",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="maximum number of versions to process",
    )
    parser.add_argument(
        "-c",
        "--concurrency",
        type=int,
        default=4,
        help="concurrent detail/download workers, default: 4",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print resolved URLs and target names without downloading",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="overwrite an existing output file",
    )
    parser.add_argument(
        "--no-app-rename",
        action="store_true",
        help="skip app-rename/apprename and use HTML metadata only",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="HTTP timeout in seconds, default: 30",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""

    args = parse_args(argv)
    try:
        input_url = build_year_url(args.url, args.year)
        jobs = resolve_jobs(
            input_url=input_url,
            timeout=args.timeout,
            latest=args.latest,
            limit=args.limit,
            concurrency=args.concurrency,
        )
        if args.dry_run:
            print_dry_run(jobs)
            return 0

        options = Options(
            out_dir=Path(args.out_dir),
            timeout=args.timeout,
            overwrite=args.overwrite,
            no_app_rename=args.no_app_rename,
            concurrency=args.concurrency,
        )
        saved_paths = download_jobs(jobs, options)
        print_line("\nDone:")
        for path in saved_paths:
            print_line(str(path))
        return 0
    except (ValueError, HTTPError, URLError, TimeoutError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
