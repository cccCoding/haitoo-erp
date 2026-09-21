from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter


TEMPLATE_PATH = Path(__file__).parent / "resources" / "tiktok_seller_batch_upload_zh_v5_0_2.xlsx"
DATA_START_ROW = 7
BASE_FIELD_START_COLUMN = 3  # C

FIELD_CATEGORY = "category"
FIELD_PRODUCT_NAME = "product_name"
FIELD_PRODUCT_DESCRIPTION = "product_description"
FIELD_MAIN_IMAGE = "main_image"
FIELD_PROPERTY_NAME_1 = "property_name_1"
FIELD_PROPERTY_VALUE_1 = "property_value_1"
FIELD_PROPERTY_1_IMAGE = "property_1_image"
FIELD_PROPERTY_NAME_2 = "property_name_2"
FIELD_PROPERTY_VALUE_2 = "property_value_2"
FIELD_PARCEL_WEIGHT = "parcel_weight"
FIELD_PARCEL_LENGTH = "parcel_length"
FIELD_PARCEL_WIDTH = "parcel_width"
FIELD_PARCEL_HEIGHT = "parcel_height"
FIELD_DELIVERY = "delivery"
FIELD_PRICE = "price"
FIELD_QUANTITY = "quantity"
FIELD_SELLER_SKU = "seller_sku"
FIELD_SIZE_CHART = "size_chart"
FIELD_COD = "cod"
FIELD_SPECIAL_PRODUCT_LISTING_TYPE = "special_product_listing_type"
FIELD_AUCTION_STARTING_PRICE = "auction_starting_price"

COMMON_REQUIRED_EXPORT_FIELDS = {
    FIELD_CATEGORY, FIELD_PRODUCT_NAME, FIELD_PRODUCT_DESCRIPTION, FIELD_MAIN_IMAGE,
    FIELD_PROPERTY_NAME_1, FIELD_PROPERTY_VALUE_1, FIELD_PROPERTY_1_IMAGE,
    FIELD_PROPERTY_NAME_2, FIELD_PROPERTY_VALUE_2, FIELD_PARCEL_WEIGHT,
    FIELD_PARCEL_LENGTH, FIELD_PARCEL_WIDTH, FIELD_PARCEL_HEIGHT,
    FIELD_PRICE, FIELD_QUANTITY, FIELD_SELLER_SKU, FIELD_SIZE_CHART,
}


@dataclass(frozen=True)
class TiktokTemplateAdapter:
    key: str
    label: str
    required_fields: frozenset[str]
    supports_cod: bool
    supports_hubstudio_submit: bool


TIKTOK_LOCAL_ADAPTER = TiktokTemplateAdapter(
    key="tiktok_local", label="tk本土店",
    required_fields=frozenset(COMMON_REQUIRED_EXPORT_FIELDS | {FIELD_DELIVERY, FIELD_COD}),
    supports_cod=True, supports_hubstudio_submit=True,
)
TIKTOK_CROSS_BORDER_ADAPTER = TiktokTemplateAdapter(
    key="tiktok_cross_border", label="tk跨境店",
    required_fields=frozenset(COMMON_REQUIRED_EXPORT_FIELDS),
    supports_cod=False, supports_hubstudio_submit=False,
)
TIKTOK_TEMPLATE_ADAPTERS = {
    TIKTOK_LOCAL_ADAPTER.key: TIKTOK_LOCAL_ADAPTER,
    TIKTOK_CROSS_BORDER_ADAPTER.key: TIKTOK_CROSS_BORDER_ADAPTER,
}


def _clean(value) -> str:
    return str(value or "").strip()


def _template_source(template_bytes: bytes | None = None):
    return BytesIO(template_bytes) if template_bytes is not None else TEMPLATE_PATH


def _field_columns(sheet) -> dict[str, int]:
    """按模板第 1 行的机器字段名定位列，避免依赖不同语言模板的固定列号。"""
    return {
        _clean(sheet.cell(1, column).value): column
        for column in range(1, sheet.max_column + 1)
        if _clean(sheet.cell(1, column).value)
    }


