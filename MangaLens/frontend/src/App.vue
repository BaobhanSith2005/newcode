<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { api, waitForResult, type Batch, type ImageTask } from '@/api'

// ----------------------------------------------------------------
// 板块切换 —— 同款见 AIRoomBuilder App.vue 第12行 viewMode
// ----------------------------------------------------------------
type TabKey = 'manga' | 'novel'
const activeTab = ref<TabKey>('manga')

// ----------------------------------------------------------------
// 漫画任务列表 —— 每项是后端返回的真实 ImageTask
// ----------------------------------------------------------------
const mangaTasks = ref<ImageTask[]>([])

// ----------------------------------------------------------------
// 批量上传 + 逐个翻译（漫画）
// 同款思路见 AIRoomBuilder workspace.ts 第40-74行 runPipeline
// ----------------------------------------------------------------
async function onMangaFilesChange(ev: Event) {
  const input = ev.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  if (!files.length) return
  input.value = ''

  // ① 先为每个文件建一个"占位任务"，立刻显示在列表里（status 暂标 pending）
  const placeholders: ImageTask[] = files.map((f, i) => ({
    id: -i - 1,                                  // 负数临时ID：真实ID要等后端分配
    batch_id: null,
    filename: f.name,
    order: 0,
    status: 'pending' as const,
    style: '直译',
    created_at: new Date().toISOString(),
  }))
  mangaTasks.value.push(...placeholders)

  // ② 逐个处理：上传 → 轮询 → 用真实数据替换占位
  for (let i = 0; i < files.length; i++) {
    const placeholder = placeholders[i]
    // current：始终指向"列表里现在那个对象"。
    // 占位(id=-1)被真实任务(id=1)替换后，列表里存的是新对象——
    // 再拿旧对象按 id 去列表里找就找不到了，所以每次替换后 current 要跟着换。
    let current: ImageTask = placeholder
    try {
      const task = await api.uploadImage(files[i])
      replaceTask(current, task)
      current = task
      const done = await waitForResult(task.id, (status) => {
        updateTaskStatus(current, status)
      })
      replaceTask(current, done)
    } catch (e) {
      replaceTask(current, {
        ...current,
        status: 'failed',
        error: e instanceof Error ? e.message : String(e),
      })
    }
  }
}

function replaceTask(oldTask: ImageTask, newTask: ImageTask) {
  const idx = mangaTasks.value.findIndex((t) => t.id === oldTask.id)
  if (idx !== -1) mangaTasks.value[idx] = newTask
}

function updateTaskStatus(task: ImageTask, status: string) {
  const idx = mangaTasks.value.findIndex((t) => t.id === task.id)
  if (idx !== -1) {
    mangaTasks.value[idx] = { ...mangaTasks.value[idx], status: status as ImageTask['status'] }
  }
}

// ----------------------------------------------------------------
// 小说板块：批次管理
// ----------------------------------------------------------------
const novelBatches = ref<Batch[]>([])
const currentBatchId = ref<number | null>(null)
const novelImages = ref<ImageTask[]>([])
const newBatchName = ref('')

onMounted(() => {
  void loadBatches()
})

async function loadBatches() {
  novelBatches.value = await api.listBatches()
}

async function createNovelBatch() {
  const name = newBatchName.value.trim()
  if (!name) return alert('先填批次名（比如书名）')
  const batch = await api.createBatch(name)
  newBatchName.value = ''
  await loadBatches()
  currentBatchId.value = batch.id
  await refreshBatchImages()
}

async function deleteNovelBatch() {
  if (currentBatchId.value == null) return
  if (!confirm('删除这个批次和它下面所有图片记录？')) return
  await api.deleteBatch(currentBatchId.value)
  currentBatchId.value = null
  novelImages.value = []
  await loadBatches()
}

