# ASC SKU Tools

批量创建 App Store Connect 自动续期订阅 SKU。每个 App 一份 JSON 目录。

**不要提交** `AuthKey_*.p8`、`.env` 或任何 App Store Connect 私钥。密钥只留在各自电脑上。

## 下载

打好的安装包在仓库右侧 **Releases**：

https://github.com/Kejiasir/asc-sku-tools/releases

- Windows **绿色版（推荐）**：`ASC-SKU-windows-x.y.z.zip`
- Windows 安装包：`ASC-SKU-Setup-x.y.z.exe`
- macOS：`ASC-SKU-macos-x.y.z.zip`（解压后打开 `ASC SKU.app`）

Windows 同事若安装包报「拒绝访问 / MoveFile code 5」，改用绿色版：把 zip 解压到桌面或「文档」，保留整个文件夹，双击其中的 `ASC SKU.exe`。不要只拷贝 exe，也不要解压/安装到 `E:\ASC SKU` 这类盘符根目录。若杀毒软件拦截，把该文件夹加入白名单。

首次启动填写 Issuer ID、Key ID 和 `.p8`。Windows 凭证存在 `%APPDATA%\ASC SKU\`，macOS 存在 `~/Library/Application Support/ASC SKU/`。

推送到 `main` 会自动打 Windows + macOS 并发布新版本。版本从 `1.0.0` 开始，每次发布最后一位加 1；到 9 则进位（`1.0.9` → `1.1.0`，`1.9.9` → `2.0.0`）。

## 批量导入 / 导出 SKU

JSON 和 Excel 使用同一套字段。导出的文件可以直接再导入。填好后在 SKU 页点「导入」，核对列表，再点「发布到 ASC」。

应用内也可点「下载模板」生成带示例数据的 JSON 或 Excel。仓库里有一份 JSON 示例：`templates/sku-import.json`。Excel 模板请用应用生成（含下拉选项和「说明」表）。

### 必填

| 字段 | JSON | Excel 表头 | 说明 |
| --- | --- | --- | --- |
| 产品 ID | `product_id` | 产品 ID | 不能有空格，对应 App Store Connect Product ID |
| 参考名称 | `reference_name` | 参考名称 | 仅开发者可见 |
| 持续时间 | `period` | 持续时间 | `ONE_WEEK` / `ONE_MONTH` / `TWO_MONTHS` / `THREE_MONTHS` / `SIX_MONTHS` / `ONE_YEAR`，或中文：1 周、1 个月、2 个月、3 个月、6 个月、1 年 |
| 美区价格 | `usd_price` | 美区价格 | 美元，例如 `6.99` |

### 选填

| 字段 | JSON | Excel 表头 | 说明 |
| --- | --- | --- | --- |
| 级别 | `group_level` | 级别 | 订阅组内排序，整数 |
| 推介优惠 | `intro` 对象，或拆开的扁平字段 | 推介优惠类型 / 推介持续时间 / 推介期数 / 推介价格 | 见下 |
| 审核备注 | `review_note` | 审核备注 | 仅审核人员可见 |
| 审核截图 | `review_screenshot` | 审核截图 | 本机 JPG/PNG 路径 |
| 状态 | `state` | 状态 | 仅导出对照，导入后不会写回 Apple |

### 推介优惠

- 无：不填 `intro`，Excel 推介优惠类型填「无」或留空
- 免费：`mode` = `FREE_TRIAL` 或「免费」；填持续时间（如 `THREE_DAYS` / 3 天）；不要填推介价格
- 提前支付：`mode` = `PAY_UP_FRONT` 或「提前支付」；填持续时间和推介价格
- 随用随付：`mode` = `PAY_AS_YOU_GO` 或「随用随付」；持续时间必须与订阅期限相同；`number_of_periods` / 推介期数 1–12；必须填推介价格

JSON 推荐写法：

```json
{
  "format": "asc-sku.subscriptions",
  "version": 1,
  "subscriptions": [
    {
      "product_id": "dj.week.1.0",
      "reference_name": "vip-week-1.0-无试用",
      "period": "ONE_WEEK",
      "usd_price": "6.99",
      "group_level": 1
    },
    {
      "product_id": "dj.month.1.1",
      "reference_name": "vip-month-1.1-前三天免费",
      "period": "ONE_MONTH",
      "usd_price": "29.99",
      "group_level": 2,
      "intro": {
        "mode": "FREE_TRIAL",
        "duration": "THREE_DAYS",
        "number_of_periods": 1
      }
    }
  ]
}
```

也接受裸 SKU 数组，或带 `subscriptions` 的完整项目 JSON。当前列表非空时，导入会询问：按产品 ID 合并，或清空后全部替换。
