// 搜索优先于轮询；一次只保留一个请求，并丢弃被替换请求的迟到结果。
export function createTaskPageLoader<Params, Page>(
  fetchPage: (params: Params, signal: AbortSignal) => Promise<Page>,
  applyPage: (page: Page) => void,
) {
  let current: AbortController | undefined

  return {
    async load(params: Params, options: { background?: boolean } = {}) {
      if (options.background && current) return
      current?.abort()
      const controller = new AbortController()
      current = controller
      try {
        const page = await fetchPage(params, controller.signal)
        if (current === controller) applyPage(page)
      } catch (error) {
        if (current === controller && !controller.signal.aborted) throw error
      } finally {
        if (current === controller) current = undefined
      }
    },
    cancel() {
      current?.abort()
      current = undefined
    },
  }
}
