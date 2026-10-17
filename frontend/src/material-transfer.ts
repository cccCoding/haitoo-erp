export type TransferOutcome = 'created' | 'duplicate'
export interface TransferResult { outcome: TransferOutcome | 'error'; error?: string }
export interface MaterialTransferItem {
  id: string
  label: string
  preview?: string
  outcome: 'pending' | 'running' | 'created' | 'duplicate' | 'error'
  error?: string
  selected: boolean
  requestKey: string
  force: boolean
  run: (force: boolean, requestKey: string) => Promise<TransferResult>
}
export function transferItem(label: string, run: MaterialTransferItem['run'], preview?: string): MaterialTransferItem {
  return { id: crypto.randomUUID(), label, preview, outcome: 'pending', selected: false,
    requestKey: crypto.randomUUID(), force: false, run }
}
export async function imageSha256(file: Blob): Promise<string> {
  const bytes = new Uint8Array(await crypto.subtle.digest('SHA-256', await file.arrayBuffer()))
  return Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('')
}
export function deduplicatedImageUpload(upload: (file: Blob, sha256: string) => Promise<string>) {
  const pending = new Map<string, Promise<string>>()
  return async (file: Blob): Promise<string> => {
    const sha256 = await imageSha256(file)
    let result = pending.get(sha256)
    if (!result) {
      result = upload(file, sha256).catch(error => { pending.delete(sha256); throw error })
      pending.set(sha256, result)
    }
    return result
  }
}
export async function runMaterialTransfers(items: MaterialTransferItem[], canContinue: () => boolean, concurrency = 4) {
  let cursor = 0
  async function worker() {
    while (canContinue()) {
      const item = items[cursor++]
      if (!item) return
      if (item.outcome !== 'pending') continue
      item.outcome = 'running'
      try {
        const result = await item.run(item.force, item.requestKey)
        item.outcome = result.outcome
        item.error = result.error
      } catch (error: any) {
        item.outcome = 'error'
        item.error = error.response?.data?.detail || error.message || '处理失败，请重试'
      }
    }
  }
  await Promise.all(Array.from({ length: Math.min(concurrency, items.length) }, worker))
}
