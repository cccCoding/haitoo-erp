import { emptyTitleGenerationProgress, type BatchTitleGroup, type TitleGenerationProgress } from './batch-title-generation.ts'

export interface PersistentTitleGroup extends BatchTitleGroup {
  manualTitle?: boolean
  generation_id?: number
  titleWarnings?: string[]
  titleKeywords?: { id: number; code: string; phrase: string; translation: string }[]
}

export function createPersistentTitleGenerator<Group extends PersistentTitleGroup>(options: {
  progress: TitleGenerationProgress
  submit: (groups: Group[]) => Promise<{ id: number }>
  poll: (id: number) => Promise<any>
  cancel: (id: number) => Promise<unknown>
  isCurrent: (group: Group) => boolean
  onError: (message: string) => void
  delay?: () => Promise<void>
}) {
  let revision = 0
  let active: { revision: number; groups: Group[]; id?: number } | undefined
  const progress = options.progress
  function stop() {
    revision++
    const run = active
    active = undefined
    if (!run) return
    if (run.id) void options.cancel(run.id).catch(() => undefined)
    for (const group of run.groups) {
      if (['queued', 'running'].includes(group.titleStatus)) {
        group.titleStatus = 'stopped'; group.titleError = ''; progress.stopped++
      }
    }
    progress.running = false
  }
  function reset() { stop(); Object.assign(progress, emptyTitleGenerationProgress()) }
  async function run(groups: Group[]) {
    if (active) return
    groups = groups.filter(group => !group.manualTitle)
    if (!groups.length) return
    const current = { revision: ++revision, groups: [...groups], id: undefined as number | undefined }
    active = current
    Object.assign(progress, emptyTitleGenerationProgress(), { running: true, total: groups.length })
    for (const group of groups) { group.titleStatus = 'queued'; group.titleError = '' }
    const isActive = () => active === current && revision === current.revision
    try {
      const task = await options.submit(groups)
      current.id = task.id
      if (!isActive()) { await options.cancel(task.id).catch(() => undefined); return }
      while (isActive()) {
        const taskState = await options.poll(task.id)
        if (!isActive()) return
        for (const group of groups) {
          if (!options.isCurrent(group)) { stop(); return }
          if (group.manualTitle) continue
          const item = taskState.result?.items?.[String(group.id)]
          if (item?.title && ['queued','running'].includes(group.titleStatus)) {
            group.title = item.title; group.generation_id = item.generation_id
            group.titleWarnings = item.warnings || []; group.titleKeywords = item.keywords || []
            group.edited = true; group.titleStatus = 'success'
            progress.succeeded++; progress.completed++
          } else if (item?.state === 'failed' && ['queued','running'].includes(group.titleStatus)) {
            group.titleStatus = 'failed'; group.titleError = item.error || '标题生成失败'
            progress.failed++; progress.completed++
          } else if (group.titleStatus === 'queued' && taskState.state === 'running') group.titleStatus = 'running'
        }
        if (['completed','completed_with_errors','failed','cancelled'].includes(taskState.state)) {
          for (const group of groups) {
            if (['queued','running'].includes(group.titleStatus)) {
              group.titleStatus = taskState.state === 'cancelled' ? 'stopped' : 'failed'
              group.titleError = taskState.error || '任务未返回标题'
              progress.completed++; progress.failed++
            }
          }
          break
        }
        await (options.delay ? options.delay() : new Promise<void>(resolve => setTimeout(resolve, 1800)))
      }
    } catch (e: any) {
      if (!isActive()) return
      const message = e.response?.data?.detail || e.message || '批量标题任务失败'
      progress.error = message
      for (const group of groups) if (['queued','running'].includes(group.titleStatus)) {
        group.titleStatus = 'failed'; group.titleError = message; progress.failed++; progress.completed++
      }
      options.onError(message)
    } finally {
      if (isActive()) { active = undefined; progress.running = false }
    }
  }
  return { run, stop, reset }
}