// ----------------------------------------------------------------
// 小说板块：传书页图 + 调序
// ----------------------------------------------------------------
async function refreshBatchImages() {
  if (currentBatchId.value == null) return
  novelImages.value = await api.listBatchImages(currentBatchId.value)
}

async function onNovelFilesChange(ev: Event) {
  const input = ev.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  if (!files.length) return
  input.value = ''
  if (currentBatchId.value == null) {
    alert('请先新建或选择一个批次')
    return
  }
  const batchId = currentBatchId.value

  // 逐个上传：order = 批次里现有张数 + 序号（继续往后排页码）
  const startOrder = novelImages.value.length
  for (let i = 0; i < files.length; i++) {
    try {
      const task = await api.uploadImage(files[i], { batchId, order: startOrder + i })
      await refreshBatchImages()          // 传一张，列表里就多一张
      void pollUntilDone(task.id)         // 后台轮询这张，不阻塞下一张上传
    } catch (e) {
      alert(`${files[i].name} 上传失败：${e instanceof Error ? e.message : e}`)
    }
  }
}

// 后台轮询单张，完成后刷新列表。void 开头 = 点着了不等着，继续干别的。
async function pollUntilDone(imageId: number) {
  await waitForResult(imageId, (status) => {
    const img = novelImages.value.find((t) => t.id === imageId)
    if (img) img.status = status as ImageTask['status']
  })
  await refreshBatchImages()
}

async function moveImageInBatch(img: ImageTask, direction: 'up' | 'down') {
  if (currentBatchId.value == null) return
  try {
    // 后端换完号会返回新的完整顺序，直接替换整个列表
    novelImages.value = await api.moveImage(currentBatchId.value, img.id, direction)
  } catch (e) {
    alert(e instanceof Error ? e.message : '移动失败')
  }
}

// 状态显示文字 + 颜色 —— 同款思路见 AIRoomBuilder App.vue 第15行 busy
function statusTag(status: string) {
  const map: Record<string, { text: string; type: 'info' | 'warning' | 'success' | 'danger' }> = {
    pending: { text: '排队中', type: 'info' },
    running: { text: '翻译中', type: 'warning' },
    done: { text: '完成', type: 'success' },
    failed: { text: '失败', type: 'danger' },
  }
  return map[status] ?? { text: status, type: 'info' }
}
</script>

