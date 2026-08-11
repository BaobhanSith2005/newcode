<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { computed, onMounted, ref } from 'vue'

import SceneCanvas from '@/components/SceneCanvas.vue'
import { demoScene } from '@/assets/demoScene'
import { useWorkspace } from '@/stores/workspace'

const ws = useWorkspace()
const canvas = ref<InstanceType<typeof SceneCanvas>>()
const selected = ref<string | null>(null)
const viewMode = ref<'free' | 'top'>('free')
const showJson = ref(false)

const busy = computed(() => ['uploading', 'analyzing', 'building'].includes(ws.stage))
const objects = computed(() => ws.scene?.objects ?? [])

const roomSourceTag = computed(() => {
  const s = ws.scene?.room?.size_source
  return (
    { model: '模型估算', preset: '房型预设', user: '已手动调整' } as Record<string, string>
  )[s ?? ''] ?? ''
})

onMounted(() => {
  void ws.loadHealth()
})

function onFileChange(ev: Event) {
  const input = ev.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  void ws.runPipeline(file).then(() => {
    if (ws.stage === 'error') ElMessage.error(ws.message)
    else ElMessage.success(ws.message)
  })
  input.value = ''
}

function setView(mode: 'free' | 'top') {
  viewMode.value = mode
  canvas.value?.setViewMode(mode)
}

