"""标题词库支持的站点和语言；不根据相近语言自动回退。"""
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, model_validator


MARKETS = {
    'MY': {'language': 'ms', 'site_name': '马来西亚', 'language_name': '马来语',
           'model_language': 'Bahasa Melayu Malaysia'},
    'ID': {'language': 'id', 'site_name': '印尼', 'language_name': '印尼语',
           'model_language': 'Bahasa Indonesia'},
}


def check_market(platform='TikTok', site='MY', language='ms'):
    if platform not in {'TikTok', 'Shopee'} or site not in MARKETS or MARKETS[site]['language'] != language:
        raise HTTPException(400, '词库仅支持马来西亚马来语（MY/ms）和印尼印尼语（ID/id）')


class TitleMarketSelection(BaseModel):
    site: Literal['MY', 'ID'] = 'MY'
    language: Literal['ms', 'id'] = 'ms'

    @model_validator(mode='after')
    def valid_market_pair(self):
        if MARKETS[self.site]['language'] != self.language:
            raise ValueError('站点和语言须匹配：MY/ms 或 ID/id')
        return self


def market_labels(site='MY'):
    return MARKETS[site]


def localized_value(fact):
    """历史事实使用 ms 字段，新事实统一保存 localized_value。"""
    return fact.get('localized_value', fact.get('ms', ''))
