"""词库产品分类与标签字典；显示名称和生成语义分开管理。"""
import hashlib
import re
import unicodedata
from collections import Counter
from datetime import datetime
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import undefer

from .title_models import TitleDictionaryEntry, TitleImportWord, TitleKeyword, TitleTask, TitleTemplateProfile
from .title_service import CATEGORY_FIELDS, DICTIONARY_TAGS, normalize


def name_key(value):
    return hashlib.sha256(normalize(value).encode()).hexdigest()


def localized_category_name(value):
    value = (value or '').strip()
    if not value:
        return None
    if (re.search(r'[\u3400-\u9fff]', value) or any(unicodedata.category(c).startswith('C') for c in value)
            or any(c in value for c in ('"', '*', '`', '<', '>'))):
        raise HTTPException(400, '马来西亚分类名称请填写单行马来语，不包含中文、Markdown 或控制字符')
    return value


def entries(db, market_id, kind=None, *, include_merged=False):
    query = select(TitleDictionaryEntry).where(TitleDictionaryEntry.market_id == market_id)
    if not include_merged:
        query = query.where(TitleDictionaryEntry.merged_into_id.is_(None))
    if kind:
        query = query.where(TitleDictionaryEntry.kind == kind)
    return db.scalars(query.order_by(TitleDictionaryEntry.id)).all()


def seed_tags(db, market):
    existing = {row.name_key for row in entries(db, market.id, 'tag')}
    for tag in DICTIONARY_TAGS:
        if name_key(tag) not in existing:
            db.add(TitleDictionaryEntry(market_id=market.id, kind='tag', name=tag, name_key=name_key(tag),
                semantic_tag=tag, built_in=True))
    db.flush()


def category_values(db, market, values, *, allow_disabled=()):
    from .title_categories import category_index, create_category
    known = category_index(db, market.id, lock=True)
    allowed = {name_key(value) for value in allow_disabled}
    result = []
    for value in values:
        value = str(value).strip()
        if not value or len(value) > 255:
            raise HTTPException(400, '产品分类须为 1–255 个字符')
        key = name_key(value)
        row = known.get(key)
        if row and not row.enabled and row.name_key not in allowed:
            raise HTTPException(400, f'产品分类“{row.name}”已停用，请先在产品分类中启用')
        if not row:
            row = create_category(db, market.id, value, known=known)
            known[key] = row
        if row.name not in result:
            result.append(row.name)
    db.flush()
    return result


def tag_entry(db, market, name, *, allow_disabled=None):
    # 模板基础字段和旧面料词保留内部语义，不建立重复的标签条目。
    if name in CATEGORY_FIELDS:
        return SimpleNamespace(name=name, semantic_tag=name, enabled=True)
    if name == '面料':
        material = tag_entry(db, market, '材质', allow_disabled='材质' if allow_disabled == name else None)
        return SimpleNamespace(name=name, semantic_tag='材质', enabled=material.enabled)
    row = db.scalar(select(TitleDictionaryEntry).where(TitleDictionaryEntry.market_id == market.id,
        TitleDictionaryEntry.kind == 'tag', TitleDictionaryEntry.name_key == name_key(name)))
    if not row:
        raise HTTPException(400, f'标签“{name}”不存在，请先在标签管理中新增')
    if not row.enabled and name_key(name) != name_key(allow_disabled or ''):
        raise HTTPException(400, f'标签“{row.name}”已停用')
    return row


def usage_counts(db, market_id, *, lock=False):
    """一次读取当前引用，包含可恢复导入，历史快照不参与删除限制。"""
    counts = Counter()
    def current(query):
        return query.with_for_update().execution_options(populate_existing=True) if lock else query
    for word in db.scalars(current(select(TitleKeyword).where(TitleKeyword.market_id == market_id))):
        counts[('tag', name_key(word.tag), 'keyword')] += 1
        for category in {name_key(c) for c in word.categories}:
            counts[('category', category, 'keyword')] += 1
            if word.merged_into_id is None:
                counts[('category', category, 'applicable_keyword')] += 1
    for profile in db.scalars(current(select(TitleTemplateProfile).where(TitleTemplateProfile.market_id == market_id))):
        counts[('category', name_key(profile.category), 'template')] += 1
        for tag in profile.attributes:
            counts[('tag', name_key(tag), 'template')] += 1
    from .title_categories import category_by_id, category_index
    category_names = category_index(db, market_id, lock=lock)
    archives = current(select(TitleDictionaryEntry.name_key, TitleDictionaryEntry.merged_into_id).where(
        TitleDictionaryEntry.market_id == market_id, TitleDictionaryEntry.kind == 'category'))
    for archived in db.execute(archives):
        if archived.merged_into_id:
            counts[('category', category_names[archived.name_key].name_key, 'merged_source')] += 1
    tasks = db.scalars(current(select(TitleTask).options(undefer(TitleTask.snapshot)).where(
        TitleTask.market_id == market_id, TitleTask.kind == 'import'))).all()
    for task in tasks:
        words = db.scalars(current(select(TitleImportWord).where(TitleImportWord.task_id == task.id))).all()
        confirmed = set(task.result.get('selections', []))
        if task.state == 'completed' and all(word.id in confirmed for word in words):
            continue
        planned = {}
        for item in task.snapshot.get('category_resolution', []):
            if item.get('target_id'):
                planned[item['source_key']] = category_by_id(db, market_id, item['target_id']).name_key
        names = set()
        for row in task.snapshot.get('rows', []):
            values = row['values']
            if task.snapshot.get('kind') == 'titles':
                names.add(('category', name_key(values.get('商品品类', ''))))
            else:
                from .title_import import split_values
                names.update(('category', name_key(v)) for v in split_values(values.get('适用品类', '')))
                names.add(('tag', name_key(values.get('属性分类', ''))))
        for word in words:
            names.add(('tag', name_key(word.word['tag'])))
        names = {(kind, planned.get(key, category_names[key].name_key if key in category_names else key)
            if kind == 'category' else key) for kind, key in names}
        for kind, key in names:
            counts[(kind, key, 'import')] += 1
    return counts


def entry_payload(row, counts):
    result = {key: getattr(row, key) for key in ('id', 'kind', 'name', 'description', 'localized_name', 'semantic_tag', 'built_in', 'enabled')}
    result['merged_into_id'] = row.merged_into_id
    result['aliases'] = sorted(item.name for item in row.names if item.name_key != row.name_key)
    result['merged_source_count'] = counts[(row.kind, row.name_key, 'merged_source')]
    result['applicable_keyword_count'] = counts[(row.kind, row.name_key, 'applicable_keyword')]
    for source in ('keyword', 'template', 'import'):
        result[f'{source}_count'] = counts[(row.kind, row.name_key, source)]
    result['reference_count'] = sum(result[f'{source}_count'] for source in ('keyword', 'template', 'import')) + result['merged_source_count']
    return result


def touch_market(market):
    market.revision += 1
    market.updated_at = datetime.utcnow()
