import axios from 'axios'

import type { SceneJSON } from '@/types/scene'

const http = axios.create({ baseURL: '/api', timeout: 180_000 })

export interface Project {
  id: number
  name: string
  created_at: string
}

export interface ImageInfo {
  id: number
  project_id: number
  filename: string
  width: number
  height: number
  status: 'pending' | 'running' | 'done' | 'failed'
  error?: string | null
  created_at: string
}

export interface AnalysisResult {
  image_id: number
  status: string
  error?: string | null
  analysis: Record<string, unknown> | null
}

export interface SceneRecord {
  id: number
  project_id: number
  image_id: number | null
  scene: SceneJSON
  created_at: string
  updated_at: string
}

export interface HealthResponse {
  ok: boolean
  vision_provider: string
  vision_model: string
  configured_provider: string
  note: string
}

export const api = {
  health: () => http.get<HealthResponse>('/health').then((r) => r.data),

  createProject: (name: string) =>
    http.post<Project>('/projects', { name }).then((r) => r.data),
  listProjects: () => http.get<Project[]>('/projects').then((r) => r.data),

  uploadImage: (projectId: number, file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return http
      .post<ImageInfo>('/images/upload', fd, { params: { project_id: projectId } })
      .then((r) => r.data)
  },
  listImages: (projectId: number) =>
    http.get<ImageInfo[]>('/images', { params: { project_id: projectId } }).then((r) => r.data),
  getAnalysis: (imageId: number) =>
    http.get<AnalysisResult>(`/images/${imageId}/analysis`).then((r) => r.data),
  reanalyze: (imageId: number) =>
    http.post<ImageInfo>(`/images/${imageId}/reanalyze`).then((r) => r.data),

  generateScene: (imageId: number, room?: { width?: number; depth?: number; height?: number }) =>
    http.post<SceneRecord>('/scenes/generate', { image_id: imageId, room }).then((r) => r.data),
  listScenes: (projectId: number) =>
    http.get<SceneRecord[]>('/scenes', { params: { project_id: projectId } }).then((r) => r.data),
  updateScene: (sceneId: number, scene: SceneJSON) =>
    http.put<SceneRecord>(`/scenes/${sceneId}`, { scene }).then((r) => r.data)
}

/** 轮询等待后台分析任务完成 */
export async function waitForAnalysis(
  imageId: number,
  onTick?: (status: string) => void,
  timeoutMs = 180_000
): Promise<AnalysisResult> {
  const started = Date.now()
  for (;;) {
    const res = await api.getAnalysis(imageId)
    onTick?.(res.status)
    if (res.status === 'done' || res.status === 'failed') return res
    if (Date.now() - started > timeoutMs) throw new Error('分析超时')
    await new Promise((r) => setTimeout(r, 1200))
  }
}
