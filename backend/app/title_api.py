"""公司词库、审核、模板确认属性和后台标题任务接口。"""
import copy
import csv
import io
import json
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session, undefer

from .ai_providers import ProviderError
from .database import get_db
from .models import MaterialAsset, ProductTemplate, Role, User
from .security import require_roles
from .title_import import MAX_BYTES, TITLE_COLUMN_NAMES, KEYWORD_COLUMN_NAMES, IMPORT_OPTIONAL_COLUMNS, confirm_import, parse_file
from .title_models import TitleCategoryMerge, TitleDictionaryEntry, TitleEvidence, TitleImportWord, TitleKeyword, TitleMarket, TitleRecord, TitleTask, TitleTemplateProfile
from .title_service import (TAGS, CATEGORY_FIELDS, DICTIONARY_TAGS, PROFILE_TAGS, GENDERS, AGE_GROUPS,
                            canonical_tag, profile_attributes, profile_issues, create_record, credential, digest, generate_record, get_market,
                            keyword_data, normalize, profile_snapshot, record_payload, validate_malay_title)

from .title_dictionary import (entries as dictionary_entries, entry_payload as dictionary_payload,
    usage_counts as dictionary_usage, name_key as dictionary_key, touch_market as touch_dictionary_market,
    category_values, tag_entry, localized_category_name)
from .title_categories import (category_index, category_summary, display_categories, merge_categories,
    merge_preview, save_resolution, sync_names, validate_choices, category_conflicts)

router = APIRouter()
reader = require_roles(Role.COMPANY_ADMIN, Role.MEMBER, Role.TEAM_LEADER)
admin = require_roles(Role.COMPANY_ADMIN)


class Input(BaseModel):
    model_config = {'extra': 'forbid'}


class MarketInput(Input):
    platform: Literal['TikTok', 'Shopee'] = 'TikTok'
    @field_validator('platform')
    @classmethod
    def shared_library(cls, value):
        return 'TikTok'

    site: Literal['MY'] = 'MY'
    language: Literal['ms'] = 'ms'


class MarketUpdate(MarketInput):
    enabled: bool


class ProfileInput(MarketInput):
    category: str = Field(min_length=1, max_length=255)
    gender: Literal['男', '女', '中性']
    age_group: Literal['成人', '儿童']
    attributes: dict[str, str] = Field(default_factory=dict, max_length=25)
    category_names: list[str] = Field(default_factory=list, max_length=100)
    locked_keyword_ids: list[int] = Field(default_factory=list, max_length=8)
    forbidden_keyword_ids: list[int] = Field(default_factory=list, max_length=100)
    fallback_title: str | None = Field(default=None, max_length=220)
    fallback_approved: bool = False

    @field_validator('category')
    @classmethod
    def nonempty_category(cls, value):
        if not value.strip():
            raise ValueError('品类不能为空')
        return value.strip()

    @field_validator('attributes')
    @classmethod
    def valid_attributes(cls, values):
        if any(not tag.strip() or len(tag) > 40 or tag in CATEGORY_FIELDS or not value.strip() or len(value) > 255 for tag, value in values.items()):
            raise ValueError('确认属性每项须为 1–255 字符；产品分类、性别和年龄请单独填写')
        return {tag: value.strip() for tag, value in values.items()}


class KeywordInput(Input):
    phrase: str | None = Field(default=None, min_length=1, max_length=160)
    translation: str | None = Field(default=None, min_length=1, max_length=255)
    tag: str | None = None
    categories: list[str] | None = Field(default=None, min_length=1, max_length=50)
    synonyms: list[str] | None = Field(default=None, max_length=50)
    conflicts: list[int] | None = Field(default=None, max_length=50)
    is_borrowed: bool | None = None
    status: Literal['enabled', 'disabled'] | None = None
    priority: Literal['preferred', 'normal', 'forbidden'] | None = None


class MergeInput(Input):
    target_id: int = Field(gt=0)


class KeywordStatusInput(Input):
    status: Literal['enabled', 'disabled']
    review_token: str = Field(min_length=64, max_length=64)


class ConfirmInput(Input):
    selections: list[int] = Field(max_length=300000)
    # 兼容旧客户端字段；确认入库始终视为审核通过并启用。
    enable: bool = True


class CategoryChoice(Input):
    source_key: str = Field(min_length=64, max_length=64)
    target_id: int | None = Field(default=None, gt=0)
    new_name: str | None = Field(default=None, min_length=1, max_length=255)
    save_alias: bool = True

    @field_validator('new_name')
    @classmethod
    def trimmed_new_name(cls, value):
        if value is not None and not value.strip():
            raise ValueError('新分类名称不能为空')
        return value.strip() if value else value


class CategoryResolutionInput(Input):
    token: str = Field(min_length=64, max_length=64)
    choices: list[CategoryChoice] = Field(max_length=10000)


class CategoryMergeInput(Input):
    source_ids: list[int] = Field(min_length=1, max_length=200)
    target_id: int = Field(gt=0)


class CategoryMergeExecute(CategoryMergeInput):
    token: str = Field(min_length=64, max_length=64)


class Source(Input):
    source_type: Literal['product', 'material'] = 'material'
    id: int = Field(gt=0)


class JobGroup(Input):
    key: str = Field(min_length=1, max_length=80)
    source: Source
    additional_requirements: str = Field(default='', max_length=1000)


class JobInput(MarketInput):
    template_id: int = Field(gt=0)
    request_key: str = Field(min_length=8, max_length=128)
    from_library: bool = False
    groups: list[JobGroup] = Field(min_length=1, max_length=400)


def market_for(db, user, platform='TikTok', site='MY', language='ms', **kwargs):
    return get_market(db, user.company_id, platform, site, language, **kwargs)


def require_title_credential(db, user_id, company_id):
    try:
        return credential(db, user_id, company_id)
    except ProviderError as exc:
        raise HTTPException(400, str(exc)) from exc


def scoped_row(db, model, identity, user):
    row = db.get(model, identity)
    market = db.get(TitleMarket, row.market_id) if row else None
    if not row or not market or market.company_id != user.company_id:
        raise HTTPException(404, '记录不存在')
    return row


def task_for(db, identity, user):
    task = scoped_row(db, TitleTask, identity, user)
    if user.role != Role.COMPANY_ADMIN and task.user_id != user.id:
        raise HTTPException(404, '任务不存在')
    return task


