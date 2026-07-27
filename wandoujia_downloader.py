#!/usr/bin/env python3
"""Download APKs from Wandoujia history pages."""

import argparse
import asyncio
import html
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

import aiohttp

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126 Safari/537.36"
)

DETAIL_RE = re.compile(
    r"https?://(?:www\.)?wandoujia\.com/apps/\d+/history_v\d+"
    r"|/apps/\d+/history_v\d+"
)
APP_ID_RE = re.compile(r"/apps/(\d+)")
DETAIL_PATH_RE = re.compile(r"/history_v\d+/?$")
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


@dataclass(slots=True, frozen=True)
class ApkJob:
    """Resolved APK task."""

    detail_url: str
    download_url: str
    package_name: str | None
    version: str | None
    year: str | None
    app_name: str | None


@dataclass(slots=True, frozen=True)
class CliArgs:
    """Typed command options."""

    url: str
    out_dir: Path
    year: str | None
    latest: bool
    limit: int | None
    concurrency: int
    dry_run: bool
    overwrite: bool
    no_app_rename: bool
    timeout: int


def log(message: str) -> None:
    """Print one line immediately."""

    print(message, flush=True)


def first_group(match: re.Match[str] | None) -> str | None:
    """Return the first non-empty regex group."""

    if match is None:
        return None
    for value in match.groups():
        if value:
            text = re.sub(r"<.*?>", "", value).strip()
            return html.unescape(text)
    return None