def _attribute_fields(sheet) -> list[tuple[int, str]]:
    """按机器字段名查找类目属性，兼容不同模板版本中的起始列。"""
    return [
        (column, field)
        for column in range(1, sheet.max_column + 1)
        if (field := _clean(sheet.cell(1, column).value)).startswith(("product_property/", "qualification/"))
    ]


def _template_version(sheet) -> str | None:
    """本土模板将版本放在 A2，跨境模板则将语言提示放在 A2、版本放在 B2。"""
    values = [_clean(sheet.cell(2, column).value) for column in range(1, sheet.max_column + 1)]
    return next((value for value in values if value.upper().startswith("V") and any(char.isdigit() for char in value)), values[0][:40] or None)


def tiktok_template_adapter(template_fields: set[str], expected_type: str | None = None) -> TiktokTemplateAdapter:
    """根据机器字段识别本土/跨境模板，并拒绝与用户选择不一致的文件。"""
    if {FIELD_DELIVERY, FIELD_COD}.issubset(template_fields):
        adapter = TIKTOK_LOCAL_ADAPTER
    elif (
        {FIELD_SPECIAL_PRODUCT_LISTING_TYPE, FIELD_AUCTION_STARTING_PRICE}.issubset(template_fields)
        or (
            COMMON_REQUIRED_EXPORT_FIELDS.issubset(template_fields)
            and FIELD_DELIVERY not in template_fields
            and FIELD_COD not in template_fields
        )
    ):
        # 新版跨境模板不再包含拍卖相关字段，属性列也可能从 AA 开始。
        adapter = TIKTOK_CROSS_BORDER_ADAPTER
    else:
        raise ValueError("无法识别 TikTok 模板类型：未找到本土店或跨境店的特征字段")
    if expected_type and adapter.key != expected_type:
        raise ValueError(f"所选{TIKTOK_TEMPLATE_ADAPTERS[expected_type].label if expected_type in TIKTOK_TEMPLATE_ADAPTERS else '店铺类型'}与上传模板不匹配，识别结果为{adapter.label}")
    return adapter


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


def parse_listing_options(template_bytes: bytes | None = None, template_type: str | None = None) -> dict:
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
    template_fields = _field_columns(template_sheet)
    adapter = tiktok_template_adapter(set(template_fields), template_type)
    missing_fields = sorted(adapter.required_fields - set(template_fields))
    if missing_fields:
        raise ValueError(f"TikTok 模板缺少导出字段：{', '.join(missing_fields)}")
    attribute_fields = _attribute_fields(template_sheet)

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
            field: _clean(style_sheet.cell(style_row, column).value)
            for column in range(BASE_FIELD_START_COLUMN, template_sheet.max_column + 1)
            if not (field := _clean(template_sheet.cell(1, column).value)).startswith(("product_property/", "qualification/"))
            and _clean(style_sheet.cell(style_row, column).value)
            and _clean(style_sheet.cell(style_row, column).value) != "Forbid"
        }
        for attribute_index, (column, field) in enumerate(attribute_fields):
            status = _clean(style_sheet.cell(style_row, column).value)
            if not status or status == "Forbid":
                continue
            label = _clean(template_sheet.cell(3, column).value)
            description = _clean(template_sheet.cell(5, column).value)
            options = []
            key_column = 1 + attribute_index * 2
            value_column = key_column + 1
            if value_column <= attribute_sheet.max_column:
                options = [
                    _clean(attribute_sheet.cell(row, value_column).value)
                    for row in range(1, attribute_sheet.max_row + 1)
                    if _clean(attribute_sheet.cell(row, key_column).value) == category_name
                    and _clean(attribute_sheet.cell(row, value_column).value)
                ]
            allow_custom = "custom value" in description.lower() or "输入自定义值" in description
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
        "template_version": _template_version(template_sheet),
        "template_type": adapter.key,
        "template_type_label": adapter.label,
        "capabilities": {
            "supports_cod": adapter.supports_cod,
            "supports_hubstudio_submit": adapter.supports_hubstudio_submit,
        },
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


