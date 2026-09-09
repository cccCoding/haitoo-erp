from functools import lru_cache
from io import BytesIO
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter


TEMPLATE_PATH = Path(__file__).parent / "resources" / "tiktok_seller_batch_upload_v5_0_2.xlsx"
DATA_START_ROW = 7
DATA_END_ROW = 5000
ATTRIBUTE_START_COLUMN = 29  # AC
ATTRIBUTE_END_COLUMN = 42  # AP


def _clean(value) -> str:
    return str(value or "").strip()


@lru_cache(maxsize=1)
def listing_options() -> dict:
    workbook = load_workbook(TEMPLATE_PATH, data_only=False, read_only=False)
    category_sheet = workbook["Category"]
    template_sheet = workbook["Template"]
    style_sheet = workbook["HiddenStyle"]
    attribute_sheet = workbook["HiddenAttr"]

    categories = [
        {"name": _clean(category_sheet.cell(row, 1).value), "id": category_sheet.cell(row, 2).value}
        for row in range(1, category_sheet.max_row + 1)
        if _clean(category_sheet.cell(row, 1).value)
    ]
    category_rows = {
        _clean(style_sheet.cell(row, 1).value): row
        for row in range(1, style_sheet.max_row + 1)
        if _clean(style_sheet.cell(row, 1).value)
    }
    attributes_by_category: dict[str, list[dict]] = {}
    for category in categories:
        category_name = category["name"]
        style_row = category_rows.get(category_name)
        fields = []
        if style_row is None:
            attributes_by_category[category_name] = fields
            continue
        for column in range(ATTRIBUTE_START_COLUMN, ATTRIBUTE_END_COLUMN + 1):
            status = _clean(style_sheet.cell(style_row, column).value)
            if not status or status == "Forbid":
                continue
            field = _clean(template_sheet.cell(1, column).value)
            label = _clean(template_sheet.cell(3, column).value)
            description = _clean(template_sheet.cell(5, column).value)
            options = []
            if column < ATTRIBUTE_END_COLUMN:
                key_column = 1 + (column - ATTRIBUTE_START_COLUMN) * 2
                value_column = key_column + 1
                options = [
                    _clean(attribute_sheet.cell(row, value_column).value)
                    for row in range(1, attribute_sheet.max_row + 1)
                    if _clean(attribute_sheet.cell(row, key_column).value) == category_name
                    and _clean(attribute_sheet.cell(row, value_column).value)
                ]
            fields.append({
                "field": field,
                "column": get_column_letter(column),
                "label": label,
                "required": status == "Mandatory",
                "options": list(dict.fromkeys(options)),
                "allow_custom": "custom value" in description.lower(),
                "input_type": "url" if field.startswith("qualification/") else "select",
            })
        attributes_by_category[category_name] = fields

    return {
        "template_version": _clean(template_sheet["A2"].value),
        "categories": categories,
        "attributes_by_category": attributes_by_category,
        "cod_options": ["Y", "N"],
    }


def category_attributes(category: str) -> list[dict]:
    options = listing_options()
    if category not in options["attributes_by_category"]:
        raise ValueError("TikTok 类目不存在，请重新选择")
    return options["attributes_by_category"][category]


def validate_attributes(category: str, attributes: dict[str, str]) -> dict[str, str]:
    fields = {item["field"]: item for item in category_attributes(category)}
    cleaned = {key: _clean(value) for key, value in attributes.items() if _clean(value)}
    unknown = sorted(set(cleaned) - set(fields))
    if unknown:
        raise ValueError(f"所选类目不支持属性：{', '.join(unknown)}")
    for key, value in cleaned.items():
        field = fields[key]
        if len(value) > 500:
            raise ValueError(f"{field['label']} 不能超过 500 个字符")
        if field["input_type"] == "url" and not value.lower().startswith(("http://", "https://")):
            raise ValueError(f"{field['label']} 必须填写 http:// 或 https:// 开头的 URL")
        if field["options"] and not field["allow_custom"] and value not in field["options"]:
            raise ValueError(f"{field['label']} 必须从模板选项中选择")
    missing = [item["label"] for item in fields.values() if item["required"] and not cleaned.get(item["field"])]
    if missing:
        raise ValueError(f"请填写必填类目属性：{', '.join(missing)}")
    return cleaned


def build_workbook(*, template, category: str, description: str, default_price: float, cod: str | None,
                   attributes: dict[str, str], products: list[dict]) -> bytes:
    workbook = load_workbook(TEMPLATE_PATH, data_only=False, read_only=False)
    sheet = workbook["Template"]
    for row in sheet.iter_rows(min_row=DATA_START_ROW, max_row=min(sheet.max_row, DATA_END_ROW), min_col=1, max_col=42):
        for cell in row:
            cell.value = None

    sizes = [
        _clean(size)
        for size in ((template.sku_specifications or {}).get("size", {}).get("options", []))
        if _clean(size)
    ]
    row_number = DATA_START_ROW
    attribute_columns = {
        _clean(sheet.cell(1, column).value): column
        for column in range(ATTRIBUTE_START_COLUMN, ATTRIBUTE_END_COLUMN + 1)
    }
    weight_grams = round(float(template.package_weight) * 1000, 3)
    for product in products:
        main_image = product["assets"][0].url
        price = product.get("price_override") or default_price
        for asset in product["assets"]:
            for size in sizes:
                if row_number > DATA_END_ROW:
                    raise ValueError("导出数据超过 TikTok 模板 5000 行限制")
                seller_sku = f"{asset.sku}-{size}"
                values = {
                    1: category,
                    2: None,
                    3: product["title"],
                    4: description,
                    5: main_image,
                    14: "Color",
                    15: asset.sku,
                    16: asset.url,
                    17: "Size",
                    18: size,
                    19: weight_grams,
                    20: template.package_length,
                    21: template.package_width,
                    22: template.package_height,
                    23: None,
                    24: price,
                    25: 999,
                    26: seller_sku,
                    27: template.size_chart_url,
                    28: cod,
                }
                for column, value in values.items():
                    sheet.cell(row_number, column).value = value
                for field, value in attributes.items():
                    sheet.cell(row_number, attribute_columns[field]).value = value
                row_number += 1

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()
