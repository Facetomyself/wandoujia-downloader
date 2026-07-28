# 变更记录

## 0.2.1 - 2026-07-28

- 完善中文 README、仓库结构说明、`reverse_ENV` wrapper 使用约束和测试门禁。
- Manifest artifact 增加来源声明 `expected_crc32` 与 `min_sdk`，补齐 schema 和测试覆盖。
- 增加 `MANIFEST.in`，确保 sdist 收录文档、schema 与协作约束文件。
- 清理 ignored 缓存文件，让 checkout 保持干净。

## 0.2.0 - 2026-07-28

- 增加应用名搜索、有界 JSON 分页、精确包名 alias 解析和歧义结果显式选择。
- 增加 `search`、`list`、`download` 三个子命令，同时保留 URL 直调兼容入口。
- 从来源页面解析 versionCode、完整更新时间、size、MD5、CRC32 和 minSDK。
- 增加有界重试/并发、HTTPS/host 门禁、字节上限和原子写入。
- 校验来源 size/MD5、本地 SHA-256、ZIP 结构、Android manifest，以及可选 `aapt2` package/versionCode 一致性。
- 增加脱敏 evidence manifest、部分失败退出码和离线单元测试。