def safe_part(value: str | None, fallback: str) -> str:
    """Make a string safe for use inside a file name."""

    text = html.unescape(value or "").strip()
    text = re.sub(r"[\\/:*?\"<>|\s]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("._-")
    return text or fallback


def clean_version(value: str | None) -> str | None:
    """Normalize version text."""

    if value is None:
        return None
    text = html.unescape(value).strip()
    text = text.removeprefix("v").removeprefix("V")
    text = re.sub(r"[^0-9A-Za-z._+-]+", "_", text).strip("._-+")
    return text or None


def unique(items: list[str]) -> list[str]:
    """Deduplicate a list while keeping order."""

    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def app_id_from_url(url: str) -> str | None:
    """Extract Wandoujia app id from URL."""

    match = APP_ID_RE.search(url)
    if match:
        return match.group(1)
    return None


def apply_year(url: str, year: str | None) -> str:
    """Build the requested year history URL."""

    if not year:
        return url
    app_id = app_id_from_url(url)
    if app_id is None:
        raise ValueError("--year needs a Wandoujia /apps/<id> URL")
    return f"https://www.wandoujia.com/apps/{app_id}/history_y{year}"


def absolute_url(value: str, base_url: str) -> str:
    """Decode and absolutize a URL."""

    return html.unescape(urljoin(base_url, value.strip()))


def detail_urls(page_url: str, page_body: str) -> list[str]:
    """Extract all history_v links.

    The tested Wandoujia "查看更多" button only reveals hidden list items that
    already exist in the first HTML response.
    """

    urls = [
        absolute_url(match.group(0), page_url)
        for match in DETAIL_RE.finditer(page_body)
    ]
    return unique(urls)


def package_name(page_body: str) -> str | None:
    """Extract package name from Wandoujia HTML."""

    return first_group(APP_PNAME_RE.search(page_body))


def version_name(page_body: str) -> str | None:
    """Extract version name from Wandoujia HTML."""

    value = first_group(APP_VNAME_RE.search(page_body))
    if value is None:
        value = first_group(VERSION_TEXT_RE.search(page_body))
    return clean_version(value)


def release_year(page_body: str, page_url: str) -> str | None:
    """Extract release year from HTML or URL."""

    value = first_group(UPDATE_YEAR_RE.search(page_body))
    if value:
        return value
    match = HISTORY_YEAR_RE.search(page_url)
    if match:
        return match.group(1)
    return None


def app_name(page_body: str) -> str | None:
    """Extract display name from HTML."""

    value = first_group(TITLE_RE.search(page_body))
    if value is None:
        return None
    value = re.sub(r"[_-].*$", "", value).strip()
    return value or None


def download_url(detail_url: str, page_body: str) -> str:
    """Extract the APK URL from a detail page."""

    for regex in (DATA_HREF_RE, HREF_APK_RE):
        match = regex.search(page_body)
        if match:
            return absolute_url(match.group(1), detail_url)

    match = re.search(r"downloadUrl=([^\"'&]+)", page_body)
    if match:
        return html.unescape(unquote(match.group(1)))

    raise ValueError(f"APK URL not found: {detail_url}")


def target_path(
    out_dir: Path,
    package_value: str | None,
    version_value: str | None,
    year_value: str | None,
) -> Path:
    """Build the canonical output path."""

    file_name = "{}-{}-{}.apk".format(
        safe_part(package_value, "unknown.package"),
        safe_part(version_value, "unknown_version"),
        safe_part(year_value, "unknown_year"),
    )
    return out_dir / file_name


def available_path(path: Path, overwrite: bool) -> Path:
    """Return path or a collision-safe variant."""

    if overwrite or not path.exists():
        return path

    index = 1
    while True:
        candidate = path.with_name(f"{path.stem}__{index}{path.suffix}")
        if not candidate.exists():
            return candidate
        index += 1


async def fetch_text(session: aiohttp.ClientSession, url: str) -> str:
    """Fetch text with aiohttp."""

    async with session.get(url) as response:
        response.raise_for_status()
        return await response.text(errors="replace")


async def resolve_detail(
    session: aiohttp.ClientSession,
    detail_url: str,
) -> ApkJob | None:
    """Resolve one detail URL to an APK job."""

    try:
        body = await fetch_text(session, detail_url)
        return ApkJob(
            detail_url=detail_url,
            download_url=download_url(detail_url, body),
            package_name=package_name(body),
            version=version_name(body),
            year=release_year(body, detail_url),
            app_name=app_name(body),
        )
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as error:
        print(f"[warn] skip detail {detail_url}: {error}", file=sys.stderr)
        return None


async def resolve_jobs(
    session: aiohttp.ClientSession,
    input_url: str,
    latest: bool,
    limit: int | None,
) -> list[ApkJob]:
    """Resolve an input URL to APK jobs."""

    body = await fetch_text(session, input_url)
    path = urlparse(input_url).path
    is_detail = DETAIL_PATH_RE.search(path) is not None

    if is_detail:
        return [
            ApkJob(
                detail_url=input_url,
                download_url=download_url(input_url, body),
                package_name=package_name(body),
                version=version_name(body),
                year=release_year(body, input_url),
                app_name=app_name(body),
            )
        ]

    urls = detail_urls(input_url, body)
    if latest:
        urls = urls[:1]
    if limit is not None:
        urls = urls[:max(0, limit)]
    if not urls:
        return [
            ApkJob(
                detail_url=input_url,
                download_url=download_url(input_url, body),
                package_name=package_name(body),
                version=version_name(body),
                year=release_year(body, input_url),
                app_name=app_name(body),
            )
        ]

    tasks = [resolve_detail(session, url) for url in urls]
    jobs = await asyncio.gather(*tasks)
    return [job for job in jobs if job is not None]


async def download_file(
    session: aiohttp.ClientSession,
    url: str,
    path: Path,
) -> None:
    """Stream one APK to disk."""

    async with session.get(url) as response:
        response.raise_for_status()
        with path.open("wb") as output:
            async for chunk in response.content.iter_chunked(1024 * 256):
                output.write(chunk)


def rename_tool() -> str | None:
    """Find app-rename or apprename."""

    return shutil.which("app-rename") or shutil.which("apprename")


async def inspect_apk(path: Path) -> tuple[Path, str | None, str | None]:
    """Run app-rename/apprename and read package/version from file name."""

    tool = rename_tool()
    if tool is None:
        return path, None, None

    before = {item.resolve() for item in path.parent.iterdir()}
    try:
        process = await asyncio.create_subprocess_exec(
            tool,
            str(path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
    except OSError as error:
        print(f"[warn] app rename failed: {error}", file=sys.stderr)
        return path, None, None
    if process.returncode != 0:
        message = stderr.decode(errors="replace").strip()
        print(f"[warn] app rename failed: {message}", file=sys.stderr)
        return path, None, None

    candidates = [
        item
        for item in path.parent.iterdir()
        if item.suffix.lower() in {".apk", ".xapk"}
    ]
    renamed = path if path.exists() else None
    for item in candidates:
        if item.resolve() not in before or item.resolve() != path.resolve():
            renamed = item
            break
    if renamed is None:
        return path, None, None

    match = re.match(r"(.+)_([0-9][0-9A-Za-z._+-]*)$", renamed.stem)
    if match is None:
        return renamed, None, None
    parsed_package = safe_part(match.group(1), "unknown.package")
    parsed_version = clean_version(match.group(2))
    return renamed, parsed_package, parsed_version


async def save_job(
    session: aiohttp.ClientSession,
    index: int,
    job: ApkJob,
    args: CliArgs,
) -> Path | None:
    """Download one job and move it to the final file name."""

    hinted_path = target_path(
        args.out_dir,
        job.package_name,
        job.version,
        job.year,
    )
    if hinted_path.exists() and not args.overwrite:
        log(f"[{index}] exists: {hinted_path}")
        return hinted_path

    log(f"[{index}] download: {job.detail_url}")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="wdj-apk-") as temp_dir:
        temp_path = Path(temp_dir) / "download.apk"
        try:
            await download_file(session, job.download_url, temp_path)
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as error:
            print(f"[warn] skip download #{index}: {error}", file=sys.stderr)
            return None

        source_path = temp_path
        package_value = job.package_name
        version_value = job.version
        if not args.no_app_rename:
            source_path, apk_package, apk_version = await inspect_apk(
                temp_path,
            )
            package_value = apk_package or package_value
            version_value = apk_version or version_value

        final_path = target_path(
            args.out_dir,
            package_value,
            version_value,
            job.year,
        )
        final_path = available_path(final_path, args.overwrite)
        if final_path.exists() and args.overwrite:
            final_path.unlink()
        shutil.move(str(source_path), final_path)
        log(f"[{index}] saved: {final_path}")
        return final_path


async def save_jobs(
    session: aiohttp.ClientSession,
    jobs: list[ApkJob],
    args: CliArgs,
) -> list[Path]:
    """Download all jobs. aiohttp connector limit controls concurrency."""

    tasks = [
        save_job(session, index, job, args)
        for index, job in enumerate(jobs, 1)
    ]
    results = await asyncio.gather(*tasks)
    return [path for path in results if path is not None]


def print_jobs(jobs: list[ApkJob]) -> None:
    """Print dry-run result."""

    for index, job in enumerate(jobs, 1):
        path = target_path(Path("."), job.package_name, job.version, job.year)
        log(f"[{index}] detail:   {job.detail_url}")
        log(f"    download: {job.download_url}")
        log(f"    name:     {path.name}")


def parse_args(argv: list[str] | None) -> CliArgs:
    """Parse CLI args."""

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
    parser.add_argument("--year", help="force a year page, e.g. --year 2026")
    parser.add_argument(
        "--latest",
        action="store_true",
        help="only process the first/latest version found",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="maximum versions to process",
    )
    parser.add_argument(
        "-c",
        "--concurrency",
        type=int,
        default=8,
        help="aiohttp connector concurrency, default: 8",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print URLs and target names without downloading",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="overwrite existing output files",
    )
    parser.add_argument(
        "--no-app-rename",
        action="store_true",
        help="skip app-rename/apprename and use HTML metadata",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="HTTP timeout seconds, default: 30",
    )
    raw = parser.parse_args(argv)
    return CliArgs(
        url=raw.url,
        out_dir=Path(raw.out_dir),
        year=raw.year,
        latest=raw.latest,
        limit=raw.limit,
        concurrency=raw.concurrency,
        dry_run=raw.dry_run,
        overwrite=raw.overwrite,
        no_app_rename=raw.no_app_rename,
        timeout=raw.timeout,
    )


async def run(args: CliArgs) -> int:
    """Run the downloader."""

    timeout = aiohttp.ClientTimeout(total=args.timeout)
    connector = aiohttp.TCPConnector(limit=max(1, args.concurrency))
    headers = {
        "User-Agent": USER_AGENT,
        "Referer": "https://www.wandoujia.com/",
    }
    async with aiohttp.ClientSession(
        connector=connector,
        timeout=timeout,
        headers=headers,
    ) as session:
        input_url = apply_year(args.url, args.year)
        jobs = await resolve_jobs(session, input_url, args.latest, args.limit)
        if args.dry_run:
            print_jobs(jobs)
            return 0

        saved_paths = await save_jobs(session, jobs, args)
        log("\nDone:")
        for path in saved_paths:
            log(str(path))
        return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""

    args = parse_args(argv)
    try:
        return asyncio.run(run(args))
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
