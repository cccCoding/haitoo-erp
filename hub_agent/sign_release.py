"""离线签名发布包；私钥由发布者指定，不上传ERP。"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import zipfile
import stat
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from package_security import canonical,safe_path,version_tuple


def main():
    p=argparse.ArgumentParser(description='离线签名Agent或插件ZIP')
    for name in ('package','key','key-id','version','platform','arch','kind','entrypoint','output'):p.add_argument('--'+name,required=True)
    p.add_argument('--installer');p.add_argument('--min-launcher-version',default='5.2.0')
    a=p.parse_args();version_tuple(a.version)
    key=serialization.load_pem_private_key(Path(a.key).read_bytes(),password=None)
    if not isinstance(key,Ed25519PrivateKey):raise ValueError('需要Ed25519私钥')
    with zipfile.ZipFile(a.package) as z:
        files={}
        for i in z.infolist():
            safe_path(i.filename)
            if not i.is_dir():
                if i.filename in files:raise ValueError('重复文件')
                files[i.filename]=hashlib.sha256(z.read(i)).hexdigest()
    if a.kind=='agent':
        with zipfile.ZipFile(a.package) as z:
            versions=[json.loads(z.read(name))['version'] for name in files if (name=='agent-version.json' or name.endswith('/agent-version.json')) and not stat.S_ISLNK(z.getinfo(name).external_attr>>16)]
        if not versions or any(version!=a.version for version in versions):raise ValueError('Agent清单版本必须与包内agent-version.json一致')
    package=Path(a.package).read_bytes()
    manifest={'kind':a.kind,'version':a.version,'platform':a.platform,'arch':a.arch,'sha256':hashlib.sha256(package).hexdigest(),
        'size':len(package),'key_id':a.key_id,'protocol_min':5,'protocol_max':5,'entrypoint':a.entrypoint,'files':files}
    with zipfile.ZipFile(a.package) as z:
        links={i.filename:z.read(i).decode('utf-8') for i in z.infolist() if stat.S_ISLNK(i.external_attr>>16)}
    if links:
        if a.platform!='macos':raise ValueError('仅 macOS 发布包允许内部链接')
        from package_security import safe_link
        for name,value in links.items():safe_link(name,value)
        manifest['symlinks']=links
    if a.installer:
        public=base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)).decode()
        with zipfile.ZipFile(a.package) as z:
            stores=[json.loads(z.read(name)) for name in files if (name=='trusted_keys.json' or name.endswith('/trusted_keys.json')) and not stat.S_ISLNK(z.getinfo(name).external_attr>>16)]
        if not stores or any(store.get(a.key_id)!=public for store in stores):raise ValueError('正式包必须内置信任当前发布签名的公钥')
        installer=Path(a.installer)
        suffix='exe' if a.platform=='windows' else 'dmg'
        expected=f'HaitooHubAgent-{a.platform}-{a.arch}-{a.version}.{suffix}'
        if installer.name!=expected:raise ValueError('安装包名称须为 '+expected)
        with installer.open('rb') as stream:checksum=hashlib.file_digest(stream,'sha256').hexdigest()
        manifest['installer']={'filename':installer.name,'size':installer.stat().st_size,'sha256':checksum}
        version_tuple(a.min_launcher_version);manifest['min_launcher_version']=a.min_launcher_version
    manifest['signature']=base64.b64encode(key.sign(canonical(manifest))).decode()
    Path(a.output).write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':main()
