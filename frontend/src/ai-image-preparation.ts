export interface AICandidate {
  id: number
  source_url: string
  display_url: string
  state: string
  error?: string | null
  expires_at?: number | null
}
export interface AIPreparation {
  id: number
  state: string
  total: number
  ready: number
  failed: number
  items: { candidate_id: number; state: string; source_url: string; url?: string | null; error?: string | null }[]
}
export function candidateUnavailable(candidate?: AICandidate, at = Date.now()) {
  return Boolean(candidate && candidate.state !== 'ready' && (['invalid', 'expired'].includes(candidate.state)
    || candidate.expires_at != null && candidate.expires_at <= at))
}
export function preparationError(data: AIPreparation) {
  return data.items.filter(item => ['failed', 'invalid', 'expired'].includes(item.state))
    .slice(0, 5).map(item => `图片 #${item.candidate_id}：${item.error || (item.state === 'expired' ? '已过期' : '准备失败')}`).join('；')
}

/** 仅提交对象身份并轮询状态；不获取或处理任何图片字节。 */
export function createImagePreparer(client: any, authorization: () => string,
  progress: (value: AIPreparation) => void, pause = (ms: number) => new Promise<void>(resolve => setTimeout(resolve, ms)),
  created?: (value: AIPreparation) => void) {
  let generation = 0
  async function wait(data: AIPreparation, headers: any, current: number) {
    while (true) {
      if (current !== generation) throw new Error('已停止等待；后台图片准备会继续，可再次确认审核')
      progress(data)
      if (data.state === 'ready') return data
      if (['failed', 'partial_failed'].includes(data.state)) throw new Error(preparationError(data))
      await pause(1000)
      if (current !== generation) throw new Error('已停止等待；后台图片准备会继续')
      data = (await client.get(`/ai-image-preparations/${data.id}`, { headers })).data
    }
  }
  return {
    cancel() { generation++ },
    async prepare(ids: number[]) {
      const headers = { Authorization: authorization() }, current = generation
      let result: AIPreparation | undefined
      const unique = [...new Set(ids)]
      for (let offset = 0; offset < unique.length; offset += 1000) {
        const { data } = await client.post('/ai-image-preparations', {
          candidate_ids: unique.slice(offset, offset + 1000), request_key: crypto.randomUUID(),
        }, { headers })
        // 关闭等待可能发生在创建响应之前；保留任务身份，便于恢复后台进度。
        if (headers.Authorization === authorization()) created?.(data)
        result = await wait(data, headers, current)
      }
      return result
    },
    async retry(id: number) {
      const headers = { Authorization: authorization() }, current = generation
      const { data } = await client.post(`/ai-image-preparations/${id}/retry`, {}, { headers })
      return wait(data, headers, current)
    },
    async resume(id: number) {
      const headers = { Authorization: authorization() }, current = generation
      const { data } = await client.get(`/ai-image-preparations/${id}`, { headers })
      return wait(data, headers, current)
    },
  }
}
