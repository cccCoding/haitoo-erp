export const TASK_RETRY_BATCH_SIZE = 1000

export function taskBatchRetryError(error: unknown): string {
  const response = (error as { response?: { status?: number; data?: { detail?: unknown } } })?.response
  if (!response) return '网络异常，提交结果未确认，请刷新列表后查看'
  const detail = response.data?.detail
  if (Array.isArray(detail)) {
    if (detail.some(item => item?.type === 'too_long' && Array.isArray(item.loc) && item.loc.includes('task_ids'))) {
      return `每批最多重试 ${TASK_RETRY_BATCH_SIZE} 个任务`
    }
    return '重试参数有误，请刷新任务列表后重试'
  }
  if (typeof detail === 'string' && detail.startsWith('只有失败任务可以重试')) {
    return '部分任务已不是失败状态，请刷新列表后重试'
  }
  if (response.status === 422) return '重试参数有误，请刷新任务列表后重试'
  if (typeof detail === 'string' && detail.trim() && detail.length <= 200 && !/[\n\r\[\]{}]/.test(detail)) {
    return detail.trim()
  }
  return '批量重试任务失败，请稍后重试'
}

export function createTaskBatchRetrier(options: {
  submit: (taskIds: number[]) => Promise<{ total: number }>
  onSucceeded: (taskIds: number[]) => void
  refresh: () => Promise<void>
  onMessage: (message: string) => void
  onRunningChange: (running: boolean) => void
}) {
  let running = false

  async function run(selectedIds: readonly number[]) {
    if (running) return
    // 点击时复制并去重，后续勾选变化和列表轮询不会改变本轮范围。
    const taskIds = [...new Set(selectedIds)]
    if (!taskIds.length) {
      options.onMessage('请至少选择一个失败任务')
      return
    }
    running = true
    options.onRunningChange(true)
    let succeeded = 0
    try {
      for (let start = 0; start < taskIds.length; start += TASK_RETRY_BATCH_SIZE) {
        const batch = taskIds.slice(start, start + TASK_RETRY_BATCH_SIZE)
        let result: { total: number }
        try {
          result = await options.submit(batch)
        } catch (error) {
          const prefix = succeeded ? `已将 ${succeeded} 个失败任务重新入队；后续批次已停止。` : ''
          options.onMessage(prefix + taskBatchRetryError(error))
          return
        }
        succeeded += result.total
        options.onSucceeded(batch)
      }
      const message = `已将 ${succeeded} 个失败任务重新入队`
      try {
        await options.refresh()
        options.onMessage(message)
      } catch {
        options.onMessage(`${message}；列表刷新失败，请刷新页面查看`)
      }
    } finally {
      running = false
      options.onRunningChange(false)
    }
  }

  return { run }
}
