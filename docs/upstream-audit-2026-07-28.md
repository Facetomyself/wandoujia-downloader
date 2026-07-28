# 上游与方案审计 - 2026-07-28

## 本地问题画像

`reverse_ENV` 需要一个可重复的历史 APK 获取入口，用在 APK 指纹、解包和版本差分之前。获取层必须把原始 APK 固定落到项目 workspace，记录来源证据，遇到 HTML 错页或完整性不匹配时失败关闭，并输出 versionCode 与哈希，方便后续比对。

选定的上游仓库创建于 2026-07-27，当时主要是一份约 16 KiB 的 Python 脚本和 README。它已经能解析豌豆荚历史详情页并使用 `aiohttp` 下载，但缺少搜索命令、测试、包元数据、原子写入、有界文件大小、哈希/ZIP 校验、evidence manifest、严格失败状态和明确许可证。

## 搜索路径

- 多源搜索查询：`wandoujia downloader historical APK GitHub`、`豌豆荚 历史版本 APK 下载 API GitHub`、`Android historical APK version downloader open source`。
- 搜索面：`search-layer` 的 Exa + Tavily 结果，以及 GitHub 仓库/代码搜索、仓库元数据、提交历史和源码读取。
- 未使用子代理：精确 Wandoujia 候选只有一个，关键证据来自本地 live endpoint 验证，拆给子代理只会重复搜索。

## 候选对比

以下元数据观察于 2026-07-28，会随时间变化。

| 项目 | Stars / forks | 语言 / 许可证 | 适配判断 |
|---|---:|---|---|
| [`LunFengChen/wandoujia-downloader`](https://github.com/LunFengChen/wandoujia-downloader) | 1 / 1 | Python / 未声明 | 精确匹配豌豆荚历史页流程；选为 source-specific 基础。 |
| [`EFForg/apkeep`](https://github.com/EFForg/apkeep) | 1,974 / 151 | Rust / MIT | 成熟多来源下载器，可参考显式来源、版本选择和校验思路；不支持豌豆荚。 |
| [`TheQmaks/justapk`](https://github.com/TheQmaks/justapk) | 79 / 7 | Python / MIT | 可参考 source abstraction、fallback 与哈希导向流程；没有豌豆荚来源。 |
| [`MuhammadKhizerJaved/PlayRetrieve`](https://github.com/MuhammadKhizerJaved/PlayRetrieve) | 16 / 6 | Python / MIT | Google Play 历史/split APK 工作流参考；provider 和 API 依赖不同。 |
| [`rdtoy/wandoujia-download`](https://github.com/rdtoy/wandoujia-download) | 低活跃 | userscript / 未声明 | 老旧浏览器脚本，能证明历史链接可行；不适合作为维护型 CLI 基础。 |

本 fork 保留上游的豌豆荚 source flow，只吸收通用工程模式：显式版本选择、有界工作、来源证据、完整性校验和机器可读结果；没有复制候选项目代码。

## Live 协议证据

2026-07-28 的匿名真实请求确认了以下行为：

- `GET https://www.wandoujia.com/search?key=微信` 返回服务端渲染卡片，包含 `data-app-id`、`data-app-pname`、`data-app-vname` 和 `data-app-vcode`。
- `GET /wdjweb/api/search/more?page=<n>&key=<query>` 返回 JSON `data.content` 与 `data.totalPage`；名称搜索最多读取 10 页并按 App ID 去重。
- 对 `com.tencent.mm` 的三页搜索没有返回精确包名。稳定路径是 `GET /apps/com.tencent.mm`，它会重定向到 `/apps/596157`；规范页面确认 package 为 `com.tencent.mm`，version 为 `8.0.76`，versionCode 为 `3140`。因此包名目标必须走 alias 闭环，不从相似搜索结果里猜。
- `GET https://www.wandoujia.com/apps/596157/history` 在测试时返回 143 个唯一历史详情链接。
- 一个测试详情页暴露 version `8.0.74`、versionCode `3120`、更新时间、`size=261152116`、MD5、CRC32、minSDK 和 HTTPS `android-apps.pp.cn` APK URL。
- 1 KiB Range 请求重定向到 `ucdl.25pp.com`，返回 HTTP 206 与 `application/vnd.android.package-archive`，声明完整大小一致，并以 ZIP magic `PK 03 04` 开头。
- 有界完整下载 smoke 使用 app ID `7702159`、package `com.polaris.ruler`、versionCode `332318`：8,074,740 bytes 与来源 MD5 一致，本地 SHA-256 已记录，ZIP/`AndroidManifest.xml` 通过，build-tools 35.0.0 `aapt2` 确认 package 与 versionCode；第二次运行复用已校验 APK，状态为 `existing`。

这些观察支撑当前 parser 和 allowlist，但它们只是 fixture 证据，不保证豌豆荚未来保持相同契约。

## 已采纳边界

- 输入页面：只接受 HTTPS 豌豆荚 app/search host。
- APK 跳转：默认只接受 HTTPS `pp.cn` / `25pp.com`；CDN 变更必须显式增加 domain override，并补 live gate。
- 输出：同目录 `.part`、字节上限、size/MD5 一致性、SHA-256、ZIP central directory、`AndroidManifest.xml`、可选 `aapt2` package/versionCode 一致性，然后原子替换。
- 证据：token-like 查询值脱敏，完整 URL 只保留 SHA-256，artifact 状态限定为 `saved`、`existing` 或 `failed`，并记录 size/MD5/CRC32/minSDK 等来源声明字段。
- 真实性：来源一致性不是签名真实性；下游 APK 分析仍必须提取和比较签名证书。

## 剩余风险

1. 上游许可证未声明；保留 fork 关系，广泛再分发前应先获得授权确认。
2. 豌豆荚 HTML/CDN 都是非官方契约，可能无预告变化。
3. 部分应用或历史条目可能缺失、下架、区域受限，或只提供 universal APK；本工具不合成缺失 split。
4. 0.2.x 故意不做多来源 fallback。以后可以在 provider-neutral acquisition interface 后接入 `apkeep` 等来源，但来源证据必须显式，不能静默混用 catalog。
