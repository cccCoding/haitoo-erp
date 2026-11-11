"""后台准备签名更新、空闲切换、健康确认与中断恢复。固定安装入口不被覆盖。"""
import asyncio
import hashlib
import json
import os
import platform
import random
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from package_security import verify_manifest, unpack_verified, verify_directory, version_tuple, MAX_UNPACKED
from plugin_manager import load_plugin

VERSION = json.loads(Path(__file__).with_name('agent-version.json').read_text(encoding='utf-8'))['version']


def target():
    system = platform.system()
    if system not in {'Darwin', 'Windows'}:
        raise ValueError('连接器仅支持 macOS 和 Windows')
    return ('macos' if system == 'Darwin' else 'windows', 'arm64' if platform.machine().lower() in {'arm64', 'aarch64'} else 'x64')


def keys():
    path = Path(os.environ.get('HAITOO_RELEASE_KEYS_FILE', str(Path(__file__).with_name('trusted_keys.json'))))
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError('本机公钥库格式无效')
    return value


def read(path, default=None):
    path = Path(path)
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def atomic(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    with temp.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False); stream.flush(); os.fsync(stream.fileno())
    temp.replace(path)


def launcher(entry):
    return [str(entry)] if entry.suffix.lower() != '.py' else [sys.executable, str(entry)]


def current_command():
    mode = 'console' if any(v in {'console', 'run'} for v in sys.argv[1:2]) else 'tray'
    return [sys.executable, mode] if getattr(sys, 'frozen', False) else [sys.executable, str(Path(__file__).with_name('haitoo_hub_agent.py')), mode]


def clean_env():
    return {**{k: v for k, v in os.environ.items() if k != 'HAITOO_UPDATE_HEALTH'}, 'PYINSTALLER_RESET_ENVIRONMENT': '1'}


def quarantine(root, checksum):
    path = Path(root) / 'blocked-releases.json'
    atomic(path, list(dict.fromkeys([*read(path, []), checksum]))[-100:])


def installed_entry(root, manifest):
    verify_manifest(manifest, keys(), *target())
    directory = Path(root) / 'versions' / manifest['sha256']
    verify_directory(directory, manifest)
    entry = directory / manifest['entrypoint']
    verify_native(entry)
    return entry


