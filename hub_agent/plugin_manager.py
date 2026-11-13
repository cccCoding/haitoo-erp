"""只加载已固定版本且通过签名的站点适配插件。"""
import importlib.util
import json
import sys
from pathlib import Path
from package_security import verify_manifest


def load_plugin(root,keys,platform,arch):
    root=Path(root);pointer=root/'current-plugin.json'
    if not pointer.exists():return None
    info=json.loads(pointer.read_text(encoding="utf-8"))
    manifest=verify_manifest(info['manifest'],keys,platform,arch)
    if manifest['kind']!='plugin':raise ValueError('插件类型错误')
    directory=root/'plugins'/manifest['sha256']
    import hashlib
    for name,checksum in manifest['files'].items():
        if hashlib.sha256((directory/name).read_bytes()).hexdigest()!=checksum:raise ValueError('已安装插件文件已变化')
    entry=directory/manifest['entrypoint']
    module_name='haitoo_signed_'+manifest['sha256']
    spec=importlib.util.spec_from_file_location(module_name,entry,submodule_search_locations=[str(directory)])
    module=sys.modules.get(module_name)
    if module is None:
        module=importlib.util.module_from_spec(spec);sys.modules[module_name]=module
        try:spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(module_name,None)
            raise
    if not isinstance(getattr(module,'CAPABILITIES',None),dict):raise ValueError('插件接口不完整')
    for task,sites in module.CAPABILITIES.items():
        if task not in {'shop.collect','listing.catalog','promotion.flash_sale.renew','promotion.flash_sale.collect'} or not isinstance(sites,list) or not set(sites)<={'MY','ID'}:raise ValueError('插件声明未知能力')
        if not callable(getattr(module,{'shop.collect':'collect','listing.catalog':'upload','promotion.flash_sale.renew':'renew_flash_sales','promotion.flash_sale.collect':'collect_flash_sales'}[task],None)):raise ValueError('插件声明能力缺少实现')
    module.VERSION=manifest['version']
    module.DIGEST=manifest['sha256']
    return module
