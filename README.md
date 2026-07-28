# wandoujia-downloader

`wandoujia-downloader` 是面向 `reverse_ENV` 的豌豆荚历史 APK 获取工具。它支持按应用名、包名、App ID 或豌豆荚链接查找应用，列出历史版本，并在下载时校验来源声明的 size / MD5、本地 SHA-256、ZIP 结构和 `AndroidManifest.xml`；如显式传入 `aapt2`，还会复核 APK 内部 package、versionName 与 versionCode。

核心流程保持稳定的三段式：

```text
search -> list -> download
```

## 适配结论

- 在 `D:\reverse_ENV` 内，历史 APK 获取统一通过 `skill\apk-reverse\scripts\fetch-wandoujia.ps1` 调用；该 wrapper 负责路径门禁、项目输出目录、固定 Python/aapt2 路径和全量下载门禁。
- 本仓库也可作为独立 Python CLI 使用，保留原始 URL 直调兼容入口，但独立模式不会替你创建或校验 `workspace\<项目名>`。
- APK、manifest、日志和真实网络 smoke 产物必须落在仓库外，`reverse_ENV` 默认落点为 `workspace\<project>\samples\wandoujia\`。
- 来源完整性只证明“下载文件与豌豆荚页面声明一致”，不等于发布者真实性；进入逆向流程后仍要记录签名证书并与可信版本比较。

## 功能边界

- 数据来源是公开的豌豆荚 Web 页面及 25PP CDN，不需要账号、Cookie 或 API key。
- 历史页面中的“查看更多”目前只是展开初始 HTML 已包含的条目，不需要浏览器自动化。
- 来源页当前可暴露 `size`、`md5`、`crc32`、`minSDK` 和 versionCode；下载器校验 size / MD5，并额外计算 SHA-256。
- 默认只允许 HTTPS 豌豆荚页面，以及 `pp.cn` / `25pp.com` APK CDN；CDN 变更时必须显式增加 `--allow-download-host`，不会静默跟随到任意域名。
- 豌豆荚页面或 CDN 改版后，解析可能失效；错误会返回非零退出码，不会把 HTML 错页保存成 APK。
- 单元测试只使用合成 HTML / APK，不依赖豌豆荚在线可用性。

## 仓库结构

```text
wandoujia-downloader/
├── src/wandoujia_downloader/   # CLI、异步客户端、解析器和数据模型
├── tests/                      # 纯离线 unittest 测试
├── schemas/                    # evidence manifest JSON Schema
├── docs/                       # 上游审计、同类方案和适配说明
├── AGENTS.md                   # 本仓协作约束
├── CHANGELOG.md                # 版本变更记录
├── NOTICE.md                   # 上游归属与许可证边界
├── MANIFEST.in                 # sdist 文档/schema 收录规则
├── pyproject.toml              # Python 包元数据与入口
└── wandoujia_downloader.py     # checkout 兼容入口
```

命名约定：Python 包使用下划线 `wandoujia_downloader`，仓库和 CLI 使用短横线 `wandoujia-downloader`，文档和 schema 使用小写短横线命名。

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

依赖只有 `aiohttp>=3.10,<4`。下载器默认读取 `HTTP_PROXY` / `HTTPS_PROXY` 等标准环境变量；不希望读取时使用 `--no-trust-env`。

## 1. 搜索应用

```bash
python wandoujia_downloader.py search "微信"
python wandoujia_downloader.py search "com.tencent.mm" --json
```

搜索结果包含 App ID、包名、当前 versionName / versionCode 和规范 App URL。精确包名通过豌豆荚 `/apps/<package>` 的服务端重定向闭环解析，不依赖模糊搜索顺序；名称搜索会读取站内 JSON 分页，但最多处理 10 页。后续命令若名称不唯一，会拒绝猜测并要求 `--select N`。

## 2. 列出历史版本

```bash
python wandoujia_downloader.py list "com.tencent.mm" --latest --json
python wandoujia_downloader.py list 596157 --year 2025 --limit 10
python wandoujia_downloader.py list 596157 --version-code 3120
```

默认输出会遮蔽 download URL 中的 `did` / token / sign 类查询值，同时保留 size、MD5、minSDK 等可复核字段。只有明确使用 `--show-download-urls` 才输出完整 URL。

## 3. 下载并验证

独立 CLI 示例：

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

wrapper 固定输出到项目 `samples\wandoujia`，使用项目 `.venv` 和 build-tools 35.0.0 `aapt2`，并禁止无 selector 下载；全量下载必须显式 `-All`。确需直调时，所有路径必须显式写绝对路径：

```powershell
& "D:\reverse_ENV\.venv\Scripts\python.exe" `
  "D:\reverse_ENV\tools\wandoujia-downloader\wandoujia_downloader.py" `
  download "com.tencent.mm" --version-code 3120 `
  --out-dir "D:\reverse_ENV\workspace\wechat-old\samples\wandoujia" `
  --manifest "D:\reverse_ENV\workspace\wechat-old\samples\wandoujia\wandoujia-manifest.json" `
  --aapt2 "D:\reverse_ENV\tools\android-sdk\build-tools\35.0.0\aapt2.exe"
```

