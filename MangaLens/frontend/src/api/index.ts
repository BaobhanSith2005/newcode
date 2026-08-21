// 后端请求封装 —— 同款见 AIRoomBuilder/frontend/src/api/index.ts
import axios from 'axios'

const http = axios.create({ baseURL: '/api', timeout: 180_000 })

// 一段文字的翻译 —— 跟后端 schemas.py 的 TranslateText 一一对应
export interface TranslateText { original: string; translation: string }

// 图片任务 —— 跟后端 ImageOut 一一对应
export interface ImageTask {
  id: number
  batch_id: number | null   // 所属批次；散图（不属于任何批次）为 null
  filename: string
  order: number             // 批次内页码顺序
  status: 'pending' | 'running' | 'done' | 'failed'
  error?: string | null
  progress?: string | null   // 阶段进度文字（"② 云端翻译中（已过 X 秒）…"），对应后端 progress 字段
  result?: { texts: TranslateText[] } | null
  style: string
  created_at: string
}

// 批次 —— 跟后端 BatchOut 一一对应；kind 区分板块：novel 小说 / manga 漫画
export interface Batch { id: number; name: string; kind: 'novel' | 'manga'; created_at: string }

// 文本文件翻译任务（小说 txt/epub）—— 跟后端 DocOut 一一对应
export interface DocTask {
  id: number
  filename: string
  file_type: string
  status: 'pending' | 'running' | 'done' | 'failed'
  error?: string | null
  style: string
  created_at: string
}

export const api = {
  health: () => http.get<{ ok: boolean }>('/health').then((r) => r.data),

  // 上传图片。散图不传 opts；书页图/漫画图传 { batchId, order }
  uploadImage: (file: File, opts?: { batchId?: number; order?: number }) => {
    const fd = new FormData()
    fd.append('file', file)
    if (opts?.batchId != null) fd.append('batch_id', String(opts.batchId))
    if (opts?.order != null) fd.append('order', String(opts.order))
    return http.post<ImageTask>('/images/upload', fd).then((r) => r.data)
  },

  getResult: (imageId: number) =>
    http.get<ImageTask>(`/images/${imageId}/result`).then((r) => r.data),

  // 重跑嵌字：失败重试用；done 之后也可以重嵌换个效果（后端只在 running 时 409 拦截）
  renderImage: (imageId: number) =>
    http.post<ImageTask>(`/images/${imageId}/render`).then((r) => r.data),

  // ---- 批次 ----
  // 创建批次：kind 区分板块——novel 小说书页（合成txt）/ manga 漫画图（批量嵌字）
  createBatch: (name: string, kind: 'novel' | 'manga' = 'novel') =>
    http.post<Batch>('/batches', { name, kind }).then((r) => r.data),
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

  // ---- 小说 txt 翻译 ----
  uploadDoc: (file: File, style?: string) => {
    const fd = new FormData()
    fd.append('file', file)
    if (style) fd.append('style', style)
    return http.post<DocTask>('/docs/upload', fd).then((r) => r.data)
  },
  getDocResult: (docId: number) =>
    http.get<DocTask>(`/docs/${docId}/result`).then((r) => r.data),
}

// 轮询等到翻译结束 —— 同款思路见 AIRoomBuilder workspace.ts
export async function waitForResult(
  imageId: number,
  onTick?: (task: ImageTask) => void,
  timeoutMs = 180_000,
): Promise<ImageTask> {
  const started = Date.now()
  for (;;) {
    const res = await api.getResult(imageId)
    // 心跳回调传整个 task：前端要显示 progress 进度文字，只传 status 不够用
    onTick?.(res)
    if (res.status === 'done' || res.status === 'failed') return res
    if (Date.now() - started > timeoutMs) throw new Error('翻译超时')
    await new Promise((r) => setTimeout(r, 1500))
  }
}

// 轮询文档翻译（同款 waitForResult）。
// 超时给到 10 分钟：整本小说切几十块，逐块翻译要花不少时间。
export async function waitForDocResult(
  docId: number,
  onTick?: (status: string) => void,
  timeoutMs = 600_000,
): Promise<DocTask> {
  const started = Date.now()
  for (;;) {
    const res = await api.getDocResult(docId)
    onTick?.(res.status)
    if (res.status === 'done' || res.status === 'failed') return res
    if (Date.now() - started > timeoutMs) throw new Error('翻译超时')
    await new Promise((r) => setTimeout(r, 1500))
  }
}