def profile_payload(profile, market=None, db=None):
    definitions = dictionary_entries(db, market.id) if db is not None and market else []
    categories = [row for row in definitions if row.kind == 'category']
    category_entry = next((row for row in categories if profile and dictionary_key(row.name) == dictionary_key(profile.category)), None)
    attributes, conflicts = profile_attributes(profile.attributes, definitions) if profile else ({}, [])
    attribute_tags = [{'name': row.name, 'semantic_tag': canonical_tag(row.semantic_tag)} for row in definitions
        if row.kind == 'tag' and row.enabled and canonical_tag(row.semantic_tag) in PROFILE_TAGS and row.name != '面料']
    tag_definitions = {row.name: row for row in definitions if row.kind == 'tag'}
    keyword_options = []
    if db is not None and market:
        for row in db.scalars(select(TitleKeyword).where(TitleKeyword.market_id == market.id,
                TitleKeyword.merged_into_id.is_(None)).order_by(TitleKeyword.id)):
            definition = tag_definitions.get(row.tag) or tag_definitions.get(canonical_tag(row.tag))
            keyword_options.append({'id': row.id, 'code': row.code, 'phrase': row.phrase,
                'translation': row.translation, 'tag': row.tag, 'categories': row.categories,
                'status': row.status, 'priority': row.priority,
                'semantic_tag': canonical_tag(definition.semantic_tag if definition else row.tag),
                'tag_enabled': definition.enabled if definition else row.tag in CATEGORY_FIELDS})
    attribute_keyword_options = [word for word in keyword_options if word['status'] == 'enabled'
        and word['priority'] != 'forbidden' and word['tag_enabled'] and word['semantic_tag'] in PROFILE_TAGS]
    material_options = [word for word in attribute_keyword_options if word['semantic_tag'] == '材质']
    issues = profile_issues(profile, category_entry, definitions)
    return {'category': profile.category if profile else '', 'attributes': profile.attributes if profile else {},
        'gender': profile.gender if profile else None, 'age_group': profile.age_group if profile else None,
        'material': attributes.get('材质', '') if '材质' not in conflicts else '', 'material_options': material_options,
        'keyword_options': keyword_options, 'attribute_keyword_options': attribute_keyword_options,
        'conflicting_attributes': conflicts,
        'configuration_issues': issues, 'ready': not issues,
        'category_names': profile.category_names if profile else [],
        'locked_keyword_ids': profile.locked_keyword_ids if profile else [],
        'forbidden_keyword_ids': profile.forbidden_keyword_ids if profile else [],
        'fallback_title': profile.fallback_title if profile else '',
        'fallback_approved': profile.fallback_approved if profile else False,
        'categories': [row.name for row in categories if row.enabled],
        'category_options': [{'name': row.name, 'localized_name': row.localized_name, 'enabled': row.enabled} for row in categories],
        'attribute_tags': attribute_tags, 'genders': GENDERS, 'age_groups': AGE_GROUPS,
        'enabled': True, 'tags': [row['name'] for row in attribute_tags] if definitions else PROFILE_TAGS, 'site': 'MY', 'language': 'ms'}


class DictionaryCreate(MarketInput):
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default='', max_length=500)
    semantic_tag: str | None = None
    localized_name: str | None = Field(default=None, max_length=255)
    enabled: bool = True
    aliases: list[str] = Field(default_factory=list)


class DictionaryUpdate(Input):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=500)
    semantic_tag: str | None = None
    localized_name: str | None = Field(default=None, max_length=255)
    enabled: bool | None = None
    aliases: list[str] | None = None


@router.get('/title-dictionaries')
def dictionaries(kind: Literal['category', 'tag'] | None = None, platform: str = 'TikTok', site: str = 'MY', language: str = 'ms', include_merged: bool = False,
                 user: User = Depends(reader), db: Session = Depends(get_db)):
    market = market_for(db, user, platform, site, language)
    counts = dictionary_usage(db, market.id) if market else {}
    return {'items': [dictionary_payload(row, counts) for row in dictionary_entries(db, market.id, kind, include_merged=include_merged)] if market else [],
            'semantic_tags': DICTIONARY_TAGS, 'category_fields': CATEGORY_FIELDS, 'genders': GENDERS, 'age_groups': AGE_GROUPS}


@router.post('/title-dictionaries/{kind}')
@category_conflicts
def create_dictionary(kind: Literal['category', 'tag'], payload: DictionaryCreate,
                      user: User = Depends(admin), db: Session = Depends(get_db)):
    market = market_for(db, user, payload.platform, payload.site, payload.language, create=True, lock=True)
    name = payload.name.strip()
    if kind == 'tag':
        payload.semantic_tag = canonical_tag(payload.semantic_tag)
    if not name or (kind == 'tag' and len(name) > 40):
        raise HTTPException(400, '产品分类名称须为 1–255 字符，标签名称须为 1–40 字符')
    if kind == 'tag' and (name in (*CATEGORY_FIELDS, '面料') or payload.semantic_tag in (*CATEGORY_FIELDS, '面料')):
        raise HTTPException(400, '产品分类、性别和年龄在模板配置中设置；面料为内置标签，请编辑已有条目')
    if (kind == 'tag' and payload.semantic_tag not in DICTIONARY_TAGS) or (kind == 'category' and payload.semantic_tag is not None):
        raise HTTPException(400, '标签必须选择内置语义分类，产品分类不填写语义分类')
    if kind == 'tag' and payload.localized_name is not None:
        raise HTTPException(400, '站点分类名称只在产品分类中设置')
    if kind == 'tag' and payload.aliases:
        raise HTTPException(400, '别名只在产品分类中设置')
    if kind == 'category' and dictionary_key(name) in category_index(db, market.id, lock=True):
        raise HTTPException(409, '该分类名称或别名已存在，请编辑已有条目')
    if any(row.name_key == dictionary_key(name) for row in dictionary_entries(db, market.id, kind)):
        raise HTTPException(409, '该名称已存在，请编辑已有条目')
    row = TitleDictionaryEntry(market_id=market.id, kind=kind, name=name, name_key=dictionary_key(name),
        description=payload.description.strip(),
        localized_name=localized_category_name(payload.localized_name), semantic_tag=payload.semantic_tag, enabled=payload.enabled)
    db.add(row)
    db.flush()
    if kind == 'category':
        sync_names(db, row, payload.aliases)
    touch_dictionary_market(market)
    db.flush()
    result = dictionary_payload(row, dictionary_usage(db, market.id))
    db.commit()
    return result


