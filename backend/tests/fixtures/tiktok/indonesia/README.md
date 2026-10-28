# 印尼 TikTok Shop 本土店测试模板

以下文件是用户提供的 2026-10-26 英文 `V5.0.2` 原始模板，仅重命名，工作簿内容未修改。用于解析、类目库上传与 Excel 导出的回归测试，不会自动导入业务数据库。

| 测试文件 | 原始文件名 | 类目数 |
| --- | --- | --- |
| `menswear_20261026.xlsx` | `印尼本土-TikTok Shop_Menswear & Underwear_20261026_template.xlsx` | 25 |
| `muslim_fashion_20261026.xlsx` | `印尼本土-TikTok Shop_Muslim Fashion_20261026_template.xlsx` | 47 |
| `womenswear_20261026.xlsx` | `印尼本土-TikTok Shop_Womenswear & Underwear_20261026_template.xlsx` | 41 |
| `bothplatforms_menswear_20261026.xlsx` | `印尼本土-Bothplatforms_Menswear & Underwear_20261026_template.xlsx` | 25 |
| `bothplatforms_muslim_fashion_20261026.xlsx` | `印尼本土-Bothplatforms_Muslim Fashion_20261026_template.xlsx` | 47 |
| `bothplatforms_womenswear_20261026.xlsx` | `印尼本土-Bothplatforms_Womenswear & Underwear_20261026_template.xlsx` | 41 |

从项目根目录运行：

```bash
cd backend
../.venv/bin/python -m unittest tests.test_tiktok_bothplatforms tests.test_tiktok_indonesia_templates tests.test_tiktok_category_catalogs tests.test_tiktok_export tests.test_tiktok_export_capacity
```
