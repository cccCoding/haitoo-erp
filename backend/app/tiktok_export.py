from functools import lru_cache
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter


TEMPLATE_PATH = Path(__file__).parent / "resources" / "tiktok_seller_batch_upload_v5_0_2.xlsx"
DATA_START_ROW = 7
DATA_END_ROW = 5000
ATTRIBUTE_START_COLUMN = 29  # AC
ATTRIBUTE_END_COLUMN = 42  # AP
BASE_FIELD_START_COLUMN = 3  # C
BASE_FIELD_END_COLUMN = 28  # AB


def _clean(value) -> str:
    return str(value or "").strip()


def _template_source(template_bytes: bytes | None = None):
    return BytesIO(template_bytes) if template_bytes is not None else TEMPLATE_PATH


def attribute_input_mode(field: dict) -> str:
    """返回属性的输入方式，并兼容尚未保存 input_mode 的旧类目库。"""
    if field.get("input_mode") in {"text", "select", "select_or_text"}:
        return field["input_mode"]
    if field.get("input_mode") in {"single", "multiple"}:
        return "select"
    if not field.get("options"):
        return "text"
    if field.get("allow_custom"):
        return "select_or_text"
    return "select"


def _preserve_template_package(generated_bytes: bytes, template_bytes: bytes | None = None) -> bytes:
    """仅替换数据工作表 XML，避免 openpyxl 丢弃说明页中的绘图和媒体。"""
    generated_stream = BytesIO(generated_bytes)
    output = BytesIO()
    with ZipFile(_template_source(template_bytes), "r") as source_zip, ZipFile(generated_stream, "r") as generated_zip, ZipFile(output, "w", ZIP_DEFLATED) as output_zip:
        generated_template_xml = generated_zip.read("xl/worksheets/sheet1.xml")
        for info in source_zip.infolist():
            content = generated_template_xml if info.filename == "xl/worksheets/sheet1.xml" else source_zip.read(info.filename)
            output_zip.writestr(info, content)
    return output.getvalue()


def parse_listing_options(template_bytes: bytes | None = None) -> dict:
    """解析 TikTok 模板中的类目、字段状态和属性选项。"""
    try:
        workbook = load_workbook(_template_source(template_bytes), data_only=False, read_only=False)
    except Exception as exc:
        raise ValueError("无法读取 TikTok XLSX 模板") from exc
    required_sheets = {"Category", "Template", "HiddenStyle", "HiddenAttr"}
    missing_sheets = sorted(required_sheets - set(workbook.sheetnames))
    if missing_sheets:
        raise ValueError(f"TikTok 模板缺少工作表：{', '.join(missing_sheets)}")
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
    base_requirements_by_category: dict[str, dict[str, str]] = {}
    for category in categories:
        category_name = category["name"]
        style_row = category_rows.get(category_name)
        fields = []
        if style_row is None:
            attributes_by_category[category_name] = fields
            base_requirements_by_category[category_name] = {}
            continue
        base_requirements_by_category[category_name] = {
            _clean(template_sheet.cell(1, column).value): _clean(style_sheet.cell(style_row, column).value)
            for column in range(BASE_FIELD_START_COLUMN, BASE_FIELD_END_COLUMN + 1)
            if _clean(style_sheet.cell(style_row, column).value)
            and _clean(style_sheet.cell(style_row, column).value) != "Forbid"
        }
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
            allow_custom = "custom value" in description.lower()
            if not options:
                input_mode = "text"
            elif allow_custom:
                input_mode = "select_or_text"
            else:
                input_mode = "select"
            fields.append({
                "field": field,
                "column": get_column_letter(column),
                "label": label,
                "status": status,
                "required": status == "Mandatory",
                "options": list(dict.fromkeys(options)),
                "allow_custom": allow_custom,
                "input_type": "url" if field.startswith("qualification/") else "select",
                "input_mode": input_mode,
            })
        attributes_by_category[category_name] = fields

    return {
        "template_version": _clean(template_sheet["A2"].value),
        "categories": categories,
        "attributes_by_category": attributes_by_category,
        "base_requirements_by_category": base_requirements_by_category,
        "cod_options": ["Y", "N"],
        "price_limits": {"min": 0.01, "max": 999999},
        "quantity_limits": {"min": 0, "max": 999999},
        "multiple_value_separator": ",",
    }


@lru_cache(maxsize=1)
def listing_options() -> dict:
    """兼容系统默认模板的只读选项。"""
    return parse_listing_options()


def category_attributes(category: str, options: dict | None = None) -> list[dict]:
    options = options or listing_options()
    if category not in options["attributes_by_category"]:
        raise ValueError("TikTok 类目不存在，请重新选择")
    return options["attributes_by_category"][category]


