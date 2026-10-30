export type TitleGenerationStatus = 'idle' | 'queued' | 'running' | 'success' | 'failed' | 'stopped'

export interface BatchTitleGroup {
  id: number
  title: string
  edited?: boolean
  titleStatus: TitleGenerationStatus
  titleError: string
}

export interface TitleGenerationProgress {
  running: boolean
  total: number
  completed: number
  succeeded: number
  failed: number
  stopped: number
  error: string
}

export function emptyTitleGenerationProgress(): TitleGenerationProgress {
  return { running: false, total: 0, completed: 0, succeeded: 0, failed: 0, stopped: 0, error: '' }
}

export const titleGenerationStatusLabels: Record<TitleGenerationStatus, string> = {
  idle: '未生成', queued: '等待生成', running: '生成中', success: '已生成', failed: '生成失败', stopped: '已停止',
}

export function isUnfinishedTitle(group: BatchTitleGroup): boolean {
  return group.titleStatus === 'failed' || group.titleStatus === 'stopped'
}

export function hasValidBatchTitles(groups: BatchTitleGroup[]): boolean {
  return groups.length > 0 && groups.every(group => {
    const length = group.title.trim().length
    return length >= 25 && length <= 255
  })
}

export function titleGenerationError(error: unknown): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof detail === 'string' ? detail : 'AI 生成标题失败，请稍后重试'
}

export function isFatalTitleGenerationError(error: unknown): boolean {
  const status = (error as { response?: { status?: number } })?.response?.status
  return status === 401 || (status === 400 && titleGenerationError(error).includes('尚未配置个人 DeepSeek 密钥'))
}

export function batchTitleRequest(templateId: number, fromLibrary: boolean,
  firstAsset: { id: number; source_type?: string; url: string }, additionalRequirements: string) {
  return {
    url: fromLibrary ? '/product-library/generate-draft-title' : `/templates/${templateId}/generate-draft-title`,
    payload: {
      ...(fromLibrary ? { source_type: firstAsset.source_type, id: firstAsset.id } : { image_url: firstAsset.url }),
      additional_requirements: additionalRequirements.trim(),
    },
  }
}

// 状态由调用方提供，可直接使用 Vue 的响应式对象；每轮标识独立于 HTTP 取消，防止旧响应回填。
export function createBatchTitleGenerator<Group extends BatchTitleGroup>(options: {
  progress: TitleGenerationProgress
  generate: (group: Group, signal: AbortSignal) => Promise<string>
  isCurrent: (group: Group) => boolean
  onFatal: (message: string) => void
  onGenerated?: (group: Group) => void
}) {
  const { progress } = options
  let revision = 0
  let active: { revision: number; groups: Group[]; controller: AbortController } | undefined

  function stop() {
    revision++
    if (!active) return
    const run = active
    active = undefined
    run.controller.abort()
    for (const group of run.groups) {
      if (group.titleStatus === 'queued' || group.titleStatus === 'running') {
        group.titleStatus = 'stopped'
        group.titleError = ''
        progress.stopped++
      }
    }
    progress.running = false
  }

  function reset() {
    stop()
    Object.assign(progress, emptyTitleGenerationProgress())
  }

  async function run(groups: Group[]) {
    if (active || !groups.length) return
    const current = { revision: ++revision, groups: [...groups], controller: new AbortController() }
    active = current
    Object.assign(progress, emptyTitleGenerationProgress(), { running: true, total: groups.length })
    for (const group of current.groups) {
      group.titleStatus = 'queued'
      group.titleError = ''
    }
    let next = 0
    const isActive = () => active === current && revision === current.revision
    async function worker() {
      while (isActive() && next < current.groups.length) {
        const group = current.groups[next++]!
        if (!options.isCurrent(group)) { stop(); return }
        group.titleStatus = 'running'
        try {
          const title = await options.generate(group, current.controller.signal)
          if (!isActive()) return
          if (!options.isCurrent(group)) { stop(); return }
          if (typeof title !== 'string' || title.trim().length < 25 || title.trim().length > 255) {
            throw { response: { data: { detail: 'AI 返回的标题长度必须为 25–255 个字符，请重试或手动填写' } } }
          }
          options.onGenerated?.(group)
          group.title = title.trim()
          group.edited = true
          group.titleStatus = 'success'
          progress.succeeded++
          progress.completed++
        } catch (error) {
          if (!isActive()) return
          if (!options.isCurrent(group)) { stop(); return }
          group.titleStatus = 'failed'
          group.titleError = titleGenerationError(error)
          progress.failed++
          progress.completed++
          if (isFatalTitleGenerationError(error)) {
            progress.error = group.titleError
            stop()
            options.onFatal(group.titleError)
            return
          }
        }
      }
    }
    await Promise.all(Array.from({ length: Math.min(10, groups.length) }, worker))
    if (isActive()) {
      active = undefined
      progress.running = false
    }
  }

  return { run, stop, reset }
}
