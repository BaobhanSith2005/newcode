// 后端请求封装 —— 同款见 AIRoomBuilder/frontend/src/api/index.ts
import axios from 'axios'

const http = axios.create({ baseURL: '/api', timeout: 180_000 })

// 一段文字的翻译 —— 跟后端 schemas.py 的 TranslateText 一一对应
export interface TranslateText { original: string; translation: string }

// 图片任务 —— 跟后端 ImageOut 一一对应
export interface ImageTask {
  id: number
  batch_id: number | null   // 所属批次；漫画图为 null
  filename: string
  order: number             // 批次内页码顺序
  status: 'pending' | 'running' | 'done' | 'failed'
  error?: string | null
  result?: { texts: TranslateText[] } | null
  style: string
  created_at: string
}

// 小说批次 —— 跟后端 BatchOut 一一对应
export interface Batch { id: number; name: string; created_at: string }

export const api = {
  health: () => http.get<{ ok: boolean }>('/health').then((r) => r.data),

  // 上传图片。漫画图不传 opts；小说书页图传 { batchId, order }
  uploadImage: (file: File, opts?: { batchId?: number; order?: number }) => {
    const fd = new FormData()
    fd.append('file', file)
    if (opts?.batchId != null) fd.append('batch_id', String(opts.batchId))
    if (opts?.order != null) fd.append('order', String(opts.order))
    return http.post<ImageTask>('/images/upload', fd).then((r) => r.data)
  },

  getResult: (imageId: number) =>
    http.get<ImageTask>(`/images/${imageId}/result`).then((r) => r.data),

  // ---- 批次 ----
  createBatch: (name: string) =>
    http.post<Batch>('/batches', { name }).then((r) => r.data),
  listBatches: () => http.get<Batch[]>('/batches').then((r) => r.data),
  listBatchImages: (batchId: number) =>
    http.get<ImageTask[]>(`/batches/${batchId}/images`).then((r) => r.data),
  deleteBatch: (batchId: number) =>
    http.delete(`/batches/${batchId}`).then((r) => r.data),

  // 调序：direction 是 up/down。axios 的 params 会自动拼成 ?direction=up
  // —— 跟后端 Query("up") 是配套的
  moveImage: (batchId: number, imageId: number, direction: 'up' | 'down') =>
    http.post<ImageTask[]>(`/batches/${batchId}/images/${imageId}/move`, null, {
      params: { direction },
    }).then((r) => r.data),
}

// 轮询等到翻译结束 —— 同款思路见 AIRoomBuilder workspace.ts
export async function waitForResult(
  imageId: number,
  onTick?: (status: string) => void,
  timeoutMs = 180_000,
): Promise<ImageTask> {
  const started = Date.now()
  for (;;) {
    const res = await api.getResult(imageId)
    onTick?.(res.status)
    if (res.status === 'done' || res.status === 'failed') return res
    if (Date.now() - started > timeoutMs) throw new Error('翻译超时')
    await new Promise((r) => setTimeout(r, 1500))
  }
}

