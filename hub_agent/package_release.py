"""创建可签名ZIP；将包内合法链接展开为普通文件，不携带外部文件。"""
import argparse
import stat
import zipfile
from pathlib import Path
from package_security import safe_path,MAX_UNPACKED,MAX_PACKAGE


def package_directory(source,destination):
    source=Path(source).resolve();destination=Path(destination).resolve()
    if not source.is_dir() or destination.is_relative_to(source):raise ValueError('请选择目录，输出ZIP须在源目录之外')
    files=[];total=0
    def walk(current,relative,ancestors):
        nonlocal total
        resolved=current.resolve()
        if not resolved.is_relative_to(source):raise ValueError('发布目录包含指向外部的链接')
        if current.is_dir():
            if resolved in ancestors:raise ValueError('发布目录包含循环链接')
            for child in sorted(current.iterdir()):walk(child,relative/child.name,ancestors|{resolved})
        elif current.is_file():
            name=relative.as_posix();safe_path(name)
            total+=current.stat().st_size
            if total>MAX_UNPACKED or len(files)>=20000:raise ValueError('发布目录超过资源上限')
            files.append((current,name))
        else:raise ValueError('发布目录包含不支持的文件类型')
    walk(source,Path(source.name),set())
    destination.parent.mkdir(parents=True,exist_ok=True)
    temporary=destination.with_suffix('.tmp')
    try:
        with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
            for path,name in files:
                info=zipfile.ZipInfo(name);info.compress_type=zipfile.ZIP_DEFLATED
                info.external_attr=(stat.S_IFREG|(0o755 if path.stat().st_mode&0o111 else 0o644))<<16
                with path.open('rb') as reader,archive.open(info,'w') as writer:
                    import shutil
                    shutil.copyfileobj(reader,writer,1024*1024)
        if temporary.stat().st_size>MAX_PACKAGE:raise ValueError('发布ZIP超过250MB')
        temporary.replace(destination)
    finally:temporary.unlink(missing_ok=True)
    return destination


def main():
    parser=argparse.ArgumentParser(description='创建可签名的Agent或插件ZIP')
    parser.add_argument('--source',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();print(package_directory(args.source,args.output))


if __name__=='__main__':main()