@router.patch('/title-dictionaries/{identity}')
@category_conflicts
def update_dictionary(identity: int, payload: DictionaryUpdate, user: User = Depends(admin), db: Session = Depends(get_db)):
    row = scoped_row(db, TitleDictionaryEntry, identity, user)
    market = db.scalar(select(TitleMarket).where(TitleMarket.id == row.market_id).with_for_update().execution_options(populate_existing=True))
    db.refresh(row, with_for_update=True)
    if row.merged_into_id:
        raise HTTPException(409, '该分类已合并，请编辑目标分类')
    data = payload.model_dump(exclude_unset=True)
    if any(value is None for value in data.values()):
        raise HTTPException(400, '编辑字段不能为 null')
    name = data.get('name', row.name).strip()
    semantic = canonical_tag(data.get('semantic_tag', row.semantic_tag)) if row.kind == 'tag' else data.get('semantic_tag', row.semantic_tag)
    if not name or len(name) > (40 if row.kind == 'tag' else 255):
        raise HTTPException(400, '产品分类名称须为 1–255 字符，标签名称须为 1–40 字符')
    if (row.kind == 'tag' and (name in (*CATEGORY_FIELDS, '面料') or (semantic not in DICTIONARY_TAGS and semantic != row.semantic_tag))) or (row.kind == 'category' and semantic is not None):
        raise HTTPException(400, '语义分类无效')
    if row.kind == 'tag' and 'localized_name' in data:
        raise HTTPException(400, '站点分类名称只在产品分类中设置')
    if row.kind == 'tag' and 'aliases' in data:
        raise HTTPException(400, '别名只在产品分类中设置')
    changed_identity = name != row.name or semantic != row.semantic_tag
    counts = dictionary_usage(db, market.id, lock=True)
    if changed_identity and (row.built_in or dictionary_payload(row, counts)['reference_count']):
        raise HTTPException(409, '内置或已被引用的条目不能修改名称和语义分类，可编辑说明或启停')
    if any(other.id != row.id and other.name_key == dictionary_key(name) for other in dictionary_entries(db, market.id, row.kind)):
        raise HTTPException(409, '该名称已存在')
    if row.kind == 'category':
        owner = category_index(db, market.id, lock=True).get(dictionary_key(name))
        if owner and owner.id != row.id:
            raise HTTPException(409, '该分类名称或别名已存在')
    row.name, row.name_key, row.semantic_tag = name, dictionary_key(name), semantic
    if row.kind == 'category':
        sync_names(db, row, data.get('aliases'))
    row.description = data.get('description', row.description).strip()
    if 'localized_name' in data:
        row.localized_name = localized_category_name(data['localized_name'])
    row.enabled = data.get('enabled', row.enabled)
    row.updated_at = datetime.utcnow()
    touch_dictionary_market(market)
    result = dictionary_payload(row, counts)
    db.commit()
    return result


@router.delete('/title-dictionaries/{identity}')
@category_conflicts
def delete_dictionary(identity: int, user: User = Depends(admin), db: Session = Depends(get_db)):
    row = scoped_row(db, TitleDictionaryEntry, identity, user)
    market = db.scalar(select(TitleMarket).where(TitleMarket.id == row.market_id).with_for_update().execution_options(populate_existing=True))
    db.refresh(row, with_for_update=True)
    if row.merged_into_id or db.scalar(select(TitleDictionaryEntry.id).where(
            TitleDictionaryEntry.market_id == market.id, TitleDictionaryEntry.merged_into_id == row.id).limit(1)):
        raise HTTPException(409, '合并归档及目标分类不可删除，可停用以停止后续使用')
    counts = dictionary_usage(db, market.id, lock=True)
    if row.built_in or dictionary_payload(row, counts)['reference_count']:
        raise HTTPException(409, '内置或已被引用的条目不能删除，可停用以停止后续使用')
    db.delete(row)
    touch_dictionary_market(market)
    db.commit()
    return {'id': identity}


@router.post('/title-category-merges/preview')
def preview_category_merge(payload: CategoryMergeInput, user: User = Depends(admin), db: Session = Depends(get_db)):
    target = scoped_row(db, TitleDictionaryEntry, payload.target_id, user)
    market = db.scalar(select(TitleMarket).where(TitleMarket.id == target.market_id).with_for_update().execution_options(populate_existing=True))
    result, _ = merge_preview(db, market, payload.source_ids, payload.target_id)
    return result


@router.get('/title-category-merges')
def category_merge_history(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                           user: User = Depends(reader), db: Session = Depends(get_db)):
    market = market_for(db, user)
    query = select(TitleCategoryMerge).where(TitleCategoryMerge.market_id == market.id) if market else None
    total = db.scalar(select(func.count()).select_from(query.subquery())) if query is not None else 0
    rows = db.scalars(query.order_by(TitleCategoryMerge.id.desc()).offset((page-1)*page_size).limit(page_size)).all() if total else []
    return {'items': [{'id': row.id, 'user_id': row.user_id,
        'operator': (actor.name if (actor := db.get(User, row.user_id)) else f'用户 {row.user_id}'),
        'created_at': row.created_at.isoformat()+'Z', 'summary': row.summary} for row in rows],
        'total': total, 'page': page, 'page_size': page_size}


@router.post('/title-category-merges')
@category_conflicts
def execute_category_merge(payload: CategoryMergeExecute, user: User = Depends(admin), db: Session = Depends(get_db)):
    target = scoped_row(db, TitleDictionaryEntry, payload.target_id, user)
    market = db.scalar(select(TitleMarket).where(TitleMarket.id == target.market_id).with_for_update().execution_options(populate_existing=True))
    result = merge_categories(db, market, user.id, payload.source_ids, payload.target_id, payload.token)
    db.commit()
    return result


@router.get('/title-market')
def market_settings(platform: str = 'TikTok', site: str = 'MY', language: str = 'ms',
                    user: User = Depends(reader), db: Session = Depends(get_db)):
    market = market_for(db, user, platform, site, language)
    return {'enabled': True, 'platform': 'TikTok', 'site': site, 'language': language,
            'revision': market.revision if market else 0, 'updated_at': market.updated_at.isoformat() + 'Z' if market else None, 'tags': [row.name for row in dictionary_entries(db, market.id, 'tag') if row.enabled] if market else TAGS}


@router.put('/title-market')
def update_market(payload: MarketUpdate, user: User = Depends(admin), db: Session = Depends(get_db)):
    market = market_for(db, user, payload.platform, payload.site, payload.language, create=True, lock=True)
    # 兼容旧接口；词库能力常驻开放，生成方式由每次请求明确选择。
    market.enabled = True
    market.updated_at = datetime.utcnow()
    db.commit()
    return {'enabled': market.enabled, 'revision': market.revision}


@router.get('/title-profiles/{template_id}')
def get_profile(template_id: int, platform: str = 'TikTok', user: User = Depends(reader), db: Session = Depends(get_db)):
    from .main import get_usable_template
    get_usable_template(db, user, template_id)
    market = market_for(db, user, platform)
    profile = db.scalar(select(TitleTemplateProfile).where(TitleTemplateProfile.market_id == market.id,
        TitleTemplateProfile.template_id == template_id)) if market else None
    return profile_payload(profile, market, db)


