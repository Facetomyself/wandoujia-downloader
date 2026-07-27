# wandoujia-downloader

Download APK files from Wandoujia app history pages and rename them as:

```text
package-version-year.apk
```

For example:

```text
com.smile.gifmaker-14.6.20.49153-2026.apk
```

The script uses only Python standard-library modules. If `app-rename` or
`apprename` exists on `PATH`, the downloaded APK is inspected with that tool to
confirm the package name and version. If the tool is absent, Wandoujia page
metadata is used.

## Install

No Python dependencies are required.

```bash
python3 --version
```

Optional package-name verifier:

```bash
app-rename --help
# or
apprename --help
```

## Usage

Preview parsed APK URLs without downloading:

```bash
python3 wandoujia_downloader.py \
  'https://www.wandoujia.com/apps/280621/history' \
  --dry-run \
  --limit 5 \
  -c 8
```

Download every downloadable APK from the full history page:

```bash
python3 wandoujia_downloader.py \
  'https://www.wandoujia.com/apps/280621/history' \
  -o ./apks \
  -c 8
```

Download one year:

```bash
python3 wandoujia_downloader.py \
  'https://www.wandoujia.com/apps/280621/history_y2026' \
  -o ./apks \
  -c 8
```

Use a normal history URL and force a year page:

```bash
python3 wandoujia_downloader.py \
  'https://www.wandoujia.com/apps/280621/history' \
  --year 2026 \
  -o ./apks \
  -c 8
```

Download only the latest entry:

```bash
python3 wandoujia_downloader.py \
  'https://www.wandoujia.com/apps/280621/history' \
  --latest \
  -o ./apks
```

Download one detail page:

```bash
python3 wandoujia_downloader.py \
  'https://www.wandoujia.com/apps/280621/history_v49153' \
  -o ./apks
```

## Options

```text
-o, --out-dir DIR       Output directory. Default: current directory.
--year YEAR             Force /history_yYEAR from any /apps/<id> URL.
--latest                Process only the first/latest entry.
--limit N               Process at most N versions.
-c, --concurrency N     Concurrent workers. Default: 4.
--dry-run               Print resolved URLs and target names, then exit.
--overwrite             Replace an existing output file.
--no-app-rename         Use Wandoujia HTML metadata only.
--timeout SECONDS       HTTP timeout. Default: 30.
```

## About the `查看更多` button

On the tested Wandoujia `/history` pages, the `查看更多` button does not request
another API page. Hidden versions are already present in the initial HTML as
`history-list-more` items. This downloader parses all `history_v...` links from
the HTML directly, so it can collect all visible and hidden history entries
without browser automation.
