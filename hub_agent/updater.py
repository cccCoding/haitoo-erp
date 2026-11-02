"""签名版本槽、健康确认与失败回滚；不原地覆盖运行中的程序。"""
import asyncio
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from package_security import verify_manifest,unpack_verified,version_tuple,MAX_UNPACKED
from plugin_manager import load_plugin

VERSION=json.loads(Path(__file__).with_name('agent-version.json').read_text(encoding="utf-8"))['version']


def target():
    return ('macos' if platform.system()=='Darwin' else 'windows', 'arm64' if platform.machine().lower() in {'arm64','aarch64'} else 'x64')


def keys():
    path=Path(os.environ.get('HAITOO_RELEASE_KEYS_FILE',str(Path(__file__).with_name('trusted_keys.json'))))
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict):raise ValueError('本机公钥库格式无效')
    return value


def atomic(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8');temp.replace(path)


def launcher(entry):
    return [str(entry)] if entry.suffix.lower()!='.py' else [sys.executable,str(entry)]


def current_command():
    mode='console' if any(v in {'console','run'} for v in sys.argv[1:2]) else 'tray'
    return [sys.executable,mode] if getattr(sys,'frozen',False) else [sys.executable,str(Path(__file__).with_name('haitoo_hub_agent.py')),mode]


def forward(root):
    pointer=Path(root)/'current-agent.json'
    if not pointer.exists() or os.environ.get('HAITOO_UPDATE_HEALTH'):return False
    info=json.loads(pointer.read_text(encoding="utf-8"));manifest=verify_manifest(info['manifest'],keys(),*target())
    entry=Path(root)/'versions'/manifest['sha256']/manifest['entrypoint']
    own=Path(sys.executable if getattr(sys,'frozen',False) else sys.argv[0]).resolve()
    if entry.resolve()==own:return False
    # 固定槽的每个文件都需保持签名摘要，不能仅相信指针。
    for name,checksum in manifest['files'].items():
        if hashlib.sha256((entry.parents[len(Path(manifest['entrypoint']).parts)-1]/name).read_bytes()).hexdigest()!=checksum:raise ValueError('已安装Agent文件校验失败')
    subprocess.Popen(launcher(entry)+[current_command()[-1]],close_fds=True)
    return True


class UpdateManager:
    def __init__(self,root,client):
        self.root=Path(root);self.client=client;self.state={'status':'idle'};self.last_check=0

    async def check(self):
        if time.monotonic()-self.last_check<900:return False
        self.last_check=time.monotonic()
        trust=keys()
        if not trust:
            self.state={'status':'no_trusted_keys'};return False
        platform_name,arch=target()
        rows=await self.client.request('GET','/hub-v5/agent/releases',params={'platform':platform_name,'arch':arch})
        blocked_path=self.root/'blocked-releases.json'
        blocked=json.loads(blocked_path.read_text(encoding="utf-8")) if blocked_path.exists() else []
        highwater_path=self.root/'release-highwater.json'
        highwater=json.loads(highwater_path.read_text(encoding="utf-8")) if highwater_path.exists() else {}
        for kind in ('plugin','agent'):
            candidates=sorted((r for r in rows if r['manifest']['kind']==kind),key=lambda r:version_tuple(r['manifest']['version']),reverse=True)
            if not candidates:continue
            row=candidates[0];manifest=row['manifest']
            current=highwater.get(kind,VERSION if kind=='agent' else '0.0.0')
            if version_tuple(manifest['version'])<=version_tuple(current) or manifest['sha256'] in blocked:continue
            try:
                verify_manifest(manifest,trust,platform_name,arch)
                if shutil.disk_usage(self.root).free < manifest['size'] + MAX_UNPACKED:
                    raise RuntimeError('磁盘空间不足，升级已停止')
                directory=self.root/('plugins' if kind=='plugin' else 'versions')/manifest['sha256']
                package=self.root/'downloads'/(manifest['sha256']+'.zip');package.parent.mkdir(parents=True,exist_ok=True)
                await self.client.matrix_download_release(row['id'],package,manifest['size'])
                if directory.exists():shutil.rmtree(directory)
                unpack_verified(package,manifest,directory)
                if kind=='plugin':
                    pointer=self.root/'current-plugin.json';previous=pointer.read_text(encoding="utf-8") if pointer.exists() else None
                    atomic(pointer,{'manifest':manifest})
                    try:load_plugin(self.root,trust,platform_name,arch)
                    except Exception:
                        if previous is None:pointer.unlink()
                        else:pointer.write_text(previous,encoding="utf-8")
                        raise
                    if previous is not None:
                        atomic(self.root/'previous-plugin.json',json.loads(previous))
                    highwater[kind]=manifest['version'];atomic(highwater_path,highwater)
                    self.state={'status':'plugin_installed','plugin_version':manifest['version']}
                else:
                    transaction=self.root/'pending-agent.json'
                    atomic(transaction,{'manifest':manifest,'parent_pid':os.getpid(),'previous_command':current_command()})
                    helper=current_command()[:-1]+['apply-update','--transaction',str(transaction)]
                    subprocess.Popen(helper,close_fds=True)
                    self.state={'status':'restart_requested','version':manifest['version']}
                    return True
            except Exception:
                blocked.append(manifest['sha256']);atomic(blocked_path,blocked[-100:])
                self.state={'status':'rejected','error_code':'PACKAGE_VALIDATION_FAILED'}
        return False


def apply_update(transaction):
    transaction=Path(transaction).resolve();root=transaction.parent
    data=json.loads(transaction.read_text(encoding="utf-8"));manifest=verify_manifest(data['manifest'],keys(),*target())
    directory=root/'versions'/manifest['sha256'];entry=directory/manifest['entrypoint']
    if manifest['kind']!='agent':raise ValueError('不是Agent发布包')
    for name,checksum in manifest['files'].items():
        if hashlib.sha256((directory/name).read_bytes()).hexdigest()!=checksum:raise ValueError('暂存文件已变化')
    for _ in range(120):
        try:os.kill(data['parent_pid'],0)
        except OSError:break
        time.sleep(.5)
    else:raise RuntimeError('旧执行器未结束，升级已停止')
    health=root/('health-'+manifest['sha256']+'.json')
    if health.exists():health.unlink()
    env={**os.environ,'HAITOO_UPDATE_HEALTH':str(health)}
    mode=data['previous_command'][-1]
    if mode not in {'tray','console'}:raise ValueError('回滚启动方式无效')
    child=subprocess.Popen(launcher(entry)+[mode],env=env,close_fds=True)
    healthy=False
    for _ in range(120):
        if child.poll() is not None:break
        if health.exists():healthy=True;break
        time.sleep(.5)
    if healthy:
        pointer=root/'current-agent.json'
        prior=json.loads(pointer.read_text(encoding="utf-8")) if pointer.exists() else {'command':data['previous_command']}
        atomic(root/'previous-agent.json',prior)
        atomic(root/'current-agent.json',{'manifest':manifest})
        high_path=root/'release-highwater.json';high=json.loads(high_path.read_text(encoding="utf-8")) if high_path.exists() else {};high['agent']=manifest['version'];atomic(high_path,high)
    else:
        if child.poll() is None:child.terminate();child.wait(timeout=15)
        blocked_path=root/'blocked-releases.json';blocked=json.loads(blocked_path.read_text(encoding="utf-8")) if blocked_path.exists() else [];blocked.append(manifest['sha256']);atomic(blocked_path,blocked[-100:])
        subprocess.Popen(data['previous_command'],close_fds=True)
    transaction.unlink(missing_ok=True)


def rollback(root,kind):
    """仅在执行器退出后由本机用户调用；回到上个已验证槽。"""
    root=Path(root)
    import socket
    with socket.socket() as connection:
        if connection.connect_ex(('127.0.0.1',45679))==0:
            raise RuntimeError('请先退出本机执行器，任务执行期间不能回滚')
    pointer=root/f'current-{kind}.json';previous=root/f'previous-{kind}.json'
    if not pointer.exists() or not previous.exists():raise RuntimeError('没有可回滚的已验证版本')
    old=json.loads(pointer.read_text(encoding="utf-8"));replacement=json.loads(previous.read_text(encoding="utf-8"))
    manifest=verify_manifest(old['manifest'],keys(),*target())
    if 'manifest' in replacement:verify_manifest(replacement['manifest'],keys(),*target())
    if kind=='plugin':
        atomic(pointer,replacement)
        try:load_plugin(root,keys(),*target())
        except Exception:atomic(pointer,old);raise
    elif 'manifest' in replacement:
        atomic(pointer,replacement)
    else:
        pointer.unlink()
    blocked_path=root/'blocked-releases.json';blocked=json.loads(blocked_path.read_text(encoding="utf-8")) if blocked_path.exists() else []
    blocked.append(manifest['sha256']);atomic(blocked_path,blocked[-100:])
    if kind=='agent':
        command=launcher(root/'versions'/replacement['manifest']['sha256']/replacement['manifest']['entrypoint'])+['console'] if 'manifest' in replacement else replacement['command']
        subprocess.Popen(command,env={k:v for k,v in os.environ.items() if k!='HAITOO_UPDATE_HEALTH'},close_fds=True)
    return True