@router.put('/title-profiles/{template_id}')
def put_profile(template_id: int, payload: ProfileInput, user: User = Depends(admin), db: Session = Depends(get_db)):
    from .main import get_usable_template
    get_usable_template(db, user, template_id)
    market = market_for(db, user, payload.platform, payload.site, payload.language, create=True, lock=True)
    if set(payload.locked_keyword_ids) & set(payload.forbidden_keyword_ids):
        raise HTTPException(400, '同一关键词不能既必用又禁用')
    ids = set(payload.locked_keyword_ids + payload.forbidden_keyword_ids)
    valid = set(db.scalars(select(TitleKeyword.id).where(TitleKeyword.market_id == market.id,
                                                       TitleKeyword.id.in_(ids), TitleKeyword.merged_into_id.is_(None))))
    if valid != ids:
        raise HTTPException(400, '包含其他词库或不存在的关键词')
    fallback = payload.fallback_title.strip() if payload.fallback_title else None
    if payload.fallback_approved and not fallback:
        raise HTTPException(400, '请填写马来语兜底标题后再确认审核')
    if fallback:
        try:
            fallback = validate_malay_title(fallback, 220)
        except ProviderError as exc:
            raise HTTPException(400, str(exc)) from exc
    profile = db.scalar(select(TitleTemplateProfile).where(TitleTemplateProfile.market_id == market.id,
                                                         TitleTemplateProfile.template_id == template_id))
    definitions = dictionary_entries(db, market.id)
    _, conflicts = profile_attributes(payload.attributes, definitions)
    if conflicts:
        raise HTTPException(400, '确认属性重复且冲突：' + '、'.join('面料' if tag == '材质' else tag for tag in conflicts))
    cleaned = {}
    for tag, value in payload.attributes.items():
        definition = tag_entry(db, market, tag, allow_disabled=tag if profile and tag in profile.attributes else None)
        semantic = canonical_tag(definition.semantic_tag)
        if semantic not in PROFILE_TAGS:
            raise HTTPException(400, '请选择商品事实标签，产品分类、性别和年龄请单独填写')
        cleaned['材质' if semantic == '材质' else tag] = value
    payload.attributes = cleaned
    payload.category = category_values(db, market, [payload.category], allow_disabled=[profile.category] if profile else [])[0]
    if not profile:
        profile = TitleTemplateProfile(market_id=market.id, template_id=template_id)
        db.add(profile)
    for key in ('category', 'gender', 'age_group', 'attributes', 'category_names', 'locked_keyword_ids', 'forbidden_keyword_ids', 'fallback_approved'):
        setattr(profile, key, getattr(payload, key))
    profile.fallback_title = fallback
    profile.updated_at = datetime.utcnow()
    market.revision += 1
    market.updated_at = datetime.utcnow()
    db.commit()
    return profile_payload(profile, market, db)


