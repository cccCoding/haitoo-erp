export interface CreativeUploadAsset {
  file: Blob
  uploadedUrl?: string
  skippedReason?: string
}

export interface CreativeSubmissionNotice {
  message: string
  skipped: { id: string; name: string; reason: string }[]
}

export async function uploadCreativeImages(
  assets: CreativeUploadAsset[],
  upload: (file: Blob) => Promise<string>,
): Promise<string[]> {
  const snapshot = [...assets]
  const urls: (string | undefined)[] = Array(snapshot.length)
  let cursor = 0
  async function worker() {
    while (true) {
      const index = cursor++
      if (index >= snapshot.length) return
      const asset = snapshot[index]
      if (asset.skippedReason) continue
      if (asset.uploadedUrl) { urls[index] = asset.uploadedUrl; continue }
      try {
        asset.uploadedUrl = await upload(asset.file)
        urls[index] = asset.uploadedUrl
      } catch (error: any) {
        if (error.response?.status !== 400 || error.response?.data?.code !== 'invalid_image') throw error
        asset.skippedReason = error.response.data.detail || '图片内容损坏或不是有效图片'
      }
    }
  }
  // 即使其他上传失败，也等待全部线程收尾，确保重试不会与残留上传重叠。
  const results = await Promise.allSettled(Array.from({ length: Math.min(4, snapshot.length) }, worker))
  const failed = results.find((result): result is PromiseRejectedResult => result.status === 'rejected')
  if (failed) throw failed.reason
  return [...new Set(urls.filter((url): url is string => Boolean(url)))]
}
