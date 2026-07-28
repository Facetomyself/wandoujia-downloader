# 仓库协作约束

- 文本文件统一使用 UTF-8 + LF。
- 保持 checkout 兼容入口 `wandoujia_downloader.py` 可用。
- Python 包名使用 `wandoujia_downloader`，CLI / 仓库名使用 `wandoujia-downloader`。
- 解析逻辑保持纯函数；豌豆荚 HTML 结构变化先补合成 fixture 和单元测试。
- 网络重试、并发和文件大小必须有上限；不要引入无界分页、无界下载或无限轮询。
- 下载必须写入相邻 `.part` 文件，完整性校验通过后再原子替换目标 APK。
- Manifest 默认写脱敏 URL；除非用户明确传 `--show-download-urls`，不得输出完整 token-like 查询值。
- 不得提交 APK、完整下载 URL、Cookie、凭据、代理密钥、浏览器 profile、真实下载日志或 workspace 产物。
- 真实网络测试只作为 opt-in smoke；单元测试不能依赖豌豆荚在线状态。
- 在 `reverse_ENV` 内使用时优先走 `D:\reverse_ENV\skill\apk-reverse\scripts\fetch-wandoujia.ps1`，不要绕过项目路径门禁。
- 上游截至 2026-07-28 未声明许可证；未获原作者确认前，不要添加声称覆盖上游代码的开源许可证。