def build_workbook(*, template, category: str, cod: str, attributes: dict[str, str], products: list[dict], template_bytes: bytes | None = None, template_type: str | None = None) -> bytes:
    workbook = load_workbook(_template_source(template_bytes), data_only=False, read_only=False)
    sheet = workbook["Template"]
    field_columns = _field_columns(sheet)
    adapter = tiktok_template_adapter(set(field_columns), template_type)
    missing_fields = sorted(adapter.required_fields - set(field_columns))
    if missing_fields:
        raise ValueError(f"TikTok 模板缺少导出字段：{', '.join(missing_fields)}")
    data_end_row = sheet.max_row
    for row in sheet.iter_rows(min_row=DATA_START_ROW, max_row=data_end_row, min_col=1, max_col=sheet.max_column):
        for cell in row:
            cell.value = None

    sizes = [
        _clean(size)
        for size in ((template.sku_specifications or {}).get("size", {}).get("options", []))
        if _clean(size)
    ] or ["Default"]
    row_number = DATA_START_ROW
    attribute_columns = {field: column for column, field in _attribute_fields(sheet)}
    weight_grams = round(float(template.package_weight) * 1000, 3)
    for product in products:
        image_urls = list(dict.fromkeys(product["image_urls"]))
        gallery = image_urls[:9]
        sku_images = product.get("sku_images") or [
            {"image_url": image_url, "sku": product["base_sku_by_image"][image_url]}
            for image_url in image_urls
        ]
        for sku_image in sku_images:
            image_url = sku_image["image_url"]
            base_sku = sku_image["sku"]
            for size in sizes:
                if row_number > data_end_row:
                    raise ValueError(f"导出数据超过 TikTok 模板 {data_end_row - DATA_START_ROW + 1} 行限制")
                seller_sku = base_sku if size == "Default" else f"{base_sku}-{size}"
                values = {
                    FIELD_CATEGORY: category,
                    FIELD_PRODUCT_NAME: product["title"],
                    FIELD_PRODUCT_DESCRIPTION: product["description"],
                    FIELD_PROPERTY_NAME_1: "Color",
                    FIELD_PROPERTY_VALUE_1: base_sku,
                    # 模板 P 列 property_1_image 的中文表头是“主要变体图片 1”。
                    FIELD_PROPERTY_1_IMAGE: image_url,
                    FIELD_PROPERTY_NAME_2: "Size",
                    FIELD_PROPERTY_VALUE_2: size,
                    FIELD_PARCEL_WEIGHT: weight_grams,
                    FIELD_PARCEL_LENGTH: template.package_length,
                    FIELD_PARCEL_WIDTH: template.package_width,
                    FIELD_PARCEL_HEIGHT: template.package_height,
                    FIELD_PRICE: product["price"],
                    FIELD_QUANTITY: product["quantity"],
                    FIELD_SELLER_SKU: seller_sku,
                    FIELD_SIZE_CHART: product.get("size_chart_url"),
                }
                if adapter.key == TIKTOK_LOCAL_ADAPTER.key:
                    values[FIELD_DELIVERY] = None
                    values[FIELD_COD] = cod
                else:
                    for field in (FIELD_SPECIAL_PRODUCT_LISTING_TYPE, FIELD_AUCTION_STARTING_PRICE):
                        if field in field_columns:
                            values[field] = None
                for index, gallery_url in enumerate(gallery):
                    values[FIELD_MAIN_IMAGE if index == 0 else f"image_{index + 1}"] = gallery_url
                for field, value in values.items():
                    sheet.cell(row_number, field_columns[field]).value = value
                for field, value in attributes.items():
                    sheet.cell(row_number, attribute_columns[field]).value = value
                row_number += 1

    output = BytesIO()
    workbook.save(output)
    return _preserve_template_package(output.getvalue(), template_bytes)