def verify_native(entry):
    """正式冻结程序还须通过操作系统签名检查；源码调试仅使用清单签名。"""
    if not getattr(sys, 'frozen', False):
        return
    if platform.system() == 'Darwin':
        bundle = next((p for p in entry.parents if p.suffix == '.app'), None)
        if bundle is None:
            raise ValueError('macOS 更新入口必须在签名应用内')
        command = ['/usr/bin/codesign', '--verify', '--deep', '--strict', str(bundle)]
    else:
        command = ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
                   "if ((Get-AuthenticodeSignature -LiteralPath $env:HAITOO_VERIFY_ENTRY).Status -ne 'Valid') { exit 1 }"]
    try:
        subprocess.run(command, check=True, capture_output=True, timeout=60, env={**os.environ, 'HAITOO_VERIFY_ENTRY': str(entry)}, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (subprocess.SubprocessError, OSError) as exc:
        raise ValueError('操作系统代码签名验证失败') from exc


def forward(root):
    root = Path(root)
    os.environ.setdefault('HAITOO_LAUNCHER_VERSION', VERSION)
    os.environ.setdefault('HAITOO_BOOTSTRAP_COMMAND', json.dumps(current_command()))
    if os.environ.get('HAITOO_UPDATE_HEALTH'):
        return False
    pending = root / 'pending-agent.json'
    if pending.exists():
        subprocess.Popen(current_command()[:-1] + ['apply-update', '--transaction', str(pending)], env=clean_env(), close_fds=True)
        return True
    pointer = root / 'current-agent.json'
    info = read(pointer)
    if not info:
        return False
    manifest = info['manifest']
    # 手动安装更高版本时，以新安装内置版本为基线，避免旧指针把用户带回旧版本。
    if version_tuple(manifest['version']) < version_tuple(VERSION):
        pointer.unlink(missing_ok=True)
        return False
    try:
        entry = installed_entry(root, manifest)
    except Exception:
        quarantine(root, manifest['sha256'])
        previous = read(root / 'previous-agent.json', {})
        if 'manifest' in previous:
            try:
                entry = installed_entry(root, previous['manifest'])
                atomic(pointer, previous)
            except Exception:
                pointer.unlink(missing_ok=True)
                return False
        else:
            pointer.unlink(missing_ok=True)
            return False  # 固定安装入口内置的完整版本仍可运行。
    own = Path(sys.executable if getattr(sys, 'frozen', False) else sys.argv[0]).resolve()
    if entry.resolve() == own:
        return False
    subprocess.Popen(launcher(entry) + [current_command()[-1]], env=clean_env(), close_fds=True)
    return True


class UpdateManager:
    def __init__(self, root, client):
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True)
        self.client = client
        self.state = read(self.root / 'update-result.json', {'status': 'idle'})
        self.next_check = 0
        self.next_activation = 0
        self.failures = 0
        self.lock = asyncio.Lock()
        self.prepared = read(self.root / 'staged-agent.json')
        if self.prepared and (version_tuple(self.prepared['manifest']['version']) <= version_tuple(VERSION) or self.prepared['manifest']['sha256'] in read(self.root / 'blocked-releases.json', [])):
            self.prepared = None  # 新进程不能把自身再次当作待更新版本，否则会在健康确认时退出。
        if self.prepared:self.state = {'status':'waiting_idle','target_version':self.prepared['manifest']['version']}
        self.force = False
        self.plugin_check = 0

    def request_check(self):
        self.force = True; self.next_check = 0; self.next_activation = 0

    async def activate(self):
        if self.lock.locked() or not self.prepared or time.monotonic() < self.next_activation:
            return False
        async with self.lock:
            row = self.prepared; manifest = row['manifest']
            # 暂存后撤回的包不再启动。离线时保留旧版本，稍后再确认。
            try:
                rows = await self.client.request('GET', '/hub-v5/agent/connector-releases', params=dict(zip(('platform', 'arch'), target())))
                if not any(r['id'] == row['id'] and r['manifest'] == manifest for r in rows):
                    self.prepared = None; (self.root / 'staged-agent.json').unlink(missing_ok=True)
                    self.state = {'status': 'idle'}
                    return False
                await asyncio.to_thread(installed_entry, self.root, manifest)
            except ValueError:
                quarantine(self.root, manifest['sha256']); self.prepared = None
                (self.root / 'staged-agent.json').unlink(missing_ok=True)
                self.state = {'status': 'rejected', 'error_code': 'PACKAGE_VALIDATION_FAILED'}
                return False
            except Exception:
                self.next_activation = time.monotonic() + 60
                self.state = {'status': 'retry', 'error_code': 'RELEASE_CHECK_FAILED', 'target_version': manifest['version']}
                return False
            transaction = self.root / 'pending-agent.json'
            atomic(transaction, {'manifest': manifest, 'parent_pid': os.getpid(), 'created_at': time.time(), 'previous_command': current_command()})
            subprocess.Popen(current_command()[:-1] + ['apply-update', '--transaction', str(transaction)], env=clean_env(), close_fds=True)
            self.state = {'status': 'restart_requested', 'target_version': manifest['version']}
            return True

    async def check(self, can_activate=True):
        if can_activate and await self.activate():
            return True
        if self.prepared:
            return False
        if self.lock.locked():
            return False
        plugin_due = can_activate and time.monotonic() >= self.plugin_check
        if time.monotonic() < self.next_check and not plugin_due:
            return False
        async with self.lock:
            self.next_check = time.monotonic() + 900 + random.uniform(0, 60)
            self.force = False
            self.state = {'status': 'checking'}
            try:
                trust = keys()
                if not trust:
                    self.state = {'status': 'no_trusted_keys'}; return False
                platform_name, arch = target()
                params = {'platform': platform_name, 'arch': arch}
                rows = await self.client.request('GET', '/hub-v5/agent/connector-releases', params=params)
                # 插件故障不会阻塞连接器自身更新。
                if plugin_due:
                    self.plugin_check = time.monotonic() + 900
                    try:
                        plugins = await self.client.request('GET', '/hub-v5/agent/releases', params=params)
                        rows += [r for r in plugins if r['manifest']['kind'] == 'plugin']
                    except Exception:
                        pass
                blocked = read(self.root / 'blocked-releases.json', [])
                highwater = read(self.root / 'release-highwater.json', {})
                plugin_highwater = read(self.root / 'plugin-highwater.json', {})
                if plugin_highwater.get('plugin'):highwater['plugin'] = max(highwater.get('plugin','0.0.0'),plugin_highwater['plugin'],key=version_tuple)
                for kind in ('agent', 'plugin'):
                    candidates = sorted((r for r in rows if r['manifest']['kind'] == kind), key=lambda r: version_tuple(r['manifest']['version']), reverse=True)
                    if not candidates:
                        continue
                    row = candidates[0]; manifest = row['manifest']
                    current = max(version_tuple(highwater.get(kind, '0.0.0')), version_tuple(VERSION if kind == 'agent' else '0.0.0'))
                    if version_tuple(manifest['version']) <= current or manifest['sha256'] in blocked:
                        continue
                    try:
                        verify_manifest(manifest, trust, platform_name, arch)
                        self.state = {'status': 'checking', 'target_version': manifest['version']}
                        if kind == 'agent' and version_tuple(manifest.get('min_launcher_version', '0.0.0')) > version_tuple(os.environ.get('HAITOO_LAUNCHER_VERSION', VERSION)):
                            self.state['status'] = 'installer_required'; return False
                        if shutil.disk_usage(self.root).free < manifest['size'] + MAX_UNPACKED:
                            self.state['status'] = 'insufficient_space'; return False
                        directory = self.root / ('plugins' if kind == 'plugin' else 'versions') / manifest['sha256']
                        package = self.root / 'downloads' / (manifest['sha256'] + '.zip')
                        package.parent.mkdir(parents=True, exist_ok=True)
                        self.state['status'] = 'downloading'
                        if kind == 'agent':
                            await self.client.connector_download_release(row['id'], package, manifest['size'], on_progress=lambda received, total: self.state.update(progress=str(int(received * 100 / total))))
                        else:
                            await self.client.matrix_download_release(row['id'], package, manifest['size'])
                        # 此处之后的错误才属于包校验；网络错误绝不隔离版本。
                        try:
                            staging = directory.with_name(directory.name + '.staging')
                            await asyncio.to_thread(shutil.rmtree, staging, True)
                            await asyncio.to_thread(unpack_verified, package, manifest, staging)
                            if kind == 'agent':
                                await asyncio.to_thread(verify_native, staging / manifest['entrypoint'])
                            if directory.exists():
                                await asyncio.to_thread(verify_directory, directory, manifest)
                                await asyncio.to_thread(shutil.rmtree, staging, True)
                            else:
                                staging.replace(directory)
                        except (ValueError, UnicodeError, zipfile.BadZipFile):
                            quarantine(self.root, manifest['sha256'])
                            self.state = {'status': 'rejected', 'target_version': manifest['version'], 'error_code': 'PACKAGE_VALIDATION_FAILED'}
                            return False
                        finally:
                            package.unlink(missing_ok=True)
                            await asyncio.to_thread(shutil.rmtree, staging, True)
                        if kind == 'agent':
                            self.prepared = row; atomic(self.root / 'staged-agent.json', row)
                            self.state = {'status': 'waiting_idle', 'target_version': manifest['version']}
                            return False
                        pointer = self.root / 'current-plugin.json'; previous = read(pointer)
                        atomic(pointer, {'manifest': manifest})
                        try:
                            load_plugin(self.root, trust, platform_name, arch)
                        except Exception:
                            if previous is None: pointer.unlink(missing_ok=True)
                            else: atomic(pointer, previous)
                            quarantine(self.root, manifest['sha256']); raise ValueError('插件加载失败')
                        if previous is not None: atomic(self.root / 'previous-plugin.json', previous)
                        atomic(self.root / 'plugin-highwater.json', {'plugin':manifest['version']})
                        self.state = {'status': 'plugin_installed', 'plugin_version': manifest['version']}
                    except ValueError:
                        quarantine(self.root, manifest['sha256'])
                        self.state = {'status': 'rejected', 'error_code': 'PACKAGE_VALIDATION_FAILED'}
                        return False
                self.failures = 0
                if self.state['status'] == 'checking': self.state = {'status': 'up_to_date'}
            except asyncio.CancelledError:
                raise
            except Exception:
                self.failures += 1
                self.next_check = time.monotonic() + min(60 * 2 ** min(self.failures - 1, 4), 900) + random.uniform(0, 15)
                self.state = {'status': 'retry', 'error_code': 'DOWNLOAD_OR_NETWORK_FAILED'}
        return False


