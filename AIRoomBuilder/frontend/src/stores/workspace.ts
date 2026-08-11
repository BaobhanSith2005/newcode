import { defineStore } from 'pinia'
import { ref } from 'vue'

import { api, waitForAnalysis, type ImageInfo, type Project } from '@/api'
import type { SceneJSON } from '@/types/scene'

export const useWorkspace = defineStore('workspace', () => {
  const project = ref<Project | null>(null)
  const image = ref<ImageInfo | null>(null)
  const analysis = ref<Record<string, unknown> | null>(null)
  const scene = ref<SceneJSON | null>(null)
  const sceneId = ref<number | null>(null)

  const stage = ref<'idle' | 'uploading' | 'analyzing' | 'building' | 'ready' | 'error'>('idle')
  const message = ref('')
  const provider = ref('unknown')
  const model = ref('')

  // 房间尺寸由用户微调——比深度估计可靠得多，成本也低得多
  const room = ref({ width: 0, depth: 0, height: 0 })

  async function ensureProject() {
    if (project.value) return project.value
    const list = await api.listProjects()
    project.value = list[0] ?? (await api.createProject('默认项目'))
    return project.value
  }

  async function loadHealth() {
    try {
      const h = await api.health()
      provider.value = h.vision_provider
      model.value = h.vision_model
    } catch {
      provider.value = 'offline'
      model.value = ''
    }
  }

  async function runPipeline(file: File) {
    try {
      stage.value = 'uploading'
      message.value = '正在上传图片…'
      const p = await ensureProject()

      const img = await api.uploadImage(p.id, file)
      image.value = img

      stage.value = 'analyzing'
      message.value = '视觉模型分析中…'
      const res = await waitForAnalysis(img.id, (s) => {
        message.value = s === 'running' ? '视觉模型分析中…' : '任务排队中…'
      })
      if (res.status === 'failed') throw new Error(res.error || '分析失败')
      analysis.value = res.analysis

      stage.value = 'building'
      message.value = '生成三维场景…'
      const rec = await api.generateScene(img.id)
      scene.value = rec.scene
      sceneId.value = rec.id
      room.value = {
        width: rec.scene.room.width,
        depth: rec.scene.room.depth,
        height: rec.scene.room.height
      }

      stage.value = 'ready'
      message.value = `识别到 ${rec.scene.objects.length} 件家具`
    } catch (e) {
      stage.value = 'error'
      message.value = e instanceof Error ? e.message : String(e)
    }
  }

  /** 用户调整房间尺寸后按新尺寸重建（布局会等比缩放并重新求解） */
  async function rebuildWithRoom() {
    if (!image.value) return
    stage.value = 'building'
    message.value = '按新尺寸重新布局…'
    try {
      const rec = await api.generateScene(image.value.id, { ...room.value })
      scene.value = rec.scene
      sceneId.value = rec.id
      stage.value = 'ready'
      message.value = `已按 ${room.value.width}×${room.value.depth} m 重建`
    } catch (e) {
      stage.value = 'error'
      message.value = e instanceof Error ? e.message : String(e)
    }
  }

  function loadDemoScene(demo: SceneJSON) {
    scene.value = demo
    sceneId.value = null
    room.value = { width: demo.room.width, depth: demo.room.depth, height: demo.room.height }
    stage.value = 'ready'
    message.value = '已加载内置示例场景'
  }

  return {
    project, image, analysis, scene, sceneId, stage, message, provider, model, room,
    ensureProject, loadHealth, runPipeline, rebuildWithRoom, loadDemoScene
  }
})