function exportScene() {
  if (!ws.scene) return
  const blob = new Blob([JSON.stringify(ws.scene, null, 2)], { type: 'application/json' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `${ws.scene.scene_id ?? 'scene'}.json`
  a.click()
  URL.revokeObjectURL(a.href)
}

function snapshot() {
  const url = canvas.value?.screenshot()
  if (!url) return
  const a = document.createElement('a')
  a.href = url
  a.download = 'room.png'
  a.click()
}

const providerTag = computed(() => {
  if (ws.model && ws.model !== 'mock') return ws.model
  const map: Record<string, string> = {
    mock: '示例数据模式', dashscope: 'Qwen-VL',
    openai: 'OpenAI', gemini: 'Gemini', offline: '后端未连接'
  }
  return map[ws.provider] ?? ws.provider
})
</script>

<template>
  <div class="app">
    <header class="topbar">
      <div class="brand">
        <span class="logo">AI</span>
        <div>
          <div class="title">AI Room Builder</div>
          <div class="subtitle">室内空间理解与三维场景生成</div>
        </div>
      </div>
      <div class="topbar-right">
        <el-tag :type="ws.provider === 'mock' ? 'warning' : 'success'" size="small" effect="light">
          {{ providerTag }}
        </el-tag>
        <el-button-group size="small">
          <el-button :type="viewMode === 'free' ? 'primary' : 'default'" @click="setView('free')">
            自由视角
          </el-button>
          <el-button :type="viewMode === 'top' ? 'primary' : 'default'" @click="setView('top')">
            俯视图
          </el-button>
        </el-button-group>
        <el-button size="small" @click="snapshot" :disabled="!ws.scene">截图</el-button>
        <el-button size="small" @click="exportScene" :disabled="!ws.scene">导出 JSON</el-button>
      </div>
    </header>

    <main class="body">
      <aside class="panel">
        <section class="block">
          <div class="block-title">1 · 上传房间照片</div>
          <label class="uploader" :class="{ disabled: busy }">
            <input type="file" accept="image/*" hidden :disabled="busy" @change="onFileChange" />
            <div class="uploader-icon">+</div>
            <div class="uploader-text">点击选择图片</div>
            <div class="uploader-hint">JPG / PNG / WebP，≤ 20MB</div>
          </label>

          <div v-if="ws.stage !== 'idle'" class="status" :class="ws.stage">
            <el-icon v-if="busy" class="spin"><svg viewBox="0 0 1024 1024" width="14" height="14">
              <path fill="currentColor" d="M512 96a416 416 0 1 1 0 832 416 416 0 0 1 0-832zm0 64a352 352 0 1 0 0 704 352 352 0 0 0 0-704z" opacity=".3"/>
              <path fill="currentColor" d="M512 96a416 416 0 0 1 416 416h-64a352 352 0 0 0-352-352V96z"/>
            </svg></el-icon>
            <span>{{ ws.message }}</span>
          </div>

          <el-button
            v-if="!ws.image" text size="small" class="demo-link"
            @click="ws.loadDemoScene(demoScene)"
          >
            加载内置示例场景
          </el-button>
        </section>

        <section class="block" v-if="ws.scene">
          <div class="block-title">
            2 · 房间尺寸（米）
            <span v-if="roomSourceTag" class="src-tag">{{ roomSourceTag }}</span>
          </div>
          <div class="hint">
            尺寸由房间类型预设，手动微调比深度估计更准。调整后会重新求解布局。
          </div>
          <div class="slider-row">
            <span class="slider-label">宽</span>
            <el-slider v-model="ws.room.width" :min="2" :max="12" :step="0.1" size="small" />
            <span class="slider-value">{{ ws.room.width.toFixed(1) }}</span>
          </div>
          <div class="slider-row">
            <span class="slider-label">深</span>
            <el-slider v-model="ws.room.depth" :min="2" :max="12" :step="0.1" size="small" />
            <span class="slider-value">{{ ws.room.depth.toFixed(1) }}</span>
          </div>
          <div class="slider-row">
            <span class="slider-label">高</span>
            <el-slider v-model="ws.room.height" :min="2.2" :max="4" :step="0.05" size="small" />
            <span class="slider-value">{{ ws.room.height.toFixed(2) }}</span>
          </div>
          <el-button
            size="small" type="primary" plain style="width: 100%"
            :disabled="!ws.image || busy" @click="ws.rebuildWithRoom()"
          >
            按新尺寸重新布局
          </el-button>
          <div v-if="!ws.image" class="hint tiny">示例场景不支持重建，上传图片后可用</div>
        </section>

        <section class="block grow" v-if="objects.length">
          <div class="block-title">
            3 · 识别结果
            <span class="count">{{ objects.length }} 件</span>
          </div>
          <ul class="obj-list">
            <li
              v-for="o in objects" :key="o.id"
              :class="{ active: selected === o.id }"
              @click="selected = selected === o.id ? null : o.id"
            >
              <span class="swatch" :style="{ background: (o.material?.color || o.color) }" />
              <div class="obj-main">
                <div class="obj-name">{{ o.label || o.category }}</div>
                <div class="obj-meta color-row">
                  颜色：{{ o.material?.name || '' }} {{ o.material?.color || o.color }}
                </div>
                <div class="obj-meta">
                  {{ o.size.w }}×{{ o.size.d }}×{{ o.size.h }} m
                  <template v-if="o.against_wall"> · 靠{{ o.against_wall }}墙</template>
                </div>
              </div>
              <span
                class="conf"
                :class="{ low: (o.confidence ?? 1) < 0.7 }"
              >{{ Math.round((o.confidence ?? 0) * 100) }}%</span>
            </li>
          </ul>
        </section>

        <section class="block" v-if="ws.scene">
          <el-button text size="small" @click="showJson = !showJson">
            {{ showJson ? '收起' : '查看' }} scene.json
          </el-button>
          <pre v-if="showJson" class="json">{{ JSON.stringify(ws.scene, null, 2) }}</pre>
        </section>
      </aside>

      <div class="viewport">
        <SceneCanvas
          ref="canvas" :scene="ws.scene" :selected="selected"
          @select="(id) => (selected = id)"
        />
      </div>
    </main>
  </div>
</template>

<style scoped>
.app { display: flex; flex-direction: column; height: 100vh; background: #f5f6f8; }

.topbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 18px; background: #fff; border-bottom: 1px solid #e5e7eb;
}
.brand { display: flex; align-items: center; gap: 10px; }
.logo {
  width: 32px; height: 32px; border-radius: 8px; display: grid; place-items: center;
  background: linear-gradient(135deg, #4f7cf7, #7d5bf5); color: #fff;
  font-weight: 700; font-size: 13px;
}
.title { font-size: 15px; font-weight: 600; color: #1f2430; line-height: 1.2; }
.subtitle { font-size: 11px; color: #8a9099; }
.topbar-right { display: flex; align-items: center; gap: 10px; }

.body { flex: 1; display: flex; min-height: 0; }

.panel {
  width: 318px; flex-shrink: 0; background: #fff; border-right: 1px solid #e5e7eb;
  display: flex; flex-direction: column; overflow-y: auto;
}
.block { padding: 14px 16px; border-bottom: 1px solid #f0f1f3; }
.block.grow { flex: 1; min-height: 0; display: flex; flex-direction: column; }
.block-title {
  font-size: 12px; font-weight: 600; color: #4b5563; margin-bottom: 10px;
  display: flex; align-items: center; justify-content: space-between;
}
.count { font-weight: 400; color: #9aa0a8; }
.src-tag {
  font-size: 10px; font-weight: 500; color: #6d8ef0; background: #eef3ff;
  padding: 2px 7px; border-radius: 10px; margin-left: 8px;
}
.hint { font-size: 11px; color: #9aa0a8; line-height: 1.6; margin-bottom: 10px; }
.hint.tiny { margin: 8px 0 0; }

.uploader {
  display: flex; flex-direction: column; align-items: center; gap: 4px;
  padding: 20px 12px; border: 1.5px dashed #d3d7de; border-radius: 8px;
  cursor: pointer; transition: all .15s; background: #fafbfc;
}
.uploader:hover { border-color: #4f7cf7; background: #f5f8ff; }
.uploader.disabled { opacity: .5; pointer-events: none; }
.uploader-icon { font-size: 22px; color: #b0b6bf; line-height: 1; }
.uploader-text { font-size: 13px; color: #4b5563; }
.uploader-hint { font-size: 11px; color: #a8aeb6; }
.demo-link { margin-top: 6px; padding: 0; }

.status {
  margin-top: 10px; padding: 7px 10px; border-radius: 6px; font-size: 12px;
  display: flex; align-items: center; gap: 6px; background: #f3f4f6; color: #4b5563;
}
.status.ready { background: #ecfdf3; color: #1f7a45; }
.status.error { background: #fef2f2; color: #b42318; }
.spin { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.slider-row { display: flex; align-items: center; gap: 10px; margin-bottom: 4px; }
.slider-label { font-size: 12px; color: #6b7280; width: 16px; }
.slider-row :deep(.el-slider) { flex: 1; }
.slider-value { font-size: 12px; color: #4b5563; width: 34px; text-align: right; font-variant-numeric: tabular-nums; }

.obj-list { list-style: none; margin: 0; padding: 0; overflow-y: auto; flex: 1; }
.obj-list li {
  display: flex; align-items: center; gap: 9px; padding: 7px 8px;
  border-radius: 6px; cursor: pointer; transition: background .12s;
}
.obj-list li:hover { background: #f5f6f8; }
.obj-list li.active { background: #eef3ff; }
.swatch { width: 12px; height: 12px; border-radius: 3px; flex-shrink: 0; border: 1px solid rgba(0,0,0,.08); }
.obj-main { flex: 1; min-width: 0; }
.obj-name { font-size: 12.5px; color: #1f2430; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.obj-meta { font-size: 10.5px; color: #9aa0a8; }
.color-row { margin-bottom: 1px; }
.conf { font-size: 10.5px; color: #7d8590; font-variant-numeric: tabular-nums; }
.conf.low { color: #d97706; }

.json {
  margin: 8px 0 0; padding: 10px; background: #f8f9fa; border-radius: 6px;
  font-size: 10.5px; line-height: 1.5; max-height: 300px; overflow: auto;
  color: #444; white-space: pre-wrap; word-break: break-all;
}

.viewport { flex: 1; min-width: 0; }
</style>
