# ASC SKU Tools

批量创建 App Store Connect 自动续期订阅 SKU。每个 App 一份 JSON 目录。

**不要提交** `AuthKey_*.p8`、`.env` 或任何 App Store Connect 私钥。密钥只留在各自电脑上。

## 下载

打好的安装包在仓库右侧 **Releases**：

https://github.com/Kejiasir/asc-sku-tools/releases

- Windows 安装包：`ASC-SKU-Setup-x.y.z.exe`
- Windows 绿色版：`ASC-SKU-windows-x.y.z.zip`
- macOS：`ASC-SKU-macos-x.y.z.zip`（解压后打开 `ASC SKU.app`）

首次启动填写 Issuer ID、Key ID 和 `.p8`。Windows 凭证存在 `%APPDATA%\ASC SKU\`，macOS 存在 `~/Library/Application Support/ASC SKU/`。

推送到 `main` 会自动打 Windows + macOS 并发布新版本。版本从 `1.0.0` 开始，每次发布最后一位加 1；到 9 则进位（`1.0.9` → `1.1.0`，`1.9.9` → `2.0.0`）。
