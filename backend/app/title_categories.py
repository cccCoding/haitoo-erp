"""产品分类归一：名称登记、导入归类和可审计合并。写操作由调用方持有市场锁。"""
from collections import Counter
from datetime import datetime
from difflib import SequenceMatcher
from functools import wraps

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, undefer

from .title_dictionary import name_key, touch_market
from .title_models import (TitleCategoryMerge, TitleCategoryName, TitleDictionaryEntry,
    TitleImportWord, TitleKeyword, TitleTask, TitleTemplateProfile)
from .title_service import digest, normalize


def category_conflicts(function):
    @wraps(function)
    def guarded(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except IntegrityError as exc:
            kwargs['db'].rollback()
            raise HTTPException(409, '分类或关联数据发生并发冲突，请刷新后重新确认') from exc
    return guarded


def checked_name(value):
    value = str(value or '').strip()
    if not value or len(value) > 255:
        raise HTTPException(400, '产品分类名称及别名须为 1–255 个字符')
    return value


def category_by_id(db, market_id, identity, *, lock=False):
    seen = set()
    while identity:
        query = select(TitleDictionaryEntry).options(joinedload(TitleDictionaryEntry.names)).where(TitleDictionaryEntry.id == identity)
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        row = db.scalars(query).unique().one_or_none()
        if not row or row.market_id != market_id or row.kind != 'category':
            raise HTTPException(404, '目标产品分类不存在')
        if identity in seen:
            raise HTTPException(409, '分类合并指向异常，请联系管理员')
        seen.add(identity)
        if not row.merged_into_id:
            return row
        identity = row.merged_into_id
    raise HTTPException(404, '目标产品分类不存在')


def category_index(db, market_id, *, lock=False):
    query = select(TitleDictionaryEntry).options(joinedload(TitleDictionaryEntry.names)).where(
        TitleDictionaryEntry.market_id == market_id, TitleDictionaryEntry.kind == 'category')
    if lock:
        # MySQL 默认可重复读：持有市场锁后仍须当前读，避免等待锁期间的旧快照。
        query = query.with_for_update().execution_options(populate_existing=True)
    definitions = db.scalars(query).unique().all()
    by_id = {row.id: row for row in definitions}
    result = {}
    for row in definitions:
        target, seen = row, set()
        while target.merged_into_id:
            if target.id in seen or target.merged_into_id not in by_id:
                raise HTTPException(409, '分类合并指向异常，请联系管理员')
            seen.add(target.id)
            target = by_id[target.merged_into_id]
        result[row.name_key] = target
        for item in row.names:
            result[item.name_key] = target
    return result


def sync_names(db, row, aliases=None):
    """标准名、别名共用数据库唯一约束；合并保留的旧名称不得移除。"""
    # 生产 Session 禁用 autoflush，当前读之前先保存本事务内的名称变更。
    db.flush()
    known = category_index(db, row.market_id, lock=True)
    if row.merged_into_id:
        raise HTTPException(409, '该分类已合并，请编辑目标分类')
    current = {item.name_key: item for item in row.names}
    if aliases is None:
        aliases = [item.name for item in row.names if item.name_key != row.name_key]
    desired = {name_key(name): checked_name(name) for name in aliases}
    desired[row.name_key] = row.name
    reserved = db.scalars(select(TitleDictionaryEntry).where(TitleDictionaryEntry.market_id == row.market_id,
        TitleDictionaryEntry.kind == 'category', TitleDictionaryEntry.merged_into_id == row.id).with_for_update()).all()
    if any(source.name_key not in desired for source in reserved):
        raise HTTPException(409, '合并保留的原分类名称不可移除')
    for key, name in desired.items():
        if key in known and known[key].id != row.id:
            raise HTTPException(409, f'分类名称或别名“{name}”已属于“{known[key].name}”')
    for key, item in list(current.items()):
        if key not in desired:
            row.names.remove(item)
    db.flush()
    for key, name in desired.items():
        if key in current:
            current[key].name = name
        else:
            row.names.append(TitleCategoryName(market_id=row.market_id, name=name, name_key=key))
    db.flush()


def create_category(db, market_id, name, *, known=None):
    name = checked_name(name)
    known = category_index(db, market_id, lock=True) if known is None else known
    if name_key(name) in known:
        raise HTTPException(409, f'分类名称或别名“{name}”已存在，请选择已有分类')
    row = TitleDictionaryEntry(market_id=market_id, kind='category', name=name, name_key=name_key(name),
        names=[TitleCategoryName(market_id=market_id, name=name, name_key=name_key(name))])
    db.add(row)
    db.flush()
    known[row.name_key] = row
    return row


def source_categories(task):
    from .title_import import split_values
    names, counts = {}, Counter()
    for row in task.snapshot.get('rows', []):
        values = row['values']
        categories = [values['商品品类']] if task.snapshot['kind'] == 'titles' else split_values(values['适用品类'])
        for key, name in {name_key(value): value for value in categories}.items():
            names.setdefault(key, name)
            counts[key] += 1
    return names, counts


def resolution_token(task):
    return digest([task.id, task.snapshot.get('category_resolution', [])])


def resolve_choice(db, task, key, source, choices, known, *, lock=False, targets=None):
    choice = choices.get(key)
    if not choice:
        target = known.get(key)
        if not target:
            raise HTTPException(409, f'陌生分类“{source}”尚未确认，请选择已有分类或明确新建')
        choice = {'source_key': key, 'target_id': target.id, 'save_alias': False}
    if choice.get('target_id'):
        target = targets.get(choice['target_id']) if targets is not None else None
        if target is None:
            target = category_by_id(db, task.market_id, choice['target_id'], lock=lock)
            if targets is not None:
                targets[choice['target_id']] = target
        if not target.enabled:
            raise HTTPException(400, f'产品分类“{target.name}”已停用，请先启用')
        if key in known and known[key].id != target.id:
            raise HTTPException(409, f'“{source}”已属于“{known[key].name}”，请刷新或通过分类合并处理')
        return {**choice, 'target_id': target.id, 'target_name': target.name, 'new_name': None}
    name = checked_name(choice.get('new_name'))
    existing = known.get(name_key(name))
    if existing:
        # 本次已明确新建的名称被另一事务创建/占用，要求重新确认，不能静默改变意图。
        raise HTTPException(409, f'拟新建分类“{name}”已存在，请刷新后选择已有分类')
    if key in known:
        raise HTTPException(409, f'“{source}”已属于“{known[key].name}”，请重新确认')
    return {**choice, 'target_name': name, 'new_name': name, 'target_id': None}


def validate_choices(db, task, choices, *, keys=None):
    names, _ = source_categories(task)
    if len(choices) != len({item['source_key'] for item in choices}):
        raise HTTPException(400, '分类归类方案不能包含重复来源')
    by_key = {item['source_key']: item for item in choices}
    if set(by_key) - set(names):
        raise HTTPException(400, '分类归类方案包含不属于本次导入的名称')
    known, resolved, claims = category_index(db, task.market_id, lock=True), {}, {}
    targets = {row.id: row for row in known.values()}
    for key in names if keys is None else keys:
        item = resolve_choice(db, task, key, names[key], by_key, known, lock=True, targets=targets)
        resolved[key] = item
        owner = ('id', item['target_id']) if item['target_id'] else ('new', name_key(item['new_name']))
        claimed_keys = [name_key(item['target_name'])]
        if item.get('save_alias'):
            claimed_keys.append(key)
        for claim in claimed_keys:
            if claim in claims and claims[claim] != owner:
                raise HTTPException(409, '本次归类方案中的标准名称与别名冲突，请重新选择')
            claims[claim] = owner
    return resolved


def category_summary(db, task):
    names, counts = source_categories(task)
    choices = {item['source_key']: item for item in task.snapshot.get('category_resolution', [])}
    known = category_index(db, task.market_id)
    targets = {row.id: row for row in known.values()}
    options = sorted({row.id: row for row in known.values()}.values(), key=lambda row: row.id)
    result = []
    for key, source in names.items():
        target = known.get(key)
        state = 'standard' if target and target.name_key == key else 'alias' if target else 'unknown'
        try:
            choice = resolve_choice(db, task, key, source, choices, known, targets=targets)
            if key in choices:
                state = 'planned'
            message = ''
        except HTTPException as exc:
            choice = choices.get(key, {})
            state = 'disabled' if exc.status_code == 400 else 'conflict' if key in choices else 'unknown'
            message = exc.detail
        suggestions = sorted((
            (max(SequenceMatcher(None, normalize(source), normalize(name)).ratio()
                 for name in [row.name, *(item.name for item in row.names)]), row)
            for row in options if row.enabled), key=lambda pair: (-pair[0], pair[1].id))[:3] if state == 'unknown' else []
        result.append({'source_key': key, 'source': source, 'row_count': counts[key], 'match': state,
            'target_id': choice.get('target_id'), 'new_name': choice.get('new_name'),
            'target_name': choice.get('target_name', target.name if target else ''),
            'save_alias': choice.get('save_alias', True), 'message': message,
            'suggestions': [{'id': row.id, 'name': row.name} for score, row in suggestions if score >= .35]})
    return {'items': result, 'options': [{'id': row.id, 'name': row.name, 'enabled': row.enabled,
        'aliases': [item.name for item in row.names if item.name_key != row.name_key]} for row in options],
        'token': resolution_token(task), 'ready': all(item['match'] not in ('unknown', 'conflict', 'disabled') for item in result)}


def save_resolution(db, task, choices, token):
    if token != resolution_token(task):
        raise HTTPException(409, '分类归类方案已变化，请刷新后重新确认')
    resolved = validate_choices(db, task, choices)
    task.snapshot = {**task.snapshot, 'category_resolution': [
        {key: item.get(key) for key in ('source_key', 'target_id', 'new_name', 'save_alias')}
        for item in resolved.values()]}
    task.updated_at = datetime.utcnow()


def materialize_categories(db, task, values):
    """仅为实际选中结果兑现新建/别名；原始行与提词分类保留用于追溯。"""
    keys = {name_key(value) for value in values}
    choices = task.snapshot.get('category_resolution', [])
    resolved = validate_choices(db, task, choices, keys=keys)
    created, by_key, aliases_by_target = {}, {}, {}
    known = category_index(db, task.market_id, lock=True)
    targets = {row.id: row for row in known.values()}
    for key, item in resolved.items():
        if item['target_id']:
            target = targets[item['target_id']]
        else:
            new_key = name_key(item['new_name'])
            if new_key not in created:
                created[new_key] = create_category(db, task.market_id, item['new_name'], known=known)
            target = created[new_key]
        by_key[key] = target
    names, _ = source_categories(task)
    for key, target in by_key.items():
        if resolved[key].get('save_alias') and key != target.name_key:
            aliases_by_target.setdefault(target.id, (target, []))[1].append(names[key])
    for target, aliases in aliases_by_target.values():
        existing = [item.name for item in target.names if item.name_key != target.name_key]
        sync_names(db, target, [*existing, *aliases])
    # 同一个拟新建目标可能由多个来源引用，部分入库后统一固定其 ID。
    updated = []
    for item in choices:
        target = created.get(name_key(item.get('new_name') or ''))
        updated.append({**item, 'target_id': target.id, 'new_name': None} if target else item)
    task.snapshot = {**task.snapshot, 'category_resolution': updated}
    return {key: target.name for key, target in by_key.items()}


def display_categories(values, summary):
    mapped = {item['source_key']: item.get('target_name') or item['source'] for item in summary['items']}
    return list(dict.fromkeys(mapped.get(name_key(value), value) for value in values))


def merge_preview(db, market, source_ids, target_id):
    source_ids = sorted(set(source_ids))
    target = category_by_id(db, market.id, target_id, lock=True)
    if target.id != target_id or not target.enabled or target_id in source_ids:
        raise HTTPException(400, '请选择未合并且已启用的目标分类，源分类和目标不能相同')
    sources = []
    for identity in source_ids:
        row = category_by_id(db, market.id, identity, lock=True)
        if row.id != identity:
            raise HTTPException(409, '源分类已合并，请刷新分类列表')
        sources.append(row)
    source_keys = {item.name_key for row in sources for item in row.names} | {row.name_key for row in sources}
    keywords = [word for word in db.scalars(select(TitleKeyword).where(TitleKeyword.market_id == market.id)
        .with_for_update().execution_options(populate_existing=True))
        if any(name_key(name) in source_keys for name in word.categories)]
    profiles = [profile for profile in db.scalars(select(TitleTemplateProfile).where(
        TitleTemplateProfile.market_id == market.id).with_for_update().execution_options(populate_existing=True)) if name_key(profile.category) in source_keys]
    pending = []
    for task in db.scalars(select(TitleTask).options(undefer(TitleTask.snapshot)).where(TitleTask.market_id == market.id, TitleTask.kind == 'import')
            .with_for_update().execution_options(populate_existing=True)):
        # completed 仍允许继续入库未选结果，也必须纳入影响预览。
        unimported = db.scalars(select(TitleImportWord).where(TitleImportWord.task_id == task.id).with_for_update()).all()
        selections = set(task.result.get('selections', []))
        if task.state == 'completed' and all(word.id in selections for word in unimported):
            continue
        names, _ = source_categories(task)
        plan_ids = {item.get('target_id') for item in task.snapshot.get('category_resolution', [])}
        if set(names) & source_keys or set(source_ids) & plan_ids:
            pending.append(task)
    def brief(row):
        return {'id': row.id, 'name': row.name, 'localized_name': row.localized_name, 'description': row.description,
            'enabled': row.enabled, 'aliases': sorted(item.name for item in row.names if item.name_key != row.name_key)}
    summary = {'sources': [brief(row) for row in sources], 'target': brief(target),
        'counts': {'keywords': len(keywords), 'templates': len(profiles), 'imports': len(pending)},
        'notice': '保留目标分类的名称、马来西亚名称和说明；源分类名称及别名转为目标别名。历史证据及已提交标题快照保留。'}
    token = digest([summary, market.revision,
        [(word.id, word.categories) for word in keywords], [(p.id, p.category) for p in profiles],
        [(task.id, task.state, task.snapshot.get('category_resolution', []), task.result.get('selections', [])) for task in pending]])
    return {**summary, 'token': token}, (sources, target, source_keys, keywords, profiles)


def merge_categories(db, market, user_id, source_ids, target_id, token):
    previous = db.scalar(select(TitleCategoryMerge).where(TitleCategoryMerge.market_id == market.id,
        TitleCategoryMerge.preview_token == token).with_for_update())
    if previous:
        if previous.source_ids != sorted(set(source_ids)) or previous.target_id != target_id:
            raise HTTPException(409, '合并请求与预览不一致')
        return previous.summary
    summary, (sources, target, source_keys, keywords, profiles) = merge_preview(db, market, source_ids, target_id)
    if summary['token'] != token:
        raise HTTPException(409, '分类或引用已变化，请重新预览并确认合并')
    now = datetime.utcnow()
    for word in keywords:
        values = [target.name if name_key(name) in source_keys or name_key(name) == target.name_key else name for name in word.categories]
        word.categories = list({name_key(name): name for name in values}.values())
        word.updated_at = now
    for profile in profiles:
        profile.category, profile.updated_at = target.name, now
    # 展平旧合并指向；旧名称记录随源分类一起转移，不修改任务原始数据。
    for row in db.scalars(select(TitleDictionaryEntry).where(TitleDictionaryEntry.market_id == market.id,
            TitleDictionaryEntry.merged_into_id.in_(source_ids))):
        row.merged_into_id, row.updated_at = target.id, now
    for source in sources:
        for item in list(source.names):
            source.names.remove(item)
            target.names.append(item)
        source.merged_into_id, source.enabled, source.updated_at = target.id, False, now
    target.updated_at = now
    touch_market(market)
    db.add(TitleCategoryMerge(market_id=market.id, user_id=user_id, target_id=target.id,
        source_ids=sorted(set(source_ids)), preview_token=token, summary=summary))
    db.flush()
    return summary
