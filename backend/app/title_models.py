"""站点词库、证据、生成快照和持久化标题任务。"""
from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base


class TitleMarket(Base):
    __tablename__ = "title_markets"
    __table_args__ = (UniqueConstraint("company_id", "platform", "site", "language", name="uq_title_market"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(index=True)
    platform: Mapped[str] = mapped_column(String(20))
    site: Mapped[str] = mapped_column(String(10))
    language: Mapped[str] = mapped_column(String(10))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    revision: Mapped[int] = mapped_column(default=1)
    next_code: Mapped[int] = mapped_column(default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TitleTemplateProfile(Base):
    __tablename__ = "title_template_profiles"
    __table_args__ = (UniqueConstraint("market_id", "template_id", name="uq_title_template_profile"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    market_id: Mapped[int] = mapped_column(index=True)
    template_id: Mapped[int] = mapped_column(index=True)
    category: Mapped[str] = mapped_column(String(255))
    gender: Mapped[str | None] = mapped_column(String(10), nullable=True)
    age_group: Mapped[str | None] = mapped_column(String(10), nullable=True)
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    category_names: Mapped[list] = mapped_column(JSON, default=list)
    locked_keyword_ids: Mapped[list] = mapped_column(JSON, default=list)
    forbidden_keyword_ids: Mapped[list] = mapped_column(JSON, default=list)
    fallback_title: Mapped[str | None] = mapped_column(String(220), nullable=True)
    fallback_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TitleDictionaryEntry(Base):
    __tablename__ = 'title_dictionary_entries'
    __table_args__ = (UniqueConstraint('market_id', 'kind', 'name_key', name='uq_title_dictionary_name'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    market_id: Mapped[int] = mapped_column(index=True)
    kind: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(255))
    name_key: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(String(500), default='')
    gender: Mapped[str | None] = mapped_column(String(10), nullable=True)
    localized_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    semantic_tag: Mapped[str | None] = mapped_column(String(40), nullable=True)
    built_in: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    merged_into_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    names: Mapped[list['TitleCategoryName']] = relationship(cascade='all, delete-orphan', lazy='selectin')
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TitleCategoryName(Base):
    __tablename__ = 'title_category_names'
    __table_args__ = (UniqueConstraint('market_id', 'name_key', name='uq_title_category_name'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    market_id: Mapped[int] = mapped_column(index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey('title_dictionary_entries.id'), index=True)
    name: Mapped[str] = mapped_column(String(255))
    name_key: Mapped[str] = mapped_column(String(64))


class TitleCategoryMerge(Base):
    __tablename__ = 'title_category_merges'
    __table_args__ = (UniqueConstraint('market_id', 'preview_token', name='uq_title_category_merge'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    market_id: Mapped[int] = mapped_column(index=True)
    user_id: Mapped[int] = mapped_column(index=True)
    target_id: Mapped[int] = mapped_column(Integer)
    source_ids: Mapped[list] = mapped_column(JSON)
    preview_token: Mapped[str] = mapped_column(String(64))
    summary: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TitleKeyword(Base):
    __tablename__ = "title_keywords"
    __table_args__ = (UniqueConstraint("market_id", "identity_hash", name="uq_title_keyword_identity"),
        UniqueConstraint("market_id", "code", name="uq_title_keyword_code"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    market_id: Mapped[int] = mapped_column(index=True)
    code: Mapped[str] = mapped_column(String(24))
    phrase: Mapped[str] = mapped_column(String(160))
    translation: Mapped[str] = mapped_column(String(255))
    identity_hash: Mapped[str] = mapped_column(String(64))
    tag: Mapped[str] = mapped_column(String(40))
    categories: Mapped[list] = mapped_column(JSON, default=list)
    synonyms: Mapped[list] = mapped_column(JSON, default=list)
    conflicts: Mapped[list] = mapped_column(JSON, default=list)
    is_borrowed: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="enabled")
    priority: Mapped[str] = mapped_column(String(20), default="normal")
    selected_count: Mapped[int] = mapped_column(default=0)
    adopted_count: Mapped[int] = mapped_column(default=0)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    merged_into_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TitleEvidence(Base):
    __tablename__ = "title_evidence"
    __table_args__ = (UniqueConstraint("market_id", "observation_hash", name="uq_title_evidence_observation"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    market_id: Mapped[int] = mapped_column(index=True)
    keyword_id: Mapped[int] = mapped_column(index=True)
    import_id: Mapped[int] = mapped_column(index=True)
    observation_hash: Mapped[str] = mapped_column(String(64))
    original_title: Mapped[str] = mapped_column(Text)
    original_phrase: Mapped[str] = mapped_column(String(160))
    source_name: Mapped[str] = mapped_column(String(120))
    source_product: Mapped[str] = mapped_column(String(255))
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    period: Mapped[str] = mapped_column(String(40))
    source_kind: Mapped[str] = mapped_column(String(20))
    position: Mapped[int] = mapped_column(default=0)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)


class TitleTask(Base):
    __tablename__ = "title_tasks"
    __table_args__ = (UniqueConstraint("market_id", "request_key", name="uq_title_task_request"),
        Index("ix_title_task_queue", "state", "lease_expires_at", "id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    market_id: Mapped[int] = mapped_column(index=True)
    user_id: Mapped[int] = mapped_column(index=True)
    kind: Mapped[str] = mapped_column(String(20))
    request_key: Mapped[str] = mapped_column(String(64))
    request_hash: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(24), default="preview")
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict, deferred=True)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    progress: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    lease_owner: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TitleRecord(Base):
    __tablename__ = "title_records"
    __table_args__ = (UniqueConstraint("market_id", "request_key", name="uq_title_record_request"),
        Index("ix_title_record_history", "market_id", "category", "adopted_at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    market_id: Mapped[int] = mapped_column(index=True)
    user_id: Mapped[int] = mapped_column(index=True)
    template_id: Mapped[int] = mapped_column(index=True)
    task_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    draft_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    request_key: Mapped[str] = mapped_column(String(64))
    category: Mapped[str] = mapped_column(String(255))
    image_url: Mapped[str] = mapped_column(Text)
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    facts: Mapped[dict] = mapped_column(JSON, default=dict)
    selected_keywords: Mapped[list] = mapped_column(JSON, default=list)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    attempts: Mapped[int] = mapped_column(default=0)
    state: Mapped[str] = mapped_column(String(20), default="pending")
    source: Mapped[str] = mapped_column(String(20), default="ai")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    lease_owner: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    adopted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class TitleAttributeCache(Base):
    __tablename__ = "title_attribute_cache"
    __table_args__ = (UniqueConstraint("market_id", "cache_key", name="uq_title_attribute_cache"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    market_id: Mapped[int] = mapped_column(index=True)
    cache_key: Mapped[str] = mapped_column(String(64))
    facts: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TitleImportWord(Base):
    __tablename__ = 'title_import_words'
    __table_args__ = (UniqueConstraint('task_id', 'row_number', 'identity_hash', name='uq_title_import_word'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(index=True)
    row_number: Mapped[int] = mapped_column()
    identity_hash: Mapped[str] = mapped_column(String(64))
    word: Mapped[dict] = mapped_column(JSON)
