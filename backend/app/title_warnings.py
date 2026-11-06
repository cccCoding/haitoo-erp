"""标题历史提示的展示兼容；不修改持久化的原始记录。"""

_HIDDEN_WARNINGS = {
    '按首图描述，请核对其他 SKU',
    '与本批或近 90 天已采用标题高度相似，真实属性有限时允许保留',
    '与并发生成的同批标题高度相似，请核对',
}
_LEGACY_FALLBACK_SUFFIX = '；可能与其他链接高度相似'


def visible_title_warnings(warnings):
    return [warning.removesuffix(_LEGACY_FALLBACK_SUFFIX) for warning in warnings or []
            if warning not in _HIDDEN_WARNINGS]