@router.get('/title-template-configurations')
def template_configurations(q: str = '', category: str = '', state: Literal['', 'ready', 'incomplete'] = '',
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=1000),
    user: User = Depends(reader), db: Session = Depends(get_db)):
    market = market_for(db, user)
    definitions = dictionary_entries(db, market.id) if market else []
    categories = {row.name_key: row for row in definitions if row.kind == 'category'}
    profiles = {row.template_id: row for row in db.scalars(select(TitleTemplateProfile).where(
        TitleTemplateProfile.market_id == market.id))} if market else {}
    query = select(ProductTemplate).where(or_(ProductTemplate.company_id == user.company_id, ProductTemplate.is_platform.is_(True)))
    if q.strip():
        query = query.where(ProductTemplate.name.contains(q.strip(), autoescape=True))
    items = []
    for template in db.scalars(query.order_by(ProductTemplate.is_platform.desc(), ProductTemplate.id.desc())):
        profile = profiles.get(template.id)
        if category and (not profile or normalize(profile.category) != normalize(category)):
            continue
        category_entry = categories.get(dictionary_key(profile.category)) if profile else None
        issues = profile_issues(profile, category_entry, definitions)
        ready = not issues
        if state and ready != (state == 'ready'):
            continue
        attributes, conflicts = profile_attributes(profile.attributes, definitions) if profile else ({}, [])
        items.append({'id': template.id, 'name': template.name, 'cover_url': template.cover_url,
            'is_platform': template.is_platform, 'category': profile.category if profile else '',
            'category_localized_name': category_entry.localized_name if category_entry else None,
            'gender': profile.gender if profile else None, 'age_group': profile.age_group if profile else None,
            'material': attributes.get('材质', '') if '材质' not in conflicts else '',
            'attributes': {tag: value for tag, value in attributes.items() if tag not in (*CATEGORY_FIELDS, '材质')},
            'configuration_issues': issues, 'ready': ready})
    page = min(page, max(1, (len(items) + page_size - 1) // page_size))
    return {'items': items[(page - 1) * page_size:page * page_size], 'total': len(items), 'page': page, 'page_size': page_size}


def keyword_review_token(row):
    content = {key: value for key, value in keyword_data(row).items() if key != 'selected_count'}
    return digest([content, row.status, row.merged_into_id, row.updated_at.isoformat()])


@router.get('/title-keywords')
def keywords(platform: str = 'TikTok', site: str = 'MY', language: str = 'ms', search: str = '', category: str = '',
    status: Literal['', 'pending', 'enabled', 'disabled'] = '', tag: str = '', page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=1000),
    user: User = Depends(reader), db: Session = Depends(get_db)):
    market = market_for(db, user, platform, site, language)
    if not market:
        return {'items': [], 'total': 0, 'page': 1, 'page_size': page_size}
    query = select(TitleKeyword).where(TitleKeyword.market_id == market.id, TitleKeyword.merged_into_id.is_(None))
    if search.strip():
        from sqlalchemy import or_
        query = query.where(or_(TitleKeyword.phrase.icontains(search.strip(), autoescape=True),
                               TitleKeyword.translation.icontains(search.strip(), autoescape=True)))
    if status:
        query = query.where(TitleKeyword.status == status)
    if tag:
        query = query.where(TitleKeyword.tag == tag)
    # JSON 品类过滤跨 MySQL / SQLite 一致，在分页前处理。
    rows = db.scalars(query.order_by(TitleKeyword.id)).all()
    if category:
        rows = [r for r in rows if normalize(category) in map(normalize, r.categories)]
    page = min(page, max(1, (len(rows) + page_size - 1) // page_size))
    result = []
    for row in rows[(page-1)*page_size:page*page_size]:
        evidence = db.scalars(select(TitleEvidence).where(TitleEvidence.market_id == market.id, TitleEvidence.keyword_id == row.id)).all()
        latest = max((e.period for e in evidence), default=None)
        current = list({(normalize(e.source_name), e.source_product): e for e in sorted(evidence, key=lambda item: item.id)
                        if e.period == latest}.values())
        result.append({**keyword_data(row), 'status': row.status, 'review_token': keyword_review_token(row), 'adopted_count': row.adopted_count,
            'last_used_at': row.last_used_at.isoformat() + 'Z' if row.last_used_at else None,
            'title_frequency': len({(normalize(e.source_name), e.source_product, e.period) for e in evidence if e.source_kind == 'titles'}),
            'evidence_count': len(evidence), 'period': latest,
            'associated_sales': sum(e.metrics.get('销量', 0) for e in current) if any('销量' in e.metrics for e in current) else None,
            'search_metrics': [e.metrics for e in current if e.metrics.get('source')]})
    return {'items': result, 'total': len(rows), 'revision': market.revision, 'page': page, 'page_size': page_size}


@router.post('/title-keywords/{identity}/status')
@router.post('/title-keywords/{identity}/review', include_in_schema=False)
def set_keyword_status(identity: int, payload: KeywordStatusInput, user: User = Depends(admin), db: Session = Depends(get_db)):
    row = scoped_row(db, TitleKeyword, identity, user)
    market = db.scalar(select(TitleMarket).where(TitleMarket.id == row.market_id).with_for_update().execution_options(populate_existing=True))
    db.refresh(row)
    if row.merged_into_id:
        raise HTTPException(400, '已合并词不能修改启用状态')
    if payload.review_token != keyword_review_token(row):
        raise HTTPException(409, '关键词已变更，请刷新列表后重试')
    if payload.status == 'enabled':
        tag_entry(db, market, row.tag)
        category_values(db, market, row.categories)
    row.status = payload.status
    row.updated_at = datetime.utcnow()
    market.revision += 1
    market.updated_at = datetime.utcnow()
    db.commit()
    return {**keyword_data(row), 'status': row.status, 'review_token': keyword_review_token(row)}


@router.patch('/title-keywords/{identity}')
def edit_keyword(identity: int, payload: KeywordInput, user: User = Depends(admin), db: Session = Depends(get_db)):
    row = scoped_row(db, TitleKeyword, identity, user)
    market = db.scalar(select(TitleMarket).where(TitleMarket.id == row.market_id).with_for_update().execution_options(populate_existing=True))
    if row.merged_into_id:
        raise HTTPException(400, '已合并词不能编辑')
    data = payload.model_dump(exclude_unset=True)
    if any(v is None for v in data.values()):
        raise HTTPException(400, '编辑字段不能为 null')
    definition = tag_entry(db, market, data.get('tag', row.tag), allow_disabled=row.tag)
    if 'tag' in data:
        data['tag'] = definition.name
    for field in ('phrase', 'translation'):
        if field in data and not data[field].strip():
            raise HTTPException(400, '词语和释义不能为空')
    for field in ('categories', 'synonyms'):
        if any(not isinstance(v, str) or not v.strip() or len(v) > 255 for v in data.get(field, [])):
            raise HTTPException(400, '品类或同义表达无效')
    if 'categories' in data:
        data['categories'] = category_values(db, market, data['categories'], allow_disabled=row.categories)
    if 'phrase' in data:
        import re
        if re.search(r'[\u3400-\u9fff]', data['phrase']):
            raise HTTPException(400, '马来语词语不能包含中文')
    conflicts = set(data.get('conflicts', row.conflicts))
    if row.id in conflicts or conflicts != set(db.scalars(select(TitleKeyword.id).where(
        TitleKeyword.market_id == market.id, TitleKeyword.id.in_(conflicts), TitleKeyword.merged_into_id.is_(None)))):
        raise HTTPException(400, '冲突词须来自同一词库且不能引用自身')
    new_hash = digest([normalize(data.get('phrase', row.phrase)), data.get('tag', row.tag)])
    if db.scalar(select(TitleKeyword.id).where(TitleKeyword.market_id == market.id,
        TitleKeyword.identity_hash == new_hash, TitleKeyword.id != row.id)):
        raise HTTPException(409, '标准词已存在，请使用合并功能')
    for key, value in data.items():
        setattr(row, key, value)
    row.identity_hash = new_hash
    row.updated_at = datetime.utcnow()
    market.revision += 1
    market.updated_at = datetime.utcnow()
    db.commit()
    return keyword_data(row)


@router.post('/title-keywords/{identity}/merge')
def merge_keyword(identity: int, payload: MergeInput, user: User = Depends(admin), db: Session = Depends(get_db)):
    source = scoped_row(db, TitleKeyword, identity, user)
    target = scoped_row(db, TitleKeyword, payload.target_id, user)
    market = db.scalar(select(TitleMarket).where(TitleMarket.id == source.market_id).with_for_update().execution_options(populate_existing=True))
    if source.id == target.id or source.market_id != target.market_id or source.tag != target.tag or source.merged_into_id or target.merged_into_id:
        raise HTTPException(400, '只能合并同一词库、相同属性分类且未合并的词')
    target.synonyms = sorted(set(target.synonyms + source.synonyms + [source.phrase]))
    target.categories = sorted(set(target.categories + source.categories))
    target.conflicts = sorted((set(target.conflicts) | set(source.conflicts)) - {source.id, target.id})
    target.selected_count += source.selected_count
    target.adopted_count += source.adopted_count
    target.is_borrowed = target.is_borrowed or source.is_borrowed
    if source.priority == 'forbidden' or target.priority == 'forbidden':
        target.priority = 'forbidden'
    elif source.priority == 'preferred':
        target.priority = 'preferred'
    db.execute(update(TitleEvidence).where(TitleEvidence.keyword_id == source.id, TitleEvidence.market_id == market.id).values(keyword_id=target.id))
    for profile in db.scalars(select(TitleTemplateProfile).where(TitleTemplateProfile.market_id == market.id)):
        for key in ('locked_keyword_ids', 'forbidden_keyword_ids'):
            setattr(profile, key, list(dict.fromkeys(target.id if i == source.id else i for i in getattr(profile, key))))
        if set(profile.locked_keyword_ids) & set(profile.forbidden_keyword_ids):
            raise HTTPException(400, '合并会使模板必用词与禁用词冲突，请先调整模板配置')
    for other in db.scalars(select(TitleKeyword).where(TitleKeyword.market_id == market.id,
        TitleKeyword.id.not_in([source.id, target.id]))):
        if source.id in other.conflicts:
            other.conflicts = sorted({target.id if i == source.id else i for i in other.conflicts} - {other.id})
    source.merged_into_id = target.id
    source.status = 'disabled'
    market.revision += 1
    market.updated_at = datetime.utcnow()
    db.commit()
    return {'merged_into_id': target.id}


@router.get('/title-keywords/{identity}/evidence')
def keyword_evidence(identity: int, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=1000),
                     user: User = Depends(reader), db: Session = Depends(get_db)):
    row = scoped_row(db, TitleKeyword, identity, user)
    query = select(TitleEvidence).where(TitleEvidence.market_id == row.market_id, TitleEvidence.keyword_id == row.id)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    page = min(page, max(1, (total + page_size - 1) // page_size))
    evidence = db.scalars(query.order_by(TitleEvidence.id.desc()).offset((page-1)*page_size).limit(page_size)).all()
    imports = {item.id: item for item in db.execute(select(TitleTask.id,
        TitleTask.snapshot['note'].as_string().label('note'), TitleTask.snapshot['period_basis'].as_string().label('period_basis'))
        .where(TitleTask.market_id == row.market_id, TitleTask.id.in_({e.import_id for e in evidence})))}
    return {'total': total, 'page': page, 'page_size': page_size, 'items': [{'original_title': e.original_title, 'original_phrase': e.original_phrase,
        'position': e.position, 'source_name': e.source_name, 'source_product': e.source_product,
        'source_url': e.source_url, 'source_kind': e.source_kind, 'period': e.period, 'metrics': e.metrics, 'import_id': e.import_id,
        'period_basis': imports[e.import_id].period_basis or 'source_period' if e.import_id in imports else 'source_period',
        'note': imports[e.import_id].note or '' if e.import_id in imports else ''}
        for e in evidence]}


@router.get('/title-import-template')
def import_template(kind: Literal['titles', 'keywords'] = 'titles', user: User = Depends(admin)):
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow([*TITLE_COLUMN_NAMES.values(), *IMPORT_OPTIONAL_COLUMNS] if kind == 'titles'
                    else [*KEYWORD_COLUMN_NAMES.values(), *IMPORT_OPTIONAL_COLUMNS])
    return Response(stream.getvalue().encode('utf-8-sig'), media_type='text/csv',
                    headers={'Content-Disposition': f'attachment; filename="title-{kind}.csv"'})


@router.post('/title-imports')
async def preview_import(file: UploadFile = File(...), kind: Literal['titles', 'keywords'] = Form('titles'),
    note: str = Form(default='', max_length=500),
    source_name: str | None = Form(default=None, min_length=1, max_length=120),
    period: str | None = Form(default=None, pattern=r'^\d{4}-\d{2}-\d{2}$'),
    platform: Literal['TikTok', 'Shopee'] = Form('TikTok'), site: str = Form('MY'), language: str = Form('ms'),
    user: User = Depends(admin), db: Session = Depends(get_db)):
    legacy_metadata = source_name is not None or period is not None
    if source_name is not None and not source_name.strip():
        raise HTTPException(400, '数据来源不能为空')
    if period is not None:
        try:
            datetime.strptime(period, '%Y-%m-%d')
        except ValueError as exc:
            raise HTTPException(400, '数据日期无效') from exc
    period_basis = 'source_period' if period is not None else 'import_date'
    source_name = source_name.strip() if source_name is not None else '手动导入'
    period = period or datetime.now(ZoneInfo('Asia/Hong_Kong')).date().isoformat()
    content = await file.read(MAX_BYTES + 1)
    market = market_for(db, user, platform, site, language, create=True, lock=True)
    tag_definitions = [row for row in dictionary_entries(db, market.id, 'tag') if row.enabled]
    allowed_tags = [*CATEGORY_FIELDS, *(row.name for row in tag_definitions)]
    rows = parse_file(content, file.filename or '', kind, allowed_tags=allowed_tags)
    from .title_import import split_values
    category_states = category_index(db, market.id)
    for row in rows:
        categories = [row['values']['商品品类']] if kind == 'titles' else split_values(row['values']['适用品类'])
        for name in categories:
            entry = category_states.get(dictionary_key(name))
            if entry and not entry.enabled:
                raise HTTPException(400, f'产品分类“{entry.name}”已停用，请先启用')
    # 新页面按文件内容与导入类型去重，备注和上传日期变化不重复提词；旧客户端保留原周期规则。
    key = digest([content.hex(), kind, normalize(source_name), period]) if legacy_metadata else digest(['title-import-v2', content.hex(), kind])
    previous = db.scalar(select(TitleTask).where(TitleTask.market_id == market.id, TitleTask.request_key == key))
    if previous:
        return {'id': previous.id, 'state': previous.state, 'duplicate': True, 'rows': len(rows), 'preview': rows[:20],
                'note': previous.snapshot.get('note', ''), 'category_resolution': category_summary(db, previous)}
    task = TitleTask(market_id=market.id, user_id=user.id, kind='import', request_key=key, request_hash=key,
        state='preview', snapshot={'rows': rows, 'allowed_tags': allowed_tags,
            'tag_semantics': {**{field: field for field in CATEGORY_FIELDS}, **{row.name: row.semantic_tag for row in tag_definitions}},
            'kind': kind, 'source_name': source_name, 'period': period, 'period_basis': period_basis, 'note': note.strip(),
            'filename': (file.filename or '')[:255]}, progress={'total': len(rows), 'completed': 0})
    db.add(task)
    db.flush()
    resolution = category_summary(db, task)
    db.commit()
    return {'id': task.id, 'state': task.state, 'duplicate': False, 'rows': len(rows), 'preview': rows[:20],
        'note': task.snapshot['note'], 'category_resolution': resolution}


@router.get('/title-tasks')
def tasks(platform: str = 'TikTok', kind: Literal['import', 'batch'] = 'import', page: int = Query(1, ge=1),
          page_size: int = Query(30, ge=1, le=1000),
          user: User = Depends(reader), db: Session = Depends(get_db)):
    market = market_for(db, user, platform)
    if not market:
        return {'items': [], 'total': 0, 'page': 1, 'page_size': page_size}
    query = select(TitleTask).where(TitleTask.market_id == market.id, TitleTask.kind == kind)
    if user.role != Role.COMPANY_ADMIN:
        query = query.where(TitleTask.user_id == user.id)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    page = min(page, max(1, (total + page_size - 1) // page_size))
    return {'total': total, 'page': page, 'page_size': page_size,
        'items': [task_payload(t) for t in db.scalars(query.order_by(TitleTask.id.desc()).offset((page-1)*page_size).limit(page_size))]}


def task_payload(task, offset=0, limit=100, db=None, category='', tag='', imported=None):
    result = copy.deepcopy(task.result)
    resolution = category_summary(db, task) if task.kind == 'import' and db is not None else None
    confirmed_ids = set(result.get('selections', []))
    if task.kind == 'import':
        result['imported_total'] = len(confirmed_ids)
    if task.kind == 'import' and result.get('word_total') and db is not None:
        query = select(TitleImportWord).where(TitleImportWord.task_id == task.id)
        # 下拉选项来自整个任务；先在数据库内筛选，再统计和分页。
        groups = db.execute(select(TitleImportWord.word['categories'], TitleImportWord.word['imported_categories'])
            .where(TitleImportWord.task_id == task.id).distinct()).all()
        result['filter_categories'] = sorted({name for original, saved in groups
            for name in (saved if saved is not None else display_categories(original, resolution))})
        result['filter_tags'] = sorted(db.scalars(select(TitleImportWord.word['tag'].as_string())
            .where(TitleImportWord.task_id == task.id).distinct()).all())
        if category:
            original_names = {name for original, saved in groups if saved is None for name in original
                if category in display_categories([name], resolution)}
            def contains_any(field, names):
                if not names:
                    return False
                if db.get_bind().dialect.name == 'mysql':
                    return or_(*(func.json_contains(field, json.dumps(name)) for name in names))
                items = func.json_each(field).table_valued('value')
                return select(1).select_from(items).where(items.c.value.in_(names)).correlate(TitleImportWord).exists()
            query = query.where(or_(contains_any(TitleImportWord.word['imported_categories'], [category]),
                TitleImportWord.word['imported_categories'].as_string().is_(None) &
                contains_any(TitleImportWord.word['categories'], original_names)))
        if tag:
            query = query.where(TitleImportWord.word['tag'].as_string() == tag)
        if imported is not None:
            query = query.where(TitleImportWord.id.in_(confirmed_ids) if imported else TitleImportWord.id.not_in(confirmed_ids))
        result['filtered_total'] = db.scalar(select(func.count()).select_from(query.subquery()))
        offset = min(offset // limit, max(0, (result['filtered_total'] - 1) // limit)) * limit
        result['offset'] = offset
        candidates = db.scalars(query.order_by(TitleImportWord.id).offset(offset).limit(limit)).all()
        hashes = [digest([normalize(item.word['phrase']), item.word['tag']]) for item in candidates]
        existing = {word.identity_hash: word for word in db.scalars(select(TitleKeyword).where(
            TitleKeyword.market_id == task.market_id, TitleKeyword.identity_hash.in_(hashes)))}
        original_rows = {row['row']: row['values'] for row in task.snapshot['rows']}
        result['words'] = []
        for item, identity_hash in zip(candidates, hashes):
            previous = existing.get(identity_hash)
            original = original_rows[item.row_number]
            result['words'].append({**item.word, 'original_categories': item.word['categories'],
                'categories': item.word.get('imported_categories', display_categories(item.word['categories'], resolution)),
                'index': item.id, 'original_title': original.get('原标题', item.word['phrase']),
                'source_product': original.get('商品ID'), 'existing_code': previous.code if previous else None,
                'imported': item.id in confirmed_ids})
    return {'id': task.id, 'kind': task.kind, 'state': task.state, 'progress': task.progress, 'error': task.error,
        'result': result, 'created_at': task.created_at.isoformat()+'Z', 'filename': task.snapshot.get('filename'),
        'source_name': task.snapshot.get('source_name'), 'period': task.snapshot.get('period'),
        'period_basis': task.snapshot.get('period_basis', 'source_period'), 'note': task.snapshot.get('note', ''),
        'category_resolution': resolution,
        'import_kind': task.snapshot.get('kind') if task.kind == 'import' else None}


@router.get('/title-tasks/{identity}')
def get_task(identity: int, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000),
             category: str = '', tag: str = '', imported: bool | None = None,
             user: User = Depends(reader), db: Session = Depends(get_db)):
    return task_payload(task_for(db, identity, user), offset, limit, db=db, category=category, tag=tag, imported=imported)


@router.post('/title-tasks/{identity}/start')
def start_task(identity: int, user: User = Depends(admin), db: Session = Depends(get_db)):
    task = task_for(db, identity, user)
    db.scalar(select(TitleMarket).where(TitleMarket.id == task.market_id).with_for_update().execution_options(populate_existing=True))
    task = db.scalar(select(TitleTask).options(undefer(TitleTask.snapshot)).where(TitleTask.id == task.id).with_for_update().execution_options(populate_existing=True))
    if task.kind != 'import' or task.state != 'preview':
        raise HTTPException(409, '只有预览中的导入任务可开始提词')
    resolved = validate_choices(db, task, task.snapshot.get('category_resolution', []))
    task.snapshot = {**task.snapshot, 'category_resolution': [
        {key: item.get(key) for key in ('source_key', 'target_id', 'new_name', 'save_alias')}
        for item in resolved.values()]}
    if task.snapshot['kind'] == 'titles':
        require_title_credential(db, task.user_id, user.company_id)
    changed = db.execute(update(TitleTask).where(TitleTask.id == task.id, TitleTask.state == 'preview').values(state='queued'))
    if not changed.rowcount:
        raise HTTPException(409, '任务状态已变化，请刷新')
    db.commit()
    return task_payload(task)


@router.put('/title-imports/{identity}/categories')
@category_conflicts
def resolve_import_categories(identity: int, payload: CategoryResolutionInput,
                              user: User = Depends(admin), db: Session = Depends(get_db)):
    task = task_for(db, identity, user)
    db.scalar(select(TitleMarket).where(TitleMarket.id == task.market_id).with_for_update().execution_options(populate_existing=True))
    task = db.scalar(select(TitleTask).options(undefer(TitleTask.snapshot)).where(TitleTask.id == task.id).with_for_update().execution_options(populate_existing=True))
    if task.kind != 'import' or task.state not in {'preview', 'review', 'completed', 'failed', 'cancelled', 'completed_with_errors'}:
        raise HTTPException(409, '请等待提词完成后再修改分类归类方案')
    for choice in payload.choices:
        if bool(choice.target_id) == bool(choice.new_name):
            raise HTTPException(400, '每项必须选择一个已有分类或填写一个新分类名称')
    save_resolution(db, task, [item.model_dump() for item in payload.choices], payload.token)
    db.commit()
    return category_summary(db, task)


@router.post('/title-imports/{identity}/confirm')
@category_conflicts
def approve_import(identity: int, payload: ConfirmInput, user: User = Depends(admin), db: Session = Depends(get_db)):
    task = task_for(db, identity, user)
    db.scalar(select(TitleMarket).where(TitleMarket.id == task.market_id).with_for_update().execution_options(populate_existing=True))
    task = db.scalar(select(TitleTask).options(undefer(TitleTask.snapshot)).where(TitleTask.id == task.id).with_for_update().execution_options(populate_existing=True))
    if task.kind != 'import' or task.state not in {'review', 'completed'}:
        raise HTTPException(409, '任务尚未完成提词')
    counts = confirm_import(db, task, payload.selections)
    db.commit()
    return counts


@router.post('/title-tasks/{identity}/cancel')
def cancel_task(identity: int, user: User = Depends(reader), db: Session = Depends(get_db)):
    task = task_for(db, identity, user)
    if task.state in {'queued', 'running', 'preview'}:
        db.execute(update(TitleTask).where(TitleTask.id == task.id, TitleTask.state.in_(['queued', 'running', 'preview']))
                   .values(state='cancelled', lease_owner=None, lease_expires_at=None))
        db.commit()
    return {'id': task.id, 'state': db.get(TitleTask, task.id, populate_existing=True).state}


@router.post('/title-tasks/{identity}/retry')
def retry_task(identity: int, user: User = Depends(reader), db: Session = Depends(get_db)):
    task = task_for(db, identity, user)
    if task.kind == 'import' and user.role != Role.COMPANY_ADMIN:
        raise HTTPException(403, '只有管理员可以重试导入')
    if task.kind == 'import':
        db.scalar(select(TitleMarket).where(TitleMarket.id == task.market_id).with_for_update().execution_options(populate_existing=True))
        task = db.scalar(select(TitleTask).options(undefer(TitleTask.snapshot)).where(TitleTask.id == task.id).with_for_update().execution_options(populate_existing=True))
        resolved = validate_choices(db, task, task.snapshot.get('category_resolution', []))
        task.snapshot = {**task.snapshot, 'category_resolution': [
            {key: item.get(key) for key in ('source_key', 'target_id', 'new_name', 'save_alias')}
            for item in resolved.values()]}
    if task.state not in {'failed', 'cancelled', 'completed_with_errors'} and not (task.state in {'review', 'completed'} and task.result.get('failed_rows')):
        raise HTTPException(409, '当前任务不可重试')
    changed = db.execute(update(TitleTask).where(TitleTask.id == task.id, TitleTask.state == task.state)
        .values(state='queued', error=None, lease_owner=None, lease_expires_at=None))
    if not changed.rowcount:
        raise HTTPException(409, '任务状态已变化，请刷新')
    db.commit()
    return task_payload(task)


@router.post('/title-generation-jobs')
def create_job(payload: JobInput, user: User = Depends(reader), db: Session = Depends(get_db)):
    from .main import get_company_template, resolve_product_library_sources, library_record_image
    market = market_for(db, user, payload.platform, payload.site, payload.language, create=True, lock=True)
    request_hash = digest(payload.model_dump(exclude={'request_key'}))
    previous = db.scalar(select(TitleTask).where(TitleTask.market_id == market.id, TitleTask.request_key == digest([user.id, payload.request_key])))
    if previous:
        if previous.request_hash != request_hash or previous.user_id != user.id:
            raise HTTPException(409, '请求键已用于不同任务')
        return task_payload(previous)
    template = get_company_template(db, user, payload.template_id)
    if len({g.key for g in payload.groups}) != len(payload.groups):
        raise HTTPException(400, '商品组标识不能重复')
    if payload.from_library:
        records = resolve_product_library_sources(db, user, [g.source for g in payload.groups])
    else:
        if any(g.source.source_type != 'material' for g in payload.groups):
            raise HTTPException(400, '素材库任务只能使用素材')
        ids = [g.source.id for g in payload.groups]
        if len(ids) != len(set(ids)):
            raise HTTPException(400, '同一首图素材不能重复用于多个商品组')
        query = select(MaterialAsset).where(MaterialAsset.id.in_(ids), MaterialAsset.company_id == user.company_id)
        if user.role != Role.COMPANY_ADMIN:
            query = query.where(MaterialAsset.claimed_by == user.id)
        by_id = {r.id: r for r in db.scalars(query)}
        if set(ids) != set(by_id):
            raise HTTPException(404, '素材不存在或无权使用')
        records = [by_id[i] for i in ids]
    if any(r.template_id != template.id or not r.sku or not library_record_image(r).strip() for r in records):
        raise HTTPException(400, '商品组须属于所选模板且包含 SKU 和首图')
    require_title_credential(db, user.id, user.company_id)
    snapshot = profile_snapshot(db, market, template.id)
    task = TitleTask(market_id=market.id, user_id=user.id, kind='batch', state='queued',
        request_key=digest([user.id, payload.request_key]), request_hash=request_hash,
        snapshot={'profile': snapshot, 'groups': []}, progress={'total': len(records), 'completed': 0})
    db.add(task)
    db.flush()
    groups = []
    for group, source in zip(payload.groups, records):
        record = create_record(db, market, user.id, {**snapshot, 'additional_requirements': group.additional_requirements},
            library_record_image(source), ['batch', task.id, group.key], task_id=task.id)
        groups.append({'key': group.key, 'generation_id': record.id})
    task.snapshot = {**task.snapshot, 'groups': groups}
    db.commit()
    return task_payload(task)


async def generate_single(db, user, template, image_url, payload):
    market = market_for(db, user, payload.platform, payload.site, payload.language, create=True, lock=True)
    snapshot = profile_snapshot(db, market, template.id)
    snapshot['additional_requirements'] = payload.additional_requirements
    import secrets
    record = create_record(db, market, user.id, snapshot, image_url, ['single', user.id, payload.request_key or secrets.token_hex(16)])
    db.commit()
    return await generate_record(db, record.id)


@router.get('/title-statistics')
def statistics(platform: str = 'TikTok', user: User = Depends(reader), db: Session = Depends(get_db)):
    market = market_for(db, user, platform)
    if not market:
        return {'generated': 0, 'adopted': 0, 'manual': 0, 'high_similarity': 0, 'attempts': 0}
    query = select(TitleRecord).where(TitleRecord.market_id == market.id)
    if user.role != Role.COMPANY_ADMIN:
        query = query.where(TitleRecord.user_id == user.id)
    rows = db.scalars(query).all()
    return {'generated': sum(bool(r.title) and r.source == 'ai' for r in rows),
        'adopted': sum(bool(r.adopted_at) and r.source == 'ai' for r in rows),
        'manual': sum(r.source == 'manual' for r in rows), 'high_similarity': sum(any('高度相似' in w for w in r.warnings) for r in rows),
        'attempts': sum(r.attempts for r in rows), 'coverage_insufficient': sum(any('覆盖不足' in w for w in r.warnings) for r in rows)}
