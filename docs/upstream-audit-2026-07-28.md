# Upstream and solution audit - 2026-07-28

## Local problem profile

`reverse_ENV` needs a repeatable way to locate and acquire historical Android APKs before
the normal fingerprint/decode workflow. The acquisition layer must keep raw APKs under a
project workspace, record provenance, fail closed on HTML/error pages, and expose
versionCode plus cryptographic hashes for later version diffing.

The selected upstream was created on 2026-07-27 and contained one 16 KiB Python script and
a README. It already parsed Wandoujia history detail pages and used `aiohttp`, but it had no
search command, tests, package metadata, atomic writes, bounded byte ceiling, hash/ZIP
validation, evidence manifest, strict failure status, or declared license.

## Search path

- Multi-source queries: `wandoujia downloader historical APK GitHub`,
  `豌豆荚 历史版本 APK 下载 API GitHub`, and
  `Android historical APK version downloader open source`.
- Sources: search-layer Exa + Tavily results, followed by GitHub repository/code search,
  repository metadata, commit history, and source reads with `gh`.
- The research was intentionally single-agent: one exact Wandoujia candidate existed and
  the decisive evidence required local live endpoint verification rather than duplicated
  repository discovery.

## Candidate comparison

Metadata was observed on 2026-07-28 and will naturally change.

| Project | Stars / forks | Language / license | Fit and decision |
|---|---:|---|---|
| [`LunFengChen/wandoujia-downloader`](https://github.com/LunFengChen/wandoujia-downloader) | 1 / 1 | Python / undeclared | Exact Wandoujia historical-page flow; selected as the source-specific base. |
| [`EFForg/apkeep`](https://github.com/EFForg/apkeep) | 1,974 / 151 | Rust / MIT | Mature multi-source downloader and version-selection reference; not Wandoujia-specific. |
| [`TheQmaks/justapk`](https://github.com/TheQmaks/justapk) | 79 / 7 | Python / MIT | Useful source abstraction/fallback and hash-oriented reference; no Wandoujia source. |
| [`MuhammadKhizerJaved/PlayRetrieve`](https://github.com/MuhammadKhizerJaved/PlayRetrieve) | 16 / 6 | Python / MIT | Historical Google Play/split APK workflow; different provider and API dependency. |
| [`rdtoy/wandoujia-download`](https://github.com/rdtoy/wandoujia-download) | low activity | userscript / undeclared | Old browser userscript proving history-link feasibility; too stale for the maintained CLI. |

The fork keeps the exact source flow and adopts only the general operational patterns:
explicit version selection, bounded work, source provenance, integrity checks, and
machine-readable results. It does not copy code from the comparison projects.

## Live protocol evidence

Real anonymous requests on 2026-07-28 established:

- `GET https://www.wandoujia.com/search?key=微信` returns server-rendered cards with
  `data-app-id`, `data-app-pname`, `data-app-vname`, and `data-app-vcode`.
- `GET /wdjweb/api/search/more?page=<n>&key=<query>` returns JSON `data.content` and
  `data.totalPage`; name searches now consume at most 10 pages and deduplicate App IDs.
- A full three-page search for `com.tencent.mm` did not return the exact package. The
  stable exact path is `GET /apps/com.tencent.mm`, which redirected to `/apps/596157`;
  the canonical page confirmed package `com.tencent.mm`, version `8.0.76`, and
  versionCode `3140`. Package targets therefore fail closed through this alias rather
  than guessing from similar search results.
- `GET https://www.wandoujia.com/apps/596157/history` returned 143 unique historical
  detail links for the tested WeChat page.
- A tested detail page exposed version `8.0.74`, versionCode `3120`, release time,
  `size=261152116`, MD5, CRC32, minSDK, and an HTTPS `android-apps.pp.cn` APK URL.
- A 1 KiB Range request redirected to `ucdl.25pp.com`, returned HTTP 206 with
  `application/vnd.android.package-archive`, advertised the same full size, and began
  with ZIP magic `PK 03 04`.
- A bounded full-download smoke used app ID `7702159`, package `com.polaris.ruler`, and
  versionCode `332318`: 8,074,740 bytes matched source MD5, local SHA-256 was recorded,
  ZIP/`AndroidManifest.xml` passed, and build-tools 35.0.0 `aapt2` confirmed package and
  versionCode. A second run reused the validated local APK as `existing`.

These observations justify current parsers and allowlists. They are fixtures, not a promise
that Wandoujia will retain the same contract.

## Adopted boundaries

- Input pages: HTTPS and Wandoujia app/search hosts only.
- APK redirects: HTTPS and `pp.cn` / `25pp.com` by default; changes require an explicit
  domain override and a new live gate.
- Output: same-directory `.part`, byte ceiling, size/MD5 parity, SHA-256, ZIP central
  directory, `AndroidManifest.xml`, optional `aapt2` package/versionCode parity, then
  atomic replace.
- Evidence: token-like query values redacted, complete URL represented by SHA-256, and
  each artifact assigned `saved`, `existing`, or `failed`.
- Authenticity: source parity is not signer authenticity; downstream APK analysis must
  still capture and compare signing certificates.

## Remaining risks

1. Upstream licensing is undeclared; preserve the fork relationship and seek clarification
   before broader redistribution.
2. Wandoujia HTML/CDN contracts are unofficial and may change without notice.
3. Some applications or historical entries may be absent, removed, region-limited, or
   served only as a universal APK; this tool does not synthesize missing splits.
4. Multi-source fallback is deliberately out of scope for 0.2.0. `apkeep` or another
   source can be added later behind a provider-neutral acquisition interface, but source
   provenance must remain explicit rather than silently mixing catalogs.
