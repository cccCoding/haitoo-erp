"""仅在MY真实页面验收通过后制作并签名发布；不自动加载此模板。"""
from plugins.flash_sales import renew_flash_sales, collect_flash_sales

CAPABILITIES = {'promotion.flash_sale.renew':['MY'],'promotion.flash_sale.collect':['MY']}