def cleanup_versions(root):
    import re
    root = Path(root)
    keep = {read(root / name, {}).get('manifest', {}).get('sha256') for name in ('current-agent.json', 'previous-agent.json')}
    for path in (root / 'versions').iterdir():
        if re.fullmatch('[a-f0-9]{64}', path.name) and path.name not in keep and path.is_dir() and not path.is_symlink():
            shutil.rmtree(path, ignore_errors=True)
    for path in (root / 'downloads').glob('*.zip'):
        if re.fullmatch(r'[a-f0-9]{64}\.zip', path.name):path.unlink(missing_ok=True)


def _apply_update(transaction):
    transaction = Path(transaction).resolve(); root = transaction.parent
    if not transaction.exists(): return
    data = read(transaction); manifest = verify_manifest(data['manifest'], keys(), *target())
    current = read(root / 'current-agent.json', {})
    result = read(root / 'update-result.json', {})
    if current.get('manifest') == manifest and result.get('status') == 'installed' and result.get('version') == manifest['version']:
        transaction.unlink(missing_ok=True); (root / 'staged-agent.json').unlink(missing_ok=True)
        subprocess.Popen(launcher(installed_entry(root, manifest)) + [data['previous_command'][-1]], env=clean_env(), close_fds=True)
        return
    if manifest['kind'] != 'agent': raise ValueError('不是连接器发布包')
    mode = data['previous_command'][-1]
    if mode not in {'tray', 'console'}: raise ValueError('回滚启动方式无效')
    # 超过两分钟的事务按中断恢复处理；不等待可能已被系统复用的旧 PID。
    if time.time() - data.get('created_at', time.time()) < 120:
        for _ in range(120):
            try: os.kill(data['parent_pid'], 0)
            except OSError: break
            time.sleep(.5)
        else: raise RuntimeError('旧执行器未结束，升级已停止')
    entry = installed_entry(root, manifest)
    health = root / ('health-' + manifest['sha256'] + '.json')
    # 辅助进程意外退出而新版本仍在线时，等待下一次干净启动恢复；不启动第二个版本。
    if data.get('child_pid') and time.time() - data.get('created_at', 0) < 120:
        try: os.kill(data['child_pid'], 0)
        except OSError: pass
        else:
            return
    health.unlink(missing_ok=True)
    child = subprocess.Popen(launcher(entry) + [mode], env={**clean_env(), 'HAITOO_UPDATE_HEALTH': str(health)}, close_fds=True)
    data['child_pid'] = child.pid
    atomic(transaction, data)
    healthy = False
    for _ in range(120):
        if child.poll() is not None: break
        value = read(health, {})
        if value.get('ready') and value.get('version') == manifest['version']:
            healthy = True; break
        time.sleep(.5)
    if healthy:
        pointer = root / 'current-agent.json'
        prior = read(pointer, {'command': data['previous_command']})
        if prior.get('manifest', {}).get('sha256') != manifest['sha256']:
            atomic(root / 'previous-agent.json', prior)
        atomic(pointer, {'manifest': manifest})
        high_path = root / 'release-highwater.json'; high = read(high_path, {}); high['agent'] = manifest['version']; atomic(high_path, high)
        atomic(root / 'update-result.json', {'status': 'installed', 'version': manifest['version']})
        cleanup_versions(root)
    else:
        if child.poll() is None:
            child.terminate(); child.wait(timeout=15)
        quarantine(root, manifest['sha256'])
        atomic(root / 'update-result.json', {'status': 'rolled_back', 'target_version': manifest['version'], 'error_code': 'NEW_VERSION_START_FAILED'})
    # 先完成事务，再启动旧版本，避免旧入口重新进入同一事务。
    transaction.unlink(missing_ok=True); (root / 'staged-agent.json').unlink(missing_ok=True); health.unlink(missing_ok=True)
    if not healthy:
        subprocess.Popen(data['previous_command'], env=clean_env(), close_fds=True)


