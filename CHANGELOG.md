# Changelog

## 0.2.0 - 2026-07-28

- Add app-name search, bounded JSON pagination, exact package-alias resolution, and
  explicit ambiguous-result selection.
- Add `search`, `list`, and `download` subcommands while preserving URL compatibility.
- Parse versionCode, full release time, size, MD5, CRC32, and minSDK from source pages.
- Add bounded retries/concurrency, HTTPS/host gates, byte ceilings, and atomic writes.
- Validate source size/MD5, local SHA-256, ZIP structure, Android manifest, and optional
  `aapt2` package/versionCode parity.
- Add sanitized evidence manifests, explicit partial-failure exit status, and 31 unit
  tests.
