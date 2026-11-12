export type UpdateState = Record<string, unknown> | undefined
const retryable = new Set(['LAUNCH_PERMISSION_DENIED', 'NEW_VERSION_START_FAILED', 'UPDATE_LAUNCH_FAILED', 'UPDATE_INTERRUPTED'])
export function updateRecovery(state: UpdateState) {
  const code = String(state?.error_code || '')
  const needed = state?.manual_required === true || ['manual_required','rolled_back','installer_required'].includes(String(state?.status || ''))
  let message = '新版尚未成功启用，原版本与设备授权保留。请先查看日志，再按实际系统提示处理。'
  if (code === 'LAUNCH_PERMISSION_DENIED') message = '系统或文件权限拒绝启动新版。请核对来源并查看实际系统提示；原版本与授权保留。'
  if (code === 'OLD_VERSION_START_FAILED') message = '新版启动失败，旧版也未能重新启动。请下载匹配安装包手动安装；设备配置和授权数据仍保留。'
  if (code === 'NEW_VERSION_START_FAILED') message = '新版未通过启动检查，已恢复旧版本。原因尚未确定，请查看日志；不能据此判断系统拦截。'
  if (['NATIVE_SIGNATURE_FAILED','PACKAGE_VALIDATION_FAILED'].includes(code)) message = '更新包未通过签名或内容校验，当前版本继续运行。请联系管理员重新发布有效包，不要通过系统例外绕过包校验。'
  if (['LAUNCHER_TOO_OLD','UPDATE_CHANNEL_MISMATCH'].includes(code)) message = '当前安装入口与此更新不兼容，请手动下载并安装匹配版本，保留原设备授权与配置。'
  return {needed, message, canRetry: needed && retryable.has(code)}
}
export function platformSteps(platform: string, errorCode = '') {
  if (['NATIVE_SIGNATURE_FAILED','PACKAGE_VALIDATION_FAILED'].includes(errorCode)) return ['当前更新包未通过签名或内容校验，不能通过系统例外或重试绕过。', '请联系平台管理员核对更新公钥和发布文件，重新发布有效版本。', '可以下载下方当前可用安装包；等待任务结束并退出连接器后手动安装，保留原设备配置与授权。']
  const common = ['先确认安装包来自本公司的 ERP；退出连接器前等待当前任务结束。', '只按系统明确提供的选项处理。若没有允许选项、提示恶意软件或由组织策略禁止，请联系管理员，不要关闭系统防护。']
  if (platform === 'windows') return [...common, '如果 Windows SmartScreen 提供“更多信息 → 仍要运行”，核对发布来源后再选择；并非所有拦截都提供此选项。', '完整解压内部 ZIP 到固定目录，保留全部文件；正式 EXE 则按安装向导操作。运行后检查 ERP 中的版本和在线状态。']
  if (platform === 'macos') return [...common, '若 macOS 提示无法验证开发者，可在“系统设置 → 隐私与安全性”中查看是否有“仍要打开”，按提示人工确认。', '内部 ZIP 请完整解压并将应用放入固定目录；DMG 请先将应用拖入“应用程序”再运行。系统未提供例外时请联系管理员。']
  return [...common, 'Windows：查看 SmartScreen 是否提供“更多信息 → 仍要运行”。macOS：查看“系统设置 → 隐私与安全性”是否提供“仍要打开”。', '安装后在 ERP 检查连接器版本和在线状态。网页不能代替系统授予运行许可。']
}
