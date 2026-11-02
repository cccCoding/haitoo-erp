"""离线签名发布包；私钥由发布者指定，不上传ERP。"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import zipfile
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from package_security import canonical,safe_path,version_tuple


def main():
    p=argparse.ArgumentParser(description='离线签名Agent或插件ZIP')
    for name in ('package','key','key-id','version','platform','arch','kind','entrypoint','output'):p.add_argument('--'+name,required=True)
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
            versions=[json.loads(z.read(name))['version'] for name in files if name=='agent-version.json' or name.endswith('/agent-version.json')]
        if not versions or any(version!=a.version for version in versions):raise ValueError('Agent清单版本必须与包内agent-version.json一致')
    package=Path(a.package).read_bytes()
    manifest={'kind':a.kind,'version':a.version,'platform':a.platform,'arch':a.arch,'sha256':hashlib.sha256(package).hexdigest(),
        'size':len(package),'key_id':a.key_id,'protocol_min':5,'protocol_max':5,'entrypoint':a.entrypoint,'files':files}
    manifest['signature']=base64.b64encode(key.sign(canonical(manifest))).decode()
    Path(a.output).write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':main()