def category_base_requirements(category: str, options: dict | None = None) -> dict[str, str]:
    options = options or listing_options()
    if category not in options["base_requirements_by_category"]:
        raise ValueError("TikTok 类目不存在，请重新选择")
    return options["base_requirements_by_category"][category]


def validate_attributes(category: str, attributes: dict, options: dict | None = None) -> dict[str, str]:
    options = options or listing_options()
    fields = {item["field"]: item for item in category_attributes(category, options)}
    cleaned: dict[str, str] = {}
    for key, raw_value in attributes.items():
        field = fields.get(key)
        input_mode = attribute_input_mode(field) if field else "select"
        if isinstance(raw_value, list):
            values = list(dict.fromkeys(_clean(item) for item in raw_value if _clean(item)))
            if not field or input_mode != "select":
                raise ValueError(f"{field['label'] if field else key} 不支持填写多个值")
        else:
            raw_text = _clean(raw_value)
            if field and input_mode == "select":
                values = list(dict.fromkeys(_clean(item) for item in raw_text.replace("，", ",").split(",") if _clean(item)))
            else:
                values = [raw_text] if raw_text else []
        value = options.get("multiple_value_separator", ",").join(values) if field and input_mode == "select" else (values[0] if values else "")
        if value:
            cleaned[key] = value
    unknown = sorted(set(cleaned) - set(fields))
    if unknown:
        raise ValueError(f"所选类目不支持属性：{', '.join(unknown)}")
    for key, value in cleaned.items():
        field = fields[key]
        if len(value) > 500:
            raise ValueError(f"{field['label']} 不能超过 500 个字符")
        if field["input_type"] == "url" and not value.lower().startswith(("http://", "https://")):
            raise ValueError(f"{field['label']} 必须填写 http:// 或 https:// 开头的 URL")
        input_mode = attribute_input_mode(field)
        selected_values = value.split(options.get("multiple_value_separator", ",")) if input_mode == "select" else [value]
        if input_mode == "select" and field["options"] and any(item not in field["options"] for item in selected_values):
            raise ValueError(f"{field['label']} 必须从模板选项中选择")
    missing = [item["label"] for item in fields.values() if item["required"] and not cleaned.get(item["field"])]
    if missing:
        raise ValueError(f"请填写必填类目属性：{', '.join(missing)}")
    return cleaned


def build_workbook(*, template, category: str, cod: str, attributes: dict[str, str], products: list[dict], template_bytes: bytes | None = None) -> bytes:
    workbook = load_workbook(_template_source(template_bytes), data_only=False, read_only=False)
    sheet = workbook["Template"]
    for row in sheet.iter_rows(min_row=DATA_START_ROW, max_row=min(sheet.max_row, DATA_END_ROW), min_col=1, max_col=42):
        for cell in row:
            cell.value = None

    sizes = [
        _clean(size)
        for size in ((template.sku_specifications or {}).get("size", {}).get("options", []))
        if _clean(size)
    ] or ["Default"]
    row_number = DATA_START_ROW
    attribute_columns = {
        _clean(sheet.cell(1, column).value): column
        for column in range(ATTRIBUTE_START_COLUMN, ATTRIBUTE_END_COLUMN + 1)
    }
    weight_grams = round(float(template.package_weight) * 1000, 3)
    for product in products:
        image_urls = list(dict.fromkeys(product["image_urls"]))
        gallery = image_urls[:9]
        base_sku_by_image = product["base_sku_by_image"]
        for image_url in image_urls:
            base_sku = base_sku_by_image[image_url]
            for size in sizes:
                if row_number > DATA_END_ROW:
                    raise ValueError("导出数据超过 TikTok 模板 5000 行限制")
                seller_sku = base_sku if size == "Default" else f"{base_sku}-{size}"
                values = {
                    1: category,
                    2: None,
                    3: product["title"],
                    4: product["description"],
                    14: "Color",
                    15: base_sku,
                    16: image_url,
                    17: "Size",
                    18: size,
                    19: weight_grams,
                    20: template.package_length,
                    21: template.package_width,
                    22: template.package_height,
                    23: None,
                    24: product["price"],
                    25: product["quantity"],
                    26: seller_sku,
                    27: product.get("size_chart_url"),
                    28: cod,
                }
                for index, gallery_url in enumerate(gallery, start=5):
                    values[index] = gallery_url
                for column, value in values.items():
                    sheet.cell(row_number, column).value = value
                for field, value in attributes.items():
                    sheet.cell(row_number, attribute_columns[field]).value = value
                row_number += 1

    output = BytesIO()
    workbook.save(output)
    return _preserve_template_package(output.getvalue(), template_bytes)
