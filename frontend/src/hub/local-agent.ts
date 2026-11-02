export const LOCAL_AGENT_URL = 'http://127.0.0.1:45679'
export type LocalAgentState = 'checking' | 'ready' | 'legacy' | 'unreachable'

export function healthState(value: unknown): LocalAgentState {
  if (!value || typeof value !== 'object') return 'unreachable'
  const body = value as Record<string, unknown>
  if (body.status !== 'ready') return 'unreachable'
  return body.application === 'haitoo-hub-agent' && body.protocol === 5 && body.mode === 'connector' ? 'ready' : 'legacy'
}

export async function probeLocalAgent(signal?: AbortSignal, request: typeof fetch = fetch): Promise<LocalAgentState> {
  const controller = new AbortController()
  const abort = () => controller.abort()
  if (signal?.aborted) controller.abort()
  signal?.addEventListener('abort', abort, { once: true })
  const timeout = setTimeout(abort, 2000)
  try {
    const response = await request(`${LOCAL_AGENT_URL}/health`, {
      method: 'GET', mode: 'cors', credentials: 'omit', cache: 'no-store',
      redirect: 'error', signal: controller.signal,
    })
    return response.ok ? healthState(await response.json()) : 'unreachable'
  } catch {
    return 'unreachable'
  } finally {
    clearTimeout(timeout)
    signal?.removeEventListener('abort', abort)
  }
}
