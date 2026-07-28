# wandoujia-downloader

豌豆荚历史 APK 获取工具。支持按应用名、包名、App ID 或豌豆荚链接查找应用，
列出历史版本，并在下载时校验来源声明的 size / MD5、本地 SHA-256、ZIP 结构和
`AndroidManifest.xml`。可选调用显式指定的 `aapt2`，复核 APK 内部 package 与
versionCode。

项目保留原来的 URL 直调方式，同时提供稳定的三段式 CLI：

```text
search -> list -> download
```

## 能力边界

- 数据来源是公开的豌豆荚 Web 页面及其 25PP CDN，不需要账号、Cookie 或 API key。
- 历史页面中的“查看更多”只是展开初始 HTML 已包含的条目，不需要浏览器自动化。
- 来源页当前给出 `size`、`md5`、`crc32`、`minSDK` 和 versionCode；下载器会核对
  size / MD5，并额外计算 SHA-256。
- 默认只允许 HTTPS 豌豆荚页面，以及 `pp.cn` / `25pp.com` APK CDN；CDN 变更时
  必须显式增加 `--allow-download-host`，不会静默跟随到任意域名。
- 来源完整性不等于发布者真实性。逆向前仍应记录签名证书并与可信版本比较。
- 豌豆荚页面或 CDN 改版后，解析可能失效；错误会返回非零退出码，不会把 HTML
  错页保存成 APK。

## 安装与运行

Python 3.10+：

```bash
python -m pip install -e .
wandoujia-downloader --help
```

也可直接运行 checkout，不需要 editable install：

```bash
python wandoujia_downloader.py --help
```

依赖只有 `aiohttp>=3.10,<4`。下载器默认读取 `HTTP_PROXY` / `HTTPS_PROXY` 等
标准环境变量；不希望读取时使用 `--no-trust-env`。

## 1. 搜索应用

```bash
python wandoujia_downloader.py search "微信"
python wandoujia_downloader.py search "com.tencent.mm" --json
```

搜索结果包含 App ID、包名、当前 versionName / versionCode 和规范 App URL。
精确包名通过豌豆荚 `/apps/<package>` 的服务端重定向闭环解析，不依赖模糊搜索顺序；
名称搜索会读取站内 JSON 分页，但最多处理 10 页。后续命令若名称不唯一，会拒绝
猜测并要求 `--select N`。

## 2. 列出历史版本

```bash
python wandoujia_downloader.py list "com.tencent.mm" --latest --json
python wandoujia_downloader.py list 596157 --year 2025 --limit 10
python wandoujia_downloader.py list 596157 --version-code 3120
```

默认输出会遮蔽 download URL 中的 `did` / token / sign 类查询值，同时保留 size、
MD5、minSDK 等可复核字段。只有明确使用 `--show-download-urls` 才输出完整 URL。

## 3. 下载并验证

```bash
python wandoujia_downloader.py download "com.tencent.mm" \
  --version-code 3120 \
  --out-dir ./apks \
  --manifest ./apks/wandoujia-manifest.json
```

`reverse_ENV` 内优先使用路径受控 wrapper：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File `
  "D:\reverse_ENV\skill\apk-reverse\scripts\fetch-wandoujia.ps1" `
  -Project "wechat-old" -Target "com.tencent.mm" `
  -Action Download -VersionCode "3120"
```

wrapper 固定输出到项目 `samples\wandoujia`、使用项目 `.venv` 和 build-tools 35.0.0
`aapt2`，并禁止无 selector 下载；全量下载必须显式 `-All`。独立 checkout 也可直接调用：

```powershell
& "D:\reverse_ENV\.venv\Scripts\python.exe" `
  "D:\reverse_ENV\tools\wandoujia-downloader\wandoujia_downloader.py" `
  download "com.tencent.mm" --version-code 3120 `
  --out-dir "D:\reverse_ENV\workspace\wechat-old\samples\wandoujia" `
  --manifest "D:\reverse_ENV\workspace\wechat-old\samples\wandoujia\wandoujia-manifest.json" `
  --aapt2 "D:\reverse_ENV\tools\android-sdk\build-tools\35.0.0\aapt2.exe"
```

输出文件名包含包名、versionName、versionCode 和完整发布日期，避免同一年多个版本
互相覆盖：

```text
com.tencent.mm-8.0.74-3120-20260612.apk
```

写入流程为同目录 `.part` -> 完整性校验 -> 原子替换。目标已存在且未指定
`--overwrite` 时，会重新校验现有文件；不匹配会失败，不会生成含糊的 `__1` 副本。

### 批量下载

不加 `--latest`、`--limit`、`--version` 或 `--version-code` 会处理页面内全部可解析
版本，可能产生大量请求与磁盘占用。自动化任务应先执行 `list`，再显式限定范围。

### Manifest

默认写入 `OUT_DIR/wandoujia-manifest.json`，schema 为
`wandoujia-downloader.manifest.v1`，定义见
[`schemas/manifest-v1.schema.json`](schemas/manifest-v1.schema.json)。每个 artifact 包含：

- 来源 detail URL、脱敏 download URL 和完整 URL SHA-256；
- 来源声明 size / MD5；
- 本地 size / MD5 / SHA-256；
- ZIP / manifest 校验状态；
- 页面元数据或 `aapt2` 实测 package、versionName、versionCode；
- `saved | existing | failed` 状态与失败原因。

退出码：

| 退出码 | 含义 |
|---:|---|
| `0` | 所有请求均已保存或命中通过校验的现有文件 |
| `2` | 输入、解析、网络或全部下载失败 |
| `3` | 批量任务部分成功、部分失败 |

## 兼容旧调用

原来的 URL 直调仍映射到 `download`：

```bash
python wandoujia_downloader.py \
  "https://www.wandoujia.com/apps/596157/history" \
  --dry-run --limit 5
```

## 开发

```bash
python -m unittest discover -s tests -p "test_*.py" -v
python -m py_compile wandoujia_downloader.py src/wandoujia_downloader/*.py
```

单元测试只使用合成 HTML / APK，不下载真实样本。真实 smoke 应只取受限版本，并把
APK、manifest 和日志写到仓库外或被忽略的 workspace。

## 上游与许可证状态

本仓库 fork 自
[`LunFengChen/wandoujia-downloader`](https://github.com/LunFengChen/wandoujia-downloader)。
截至 2026-07-28，上游没有声明开源许可证；本 fork 不擅自给上游代码补许可证。
完整研究、同类项目对比和复用边界见
[`docs/upstream-audit-2026-07-28.md`](docs/upstream-audit-2026-07-28.md) 与
[`NOTICE.md`](NOTICE.md)。
