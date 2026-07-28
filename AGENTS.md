# Repository instructions

- Use UTF-8 and LF for text files.
- Keep the checkout-compatible `wandoujia_downloader.py` entrypoint working.
- Keep parsing helpers pure and cover source HTML changes with synthetic fixtures.
- Network retries, concurrency, and file sizes must remain bounded.
- Downloads must use an adjacent `.part` file and pass integrity checks before replace.
- Never commit APKs, full download URLs containing token-like query values, credentials,
  cookies, proxy secrets, or user browser data.
- Real network tests are opt-in smoke tests; unit tests must not depend on Wandoujia uptime.
- Upstream has no declared license as of 2026-07-28. Do not add a license that claims
  rights over upstream code without the original author's confirmation.