输出文件名包含包名、versionName、versionCode 和完整发布日期，避免同一年多个版本互相覆盖：

```text
com.tencent.mm-8.0.74-3120-20260612.apk
```

写入流程为同目录 `.part` -> 完整性校验 -> 原子替换。目标已存在且未指定 `--overwrite` 时，会重新校验现有文件；不匹配会失败，不会生成含糊的 `__1` 副本。

### 批量下载

独立 CLI 不加 `--latest`、`--limit`、`--version` 或 `--version-code` 会处理页面内全部可解析版本，可能产生大量请求与磁盘占用。自动化任务应先执行 `list`，再显式限定范围；在 `reverse_ENV` wrapper 中，全量下载必须显式传 `-All`。

### Manifest

默认写入 `OUT_DIR/wandoujia-manifest.json`，schema 为 `wandoujia-downloader.manifest.v1`，定义见 [`schemas/manifest-v1.schema.json`](schemas/manifest-v1.schema.json)。每个 artifact 包含：

- 来源 detail URL、脱敏 download URL 和完整 URL SHA-256；
- 来源声明 size / MD5 / CRC32 / minSDK；
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

## 开发与测试

推荐使用 `D:\reverse_ENV\.venv`：

```powershell
& "D:\reverse_ENV\.venv\Scripts\python.exe" -m unittest discover -s "D:\reverse_ENV\tools\wandoujia-downloader\tests" -p "test_*.py" -v
& "D:\reverse_ENV\.venv\Scripts\python.exe" -m py_compile "D:\reverse_ENV\tools\wandoujia-downloader\wandoujia_downloader.py" "D:\reverse_ENV\tools\wandoujia-downloader\src\wandoujia_downloader\cli.py" "D:\reverse_ENV\tools\wandoujia-downloader\src\wandoujia_downloader\client.py" "D:\reverse_ENV\tools\wandoujia-downloader\src\wandoujia_downloader\models.py" "D:\reverse_ENV\tools\wandoujia-downloader\src\wandoujia_downloader\parsing.py"
```

真实 smoke 必须显式 opt-in，只取受限版本，并把 APK、manifest 和日志写到仓库外或被忽略的 workspace。

## 上游与许可证状态

本仓库 fork 自 [`LunFengChen/wandoujia-downloader`](https://github.com/LunFengChen/wandoujia-downloader)。截至 2026-07-28，上游没有声明开源许可证；本 fork 不擅自给上游代码补许可证。完整研究、同类项目对比和复用边界见 [`docs/upstream-audit-2026-07-28.md`](docs/upstream-audit-2026-07-28.md) 与 [`NOTICE.md`](NOTICE.md)。