<template>
  <div class="app">
    <header class="topbar">
      <div class="brand">
        <span class="logo">ML</span>
        <div>
          <div class="title">MangaLens</div>
          <div class="subtitle">漫画 · 小说 识图翻译</div>
        </div>
      </div>
      <div class="tabs">
        <button :class="{ active: activeTab === 'manga' }" @click="activeTab = 'manga'">漫画板块</button>
        <button :class="{ active: activeTab === 'novel' }" @click="activeTab = 'novel'">小说板块</button>
      </div>
    </header>

    <main class="body">
      <!-- ==================== 漫画板块 ==================== -->
      <section v-if="activeTab === 'manga'" class="panel">
        <div class="block">
          <div class="block-title">批量上传漫画图片</div>
          <label class="uploader">
            <input type="file" accept="image/*" multiple hidden @change="onMangaFilesChange" />
            <div class="uploader-icon">+</div>
            <div class="uploader-text">点击选择图片（可多选）</div>
            <div class="uploader-hint">JPG / PNG / WebP，上传后自动识别+翻译</div>
          </label>
        </div>

        <div class="block grow" v-if="mangaTasks.length">
          <div class="block-title">
            任务列表 <span class="count">{{ mangaTasks.length }} 张</span>
          </div>
          <ul class="task-list">
            <li v-for="t in mangaTasks" :key="t.id" class="task-item">
              <div class="task-head">
                <span class="task-name">{{ t.filename }}</span>
                <el-tag size="small" :type="statusTag(t.status).type">{{ statusTag(t.status).text }}</el-tag>
              </div>
              <!-- 完成：显示翻译结果 —— v-for 嵌套，同款见 AIRoomBuilder App.vue 第166-186行 -->
              <div v-if="t.status === 'done' && t.result" class="task-result">
                <div v-for="(item, i) in t.result.texts" :key="i" class="text-pair">
                  <div class="text-original">{{ item.original }}</div>
                  <div class="text-translation">{{ item.translation }}</div>
                </div>
                <!-- 下载入口：<a> 标签 + download 属性，浏览器自己就完成下载，不用 axios -->
                <a class="download-btn" :href="`/api/images/${t.id}/download`" download>⬇ 下载译文 txt</a>
              </div>
              <!-- 失败：显示原因 -->
              <div v-if="t.status === 'failed'" class="task-error">❌ {{ t.error }}</div>
            </li>
          </ul>
        </div>

        <div class="block empty-tip" v-else>还没有任务，上传第一张漫画图开始吧</div>
      </section>

      <!-- ==================== 小说板块 ==================== -->
      <section v-if="activeTab === 'novel'" class="panel">
        <!-- 批次管理 -->
        <div class="block">
          <div class="block-title">小说批次（一个批次 = 一本书 → 一个txt）</div>
          <div class="batch-row">
            <input v-model="newBatchName" class="batch-input" placeholder="新批次名（比如书名）"
                   @keyup.enter="createNovelBatch" />
            <button class="btn" @click="createNovelBatch">新建批次</button>
          </div>
          <div class="batch-row" v-if="novelBatches.length">
            <select v-model="currentBatchId" class="batch-input" @change="refreshBatchImages">
              <option :value="null" disabled>选择批次</option>
              <option v-for="b in novelBatches" :key="b.id" :value="b.id">{{ b.name }}（ID {{ b.id }}）</option>
            </select>
            <button class="btn btn-danger" @click="deleteNovelBatch">删除当前批次</button>
            <a v-if="currentBatchId != null" class="btn btn-download"
               :href="`/api/batches/${currentBatchId}/download`" download>⬇ 下载整本txt</a>
          </div>
        </div>

        <!-- 上传书页 -->
        <div class="block" v-if="currentBatchId != null">
          <label class="uploader">
            <input type="file" accept="image/*" multiple hidden @change="onNovelFilesChange" />
            <div class="uploader-icon">+</div>
            <div class="uploader-text">上传书页图片（可多选，按选择顺序排页码）</div>
            <div class="uploader-hint">传完可用 ↑↓ 重新排序，全部完成后下载整本 txt</div>
          </label>
        </div>

        <!-- 书页列表 -->
        <div class="block grow" v-if="novelImages.length">
          <div class="block-title">
            书页列表 <span class="count">{{ novelImages.length }} 页</span>
          </div>
          <ul class="task-list">
            <li v-for="t in novelImages" :key="t.id" class="task-item">
              <div class="task-head">
                <span class="page-no">{{ t.order + 1 }}</span>
                <span class="task-name">{{ t.filename }}</span>
                <span class="task-actions">
                  <button class="icon-btn" @click="moveImageInBatch(t, 'up')">↑</button>
                  <button class="icon-btn" @click="moveImageInBatch(t, 'down')">↓</button>
                  <el-tag size="small" :type="statusTag(t.status).type">{{ statusTag(t.status).text }}</el-tag>
                </span>
              </div>
              <div v-if="t.status === 'failed'" class="task-error">❌ {{ t.error }}</div>
            </li>
          </ul>
        </div>

        <div class="block empty-tip" v-else>选一个批次开始传书页图吧</div>
      </section>
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
  background: linear-gradient(135deg, #e8792b, #c2410c); color: #fff;
  font-weight: 700; font-size: 13px;
}
.title { font-size: 15px; font-weight: 600; color: #1f2430; line-height: 1.2; }
.subtitle { font-size: 11px; color: #8a9099; }

.tabs { display: flex; gap: 8px; }
.tabs button {
  padding: 6px 14px; border: 1px solid #e5e7eb; border-radius: 6px;
  background: #fff; color: #4b5563; font-size: 13px; cursor: pointer;
}
.tabs button.active { background: #e8792b; border-color: #e8792b; color: #fff; }

.body { flex: 1; min-height: 0; overflow-y: auto; }
.panel { max-width: 860px; margin: 0 auto; padding: 20px 16px; }

.block {
  background: #fff; border: 1px solid #e1e4e8; border-radius: 10px;
  padding: 16px; margin-bottom: 16px;
}
.block.grow { min-height: 200px; }
.block-title {
  font-size: 13px; font-weight: 600; color: #4b5563; margin-bottom: 12px;
  display: flex; align-items: center; justify-content: space-between;
}
.count { font-weight: 400; color: #9aa0a8; font-size: 12px; }

.uploader {
  display: flex; flex-direction: column; align-items: center; gap: 4px;
  padding: 20px 12px; border: 1.5px dashed #d3d7de; border-radius: 8px;
  cursor: pointer; transition: all .15s; background: #fafbfc;
}
.uploader:hover { border-color: #e8792b; background: #fff8f2; }
.uploader-icon { font-size: 22px; color: #b0b6bf; line-height: 1; }
.uploader-text { font-size: 13px; color: #4b5563; }
.uploader-hint { font-size: 11px; color: #a8aeb6; }

.task-list { list-style: none; margin: 0; padding: 0; max-height: 520px; overflow-y: auto; }
.task-item {
  padding: 10px 12px; border-radius: 8px; border: 1px solid #eef0f3;
  margin-bottom: 8px;
}
.task-item:hover { background: #fafbfc; }
.task-head {
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
}
.task-name { font-size: 13px; color: #1f2430; font-weight: 500; flex: 1; }

.task-result { margin-top: 8px; display: flex; flex-direction: column; gap: 6px; }
.text-pair {
  padding: 8px 10px; border-radius: 6px; background: #f8f9fa;
}
.text-original { font-size: 12px; color: #6b7280; }
.text-translation { font-size: 13px; color: #1f2430; margin-top: 2px; }

.task-error { margin-top: 8px; font-size: 12px; color: #b42318; }

.empty-tip { text-align: center; color: #9aa0a8; font-size: 13px; padding: 40px 16px; }

/* ---- 小说批次区 ---- */
.batch-row { display: flex; gap: 8px; margin-bottom: 8px; align-items: center; }
.batch-input {
  flex: 1; padding: 6px 10px; border: 1px solid #d3d7de; border-radius: 6px;
  font-size: 13px; color: #1f2430;
}
.btn {
  padding: 6px 14px; border: 1px solid #d3d7de; border-radius: 6px;
  background: #fff; color: #4b5563; font-size: 13px; cursor: pointer;
}
.btn:hover { border-color: #e8792b; color: #e8792b; }
.btn-danger { color: #b42318; }
.btn-download {
  background: #e8792b; border-color: #e8792b; color: #fff;
  text-decoration: none; display: inline-block;
}
.btn-download:hover { color: #fff; background: #c2410c; }

.page-no {
  width: 24px; height: 24px; border-radius: 50%; background: #f0f2f5;
  color: #6b7280; font-size: 12px; display: grid; place-items: center; flex-shrink: 0;
}
.task-actions { display: flex; align-items: center; gap: 6px; }
.icon-btn {
  width: 24px; height: 24px; border: 1px solid #d3d7de; border-radius: 4px;
  background: #fff; color: #4b5563; cursor: pointer; font-size: 12px; line-height: 1;
}
.icon-btn:hover { border-color: #e8792b; color: #e8792b; }

.download-btn {
  display: inline-block; margin-top: 8px; padding: 5px 12px;
  background: #e8792b; color: #fff; border-radius: 6px;
  font-size: 12px; text-decoration: none;
}
</style>