def apply_update(transaction):
    root = Path(transaction).resolve().parent
    # 同一事务只允许一个辅助进程执行；重启后文件锁自动释放。
    with (root / 'update.lock').open('a+b') as lock:
        try:
            if os.name == 'nt':
                import msvcrt
                lock.seek(0); lock.write(b'0'); lock.flush(); lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return
        try:
            _apply_update(transaction)
        except Exception:
            data = read(transaction, {})
            if not data: return
            # 父进程仍在运行时不额外启动副本，下一次启动会重新处理事务。
            if time.time() - data.get('created_at', time.time()) < 120:
                try: os.kill(data['parent_pid'], 0)
                except OSError: pass
                else: return
            manifest = data.get('manifest', {})
            if 'sha256' in manifest: quarantine(root, manifest['sha256'])
            Path(transaction).unlink(missing_ok=True)
            (root / 'staged-agent.json').unlink(missing_ok=True)
            atomic(root / 'update-result.json', {'status': 'rolled_back', 'error_code': 'UPDATE_INTERRUPTED'})
            if data.get('previous_command'):
                subprocess.Popen(data['previous_command'], env=clean_env(), close_fds=True)


def rollback(root, kind):
    """仅在连接器退出后由本机用户调用；回到上个已验证槽。"""
    root = Path(root)
    if (root / 'pending-agent.json').exists():raise RuntimeError('更新事务尚未完成，请等待自动恢复后再回滚')
    import socket
    with socket.socket() as connection:
        if connection.connect_ex(('127.0.0.1', 45679)) == 0: raise RuntimeError('请先退出本机连接器，任务执行期间不能回滚')
    pointer = root / f'current-{kind}.json'; previous = root / f'previous-{kind}.json'
    if not pointer.exists() or not previous.exists(): raise RuntimeError('没有可回滚的已验证版本')
    old = read(pointer); replacement = read(previous)
    manifest = verify_manifest(old['manifest'], keys(), *target())
    if 'manifest' in replacement: verify_manifest(replacement['manifest'], keys(), *target())
    if kind == 'plugin':
        atomic(pointer, replacement)
        try: load_plugin(root, keys(), *target())
        except Exception: atomic(pointer, old); raise
    elif 'manifest' in replacement:
        installed_entry(root, replacement['manifest']); atomic(pointer, replacement)
    else: pointer.unlink()
    quarantine(root, manifest['sha256'])
    if kind == 'agent':
        command = launcher(installed_entry(root, replacement['manifest'])) + ['tray'] if 'manifest' in replacement else replacement['command']
        subprocess.Popen(command, env=clean_env(), close_fds=True)
