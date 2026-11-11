"""签名发布清单和ZIP校验；只信任本机固定公钥，不从发布包导入信任。"""
import base64
import hashlib
import json
import re
import stat
import zipfile
import shutil
import unicodedata
from pathlib import Path, PurePosixPath
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

MAX_PACKAGE=250*1024*1024
MAX_UNPACKED=1024*1024*1024


def canonical(manifest):
    return json.dumps({k:v for k,v in manifest.items() if k!='signature'},ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()


def version_tuple(version):
    if not isinstance(version,str) or not re.fullmatch(r'\d+\.\d+\.\d+',version):raise ValueError('版本格式无效')
    return tuple(map(int,version.split('.')))


def safe_path(name):
    if not isinstance(name,str) or not name or '\\' in name or ':' in name or name.startswith('/') or any(p in {'','.','..'} for p in name.rstrip('/').split('/')):
        raise ValueError('发布包包含不安全路径')
    reserved={'con','prn','aux','nul',*[f'com{i}' for i in range(1,10)],*[f'lpt{i}' for i in range(1,10)]}
    if any(part.rstrip(' .')!=part or part.split('.')[0].casefold() in reserved for part in name.rstrip('/').split('/')):
        raise ValueError('发布包包含平台保留路径')
    return PurePosixPath(name)


def verify_manifest(manifest,keys,platform,arch):
    required={'kind','version','platform','arch','sha256','size','key_id','signature','protocol_min','protocol_max','entrypoint','files'}
    if not required.issubset(manifest) or set(manifest)-required-{'installer','min_launcher_version','symlinks'}:raise ValueError('签名清单字段不正确')
    version_tuple(manifest['version'])
    if manifest['kind'] not in {'agent','plugin'} or (manifest['platform'],manifest['arch'])!=(platform,arch):raise ValueError('发布平台不匹配')
    if type(manifest['protocol_min']) is not int or type(manifest['protocol_max']) is not int or not manifest['protocol_min']<=5<=manifest['protocol_max']:raise ValueError('协议不兼容')
    if type(manifest['size']) is not int or not 0<manifest['size']<=MAX_PACKAGE or not re.fullmatch(r'[a-f0-9]{64}',manifest['sha256']):raise ValueError('文件大小或摘要无效')
    if not isinstance(manifest['files'],dict) or not 1<=len(manifest['files'])<=20000:raise ValueError('文件清单无效')
    for name,checksum in manifest['files'].items():
        safe_path(name)
        if not re.fullmatch(r'[a-f0-9]{64}',checksum):raise ValueError('文件摘要无效')
    if len({unicodedata.normalize('NFC',n).casefold() for n in manifest['files']})!=len(manifest['files']):raise ValueError('发布路径存在大小写或Unicode冲突')
    if 'min_launcher_version' in manifest:version_tuple(manifest['min_launcher_version'])
    links=manifest.get('symlinks',{})
    if not isinstance(links,dict) or platform!='macos' and links:raise ValueError('链接清单无效')
    for name,value in links.items():
        if name not in manifest['files']:raise ValueError('链接未签名')
        safe_link(name,value)
    if manifest['entrypoint'] in links:raise ValueError('启动入口不能为链接')
    if manifest['entrypoint'] not in manifest['files']:raise ValueError('启动入口未签名')
    try:
        key=Ed25519PublicKey.from_public_bytes(base64.b64decode(keys[manifest['key_id']],validate=True))
        key.verify(base64.b64decode(manifest['signature'],validate=True),canonical(manifest))
    except Exception as exc:raise ValueError('发布签名无效或公钥未受信任') from exc
    return manifest


def safe_link(name,value):
    if not isinstance(value,str) or not value or value.startswith('/') or '\\' in value or ':' in value:
        raise ValueError('链接目标无效')
    parts=list(safe_path(name).parent.parts)
    for part in value.split('/'):
        if part=='..':
            if not parts:raise ValueError('链接越出发布目录')
            parts.pop()
        elif part not in {'','.'}:parts.append(part)
    return value


def verify_directory(directory,manifest):
    directory=Path(directory).resolve()
    links=manifest.get('symlinks',{})
    for name,checksum in manifest['files'].items():
        path=directory/name
        if not path.resolve().is_relative_to(directory):raise ValueError('安装文件越出版本目录')
        if name in links:
            if not path.is_symlink() or path.readlink().as_posix()!=links[name]:raise ValueError('安装链接已变化')
            content=links[name].encode('utf-8')
            actual=hashlib.sha256(content).hexdigest()
        else:
            if path.is_symlink():raise ValueError('安装文件被替换为链接')
            with path.open('rb') as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
        if actual!=checksum:raise ValueError('已安装文件校验失败')


def unpack_verified(package,manifest,destination):
    package=Path(package);destination=Path(destination)
    with package.open('rb') as stream:checksum=hashlib.file_digest(stream,'sha256').hexdigest()
    if package.stat().st_size!=manifest['size'] or checksum!=manifest['sha256']:raise ValueError('发布包摘要不一致')
    if destination.exists():raise ValueError('暂存目录已存在')
    with zipfile.ZipFile(package) as zf:
        infos=zf.infolist()
        if len(infos)>22000 or sum(i.file_size for i in infos)>MAX_UNPACKED:raise ValueError('发布包解压资源超限')
        names=set()
        for info in infos:
            safe_path(info.filename)
            mode=info.external_attr>>16
            is_link=stat.S_ISLNK(mode)
            if mode and stat.S_IFMT(mode) not in {0,stat.S_IFREG,stat.S_IFDIR,stat.S_IFLNK}:raise ValueError('发布包不允许设备文件')
            links=manifest.get('symlinks',{})
            if is_link != (info.filename in links):raise ValueError('发布包包含未签名链接')
            if is_link:
                if info.file_size>4096 or zf.read(info).decode('utf-8')!=links[info.filename]:raise ValueError('链接目标不一致')
                safe_link(info.filename,links[info.filename])
            if info.is_dir():continue
            if info.filename in names:raise ValueError('发布包包含重复路径')
            names.add(info.filename)
            if info.filename not in manifest['files']:raise ValueError('发布包包含未签名文件')
            with zf.open(info) as stream:checksum=hashlib.file_digest(stream,'sha256').hexdigest()
            if checksum!=manifest['files'][info.filename]:raise ValueError('发布文件摘要错误')
        if names!=set(manifest['files']):raise ValueError('发布包缺少签名文件')
        for name in names:
            if any(parent.as_posix() in names for parent in PurePosixPath(name).parents if parent.as_posix()!='.'):
                raise ValueError('发布文件与目录冲突')
        destination.mkdir(parents=True)
        for info in infos:
            path=destination.joinpath(*safe_path(info.filename).parts)
            if info.is_dir():path.mkdir(parents=True,exist_ok=True);continue
            if info.filename in manifest.get('symlinks',{}):continue
            path.parent.mkdir(parents=True,exist_ok=True)
            with zf.open(info) as source,path.open('wb') as output:shutil.copyfileobj(source,output,1024*1024)
            path.chmod(0o755 if info.external_attr>>16 & 0o111 else 0o644)
        for name,value in manifest.get('symlinks',{}).items():
            path=destination/name;path.parent.mkdir(parents=True,exist_ok=True);path.symlink_to(value)
    verify_directory(destination,manifest)
    return destination
