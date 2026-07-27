# wandoujia-downloader

豌豆荚历史版本 APK 下载器。输入豌豆荚 App 链接，自动解析历史版本详情页和
“普通下载”链接，并把 APK 保存为规范文件名：

```text
包名-版本号-年号.apk
```

示例：

```text
com.smile.gifmaker-14.6.20.49153-2026.apk
```

脚本本身只使用 Python 标准库。若本机 `PATH` 里存在 `app-rename` 或
`apprename`，会优先用它读取 APK 内部包名和版本号；否则使用豌豆荚页面中的
`data-app-pname` / `data-app-vname` 元数据。

`apprename` / `app-rename` 是作者主页里的 APK/XAPK 重命名工具，主页：

```text
https://github.com/LunFengChen
```

## 环境

```bash
python3 --version
```

可选检查：

```bash
app-rename --help
# 或
apprename --help
```

## CLI 使用教程

### 1. 预览解析结果，不下载

```bash
python3 wandoujia_downloader.py \
  'https://www.wandoujia.com/apps/280621/history' \
  --dry-run \
  --limit 5 \
  -c 8
```

### 2. 下载全部可解析历史 APK

```bash
python3 wandoujia_downloader.py \
  'https://www.wandoujia.com/apps/280621/history' \
  -o ./apks \
  -c 8
```

## 单个选项说明

| 选项 | 作用 | 示例 |
| --- | --- | --- |
| `url` | 必填。豌豆荚 `/history`、`/history_yYYYY` 或 `/history_vNNNNN` 链接。 | `https://www.wandoujia.com/apps/280621/history` |
| `-o, --out-dir DIR` | 指定 APK 输出目录，默认当前目录。 | `-o ./apks` |
| `--year YEAR` | 从任意 `/apps/<id>` 链接强制构造某年份页面。 | `--year 2026` |
| `--latest` | 只处理解析到的第一个版本，通常是最新历史版本。 | `--latest` |
| `--limit N` | 限制最多处理多少个历史版本。 | `--limit 10` |
| `-c, --concurrency N` | 并发解析和下载数量，默认 `4`。 | `-c 8` |
| `--dry-run` | 只打印详情页、下载链接和目标文件名，不下载 APK。 | `--dry-run` |
| `--overwrite` | 目标文件已存在时直接覆盖；默认会生成 `__1` 后缀避免覆盖。 | `--overwrite` |
| `--no-app-rename` | 跳过 `app-rename` / `apprename`，只使用页面元数据命名。 | `--no-app-rename` |
| `--timeout SECONDS` | HTTP 请求超时时间，默认 `30` 秒。 | `--timeout 60` |

## 关于“查看更多”

豌豆荚 `/history` 页面里的“查看更多”按钮并不是新的分页接口。隐藏历史版本
已经在初始 HTML 里，只是后续 `<li>` 带有 `history-list-more` 类名。脚本会
直接解析页面中的全部 `history_v...` 链接，所以无需浏览器自动化点击。
