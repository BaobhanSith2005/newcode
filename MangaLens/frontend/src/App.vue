<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { api, waitForDocResult, waitForResult, type Batch, type DocTask, type ImageTask } from '@/api'

// ----------------------------------------------------------------
// 板块切换 —— 同款见 AIRoomBuilder App.vue 第12行 viewMode
// ----------------------------------------------------------------
type TabKey = 'manga' | 'novel'
const activeTab = ref<TabKey>('manga')

// ----------------------------------------------------------------
// 漫画板块：批次管理（一个批次 = 一部漫画，复用小说批次的 UI 套路）
// ----------------------------------------------------------------
const currentMangaBatchId = ref<number | null>(null)
const mangaImages = ref<ImageTask[]>([])
const newMangaBatchName = ref('')

async function createMangaBatch() {
  const name = newMangaBatchName.value.trim()
  if (!name) return alert('先填批次名（比如漫画名）')
  const batch = await api.createBatch(name, 'manga')
  newMangaBatchName.value = ''
  await loadBatches()
  currentMangaBatchId.value = batch.id
  await refreshMangaBatchImages()
}

async function deleteMangaBatch() {
  if (currentMangaBatchId.value == null) return
  if (!confirm('删除这个批次和它下面所有图片记录？')) return
  await api.deleteBatch(currentMangaBatchId.value)
  currentMangaBatchId.value = null
  mangaImages.value = []
  await loadBatches()
}

// ----------------------------------------------------------------
// 漫画板块：传图 + 调序（跟小说书页同一个套路）
// ----------------------------------------------------------------
async function refreshMangaBatchImages() {
  if (currentMangaBatchId.value == null) return
  mangaImages.value = await api.listBatchImages(currentMangaBatchId.value)
}

async function onMangaFilesChange(ev: Event) {
  const input = ev.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  if (!files.length) return
  input.value = ''
  if (currentMangaBatchId.value == null) {
    alert('请先新建或选择一个漫画批次')
    return
  }
  const batchId = currentMangaBatchId.value

  // 逐个上传：order = 批次里现有张数 + 序号（继续往后排页码）；
  // 上传后后台自动嵌字，前台开后台轮询不阻塞下一张
  const startOrder = mangaImages.value.length
  for (let i = 0; i < files.length; i++) {
    try {
      const task = await api.uploadImage(files[i], { batchId, order: startOrder + i })
      await refreshMangaBatchImages()     // 传一张，列表里就多一张
      void pollMangaUntilDone(task.id)    // 后台轮询这张，不阻塞下一张上传
    } catch (e) {
      alert(`${files[i].name} 上传失败：${e instanceof Error ? e.message : e}`)
    }
  }
}

// 后台轮询单张，完成后刷新列表 + 弹桌面通知
async function pollMangaUntilDone(imageId: number) {
  const done = await waitForResult(imageId, (tick) => {
    const img = mangaImages.value.find((t) => t.id === imageId)
    if (img) {
      img.status = tick.status
      img.progress = tick.progress
    }
  })
  await refreshMangaBatchImages()
  if (done.status === 'done') notifyDone(done.filename)
}

async function moveMangaImage(img: ImageTask, direction: 'up' | 'down') {
  if (currentMangaBatchId.value == null) return
  try {
    // 后端换完号会返回新的完整顺序，直接替换整个列表
    mangaImages.value = await api.moveImage(currentMangaBatchId.value, img.id, direction)
  } catch (e) {
    alert(e instanceof Error ? e.message : '移动失败')
  }
}

// 失败重试：重新跑嵌字（POST /render），不用重传图。
// 后端会 409 拦住 running 中的重复点击
async function retryRender(t: ImageTask) {
  try {
    await api.renderImage(t.id)
    await pollMangaUntilDone(t.id)
  } catch (e) {
    alert(e instanceof Error ? e.message : '重试失败')
  }
}

// 浏览器桌面通知：翻译好了弹一下，切到别的窗口也能知道。
// 权限在 onMounted 里提前要（第一次会弹授权框）；被拒绝就静默跳过
function notifyDone(filename: string) {
  if (!('Notification' in window) || Notification.permission !== 'granted') return
  new Notification('MangaLens 翻译完成', { body: filename })
}

// ----------------------------------------------------------------
// 批次总台账：一张 batches 表装两个板块（Batch.kind 区分），
// novelBatches / mangaBatches 是从全量列表里按 kind 筛出来的两个视图
// ----------------------------------------------------------------
const batches = ref<Batch[]>([])
const novelBatches = computed(() => batches.value.filter((b) => b.kind === 'novel'))
const mangaBatches = computed(() => batches.value.filter((b) => b.kind === 'manga'))

// ----------------------------------------------------------------
// 小说板块：批次管理
// ----------------------------------------------------------------
const currentBatchId = ref<number | null>(null)
const novelImages = ref<ImageTask[]>([])
const newBatchName = ref('')

onMounted(() => {
  void loadBatches()
  // 提前要桌面通知权限：第一次打开页面弹授权框，授权过后完成时才弹得出来
  if ('Notification' in window && Notification.permission === 'default') {
    void Notification.requestPermission()
  }
})

async function loadBatches() {
  batches.value = await api.listBatches()
}

async function createNovelBatch() {
  const name = newBatchName.value.trim()
  if (!name) return alert('先填批次名（比如书名）')
  const batch = await api.createBatch(name, 'novel')
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
  await waitForResult(imageId, (tick) => {
    const img = novelImages.value.find((t) => t.id === imageId)
    if (img) {
      img.status = tick.status
      img.progress = tick.progress
    }
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

// ----------------------------------------------------------------
// 小说板块：txt / epub 整本翻译
// ----------------------------------------------------------------
const novelDocs = ref<DocTask[]>([])
let docTempId = -1  // 占位任务用的临时负数ID，跟漫画占位一个套路

async function onNovelDocChange(ev: Event) {
  const input = ev.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  if (!files.length) return
  input.value = ''

  // 跟漫画上传同一个套路：占位 → 上传 → 轮询 → 替换
  for (const f of files) {
    const placeholder: DocTask = {
      id: docTempId--,
      filename: f.name,
      file_type: 'txt',
      status: 'pending',
      style: '文学风',
      created_at: new Date().toISOString(),
    }
    novelDocs.value.push(placeholder)
    let current: DocTask = placeholder
    try {
      const task = await api.uploadDoc(f)
      replaceDoc(current, task)
      current = task
      // 整本小说逐块翻译慢，耐心等（前端最长等10分钟）
      const done = await waitForDocResult(task.id, (status) => {
        const d = novelDocs.value.find((x) => x.id === current.id)
        if (d) d.status = status as DocTask['status']
      })
      replaceDoc(current, done)
    } catch (e) {
      replaceDoc(current, {
        ...current,
        status: 'failed',
        error: e instanceof Error ? e.message : String(e),
      })
    }
  }
}

function replaceDoc(oldDoc: DocTask, newDoc: DocTask) {
  const idx = novelDocs.value.findIndex((d) => d.id === oldDoc.id)
  if (idx !== -1) novelDocs.value[idx] = newDoc
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
        <!-- 批次管理（跟小说板块同款结构） -->
        <div class="block">
          <div class="block-title">漫画批次（一个批次 = 一部漫画，可调序后整批下载成品图）</div>
          <div class="batch-row">
            <input v-model="newMangaBatchName" class="batch-input" placeholder="新批次名（比如漫画名）"
                   @keyup.enter="createMangaBatch" />
            <button class="btn" @click="createMangaBatch">新建批次</button>
          </div>
          <div class="batch-row" v-if="mangaBatches.length">
            <select v-model="currentMangaBatchId" class="batch-input" @change="refreshMangaBatchImages">
              <option :value="null" disabled>选择批次</option>
              <option v-for="b in mangaBatches" :key="b.id" :value="b.id">{{ b.name }}（ID {{ b.id }}）</option>
            </select>
            <button class="btn btn-danger" @click="deleteMangaBatch">删除当前批次</button>
            <a v-if="currentMangaBatchId != null" class="btn btn-download"
               :href="`/api/batches/${currentMangaBatchId}/download`" download>⬇ 下载整批成品(zip)</a>
          </div>
        </div>

        <!-- 上传漫画图 -->
        <div class="block" v-if="currentMangaBatchId != null">
          <label class="uploader">
            <input type="file" accept="image/*" multiple hidden @change="onMangaFilesChange" />
            <div class="uploader-icon">+</div>
            <div class="uploader-text">上传漫画图片（可多选，按选择顺序排页码）</div>
            <div class="uploader-hint">传完自动嵌字；可用 ↑↓ 重新排序，全部完成后下载整批成品</div>
          </label>
        </div>

        <!-- 图片列表（跟书页列表同款结构，多成品图 + 重试） -->
        <div class="block grow" v-if="mangaImages.length">
          <div class="block-title">
            图片列表 <span class="count">{{ mangaImages.length }} 张</span>
          </div>
          <ul class="task-list">
            <li v-for="t in mangaImages" :key="t.id" class="task-item">
              <div class="task-head">
                <span class="page-no">{{ t.order + 1 }}</span>
                <span class="task-name">{{ t.filename }}</span>
                <span class="task-actions">
                  <button class="icon-btn" @click="moveMangaImage(t, 'up')">↑</button>
                  <button class="icon-btn" @click="moveMangaImage(t, 'down')">↓</button>
                  <el-tag size="small" :type="statusTag(t.status).type">{{ statusTag(t.status).text }}</el-tag>
                </span>
              </div>
              <!-- 进度文字：后端 progress 字段，跑着时实时刷新（"② 云端翻译中（已过 X 秒）…"），
                   完成后带漏译上报（"完成（3 条未认领只擦不画：…）"），失败看下面原因区 -->
              <div v-if="t.progress && t.status !== 'failed'" class="task-progress">{{ t.progress }}</div>
              <!-- 完成：显示嵌字成品图 —— 漫画图没有 result（直接嵌字，result 是 null），
                   成品图走 /render/download 接口；<img> 把接口地址直接当图片源 -->
              <div v-if="t.status === 'done'" class="task-result">
                <img class="result-img" :src="`/api/images/${t.id}/render/download`" :alt="t.filename" />
                <a class="download-btn" :href="`/api/images/${t.id}/render/download`" download>⬇ 下载成品图</a>
              </div>
              <!-- 失败：显示原因 + 重试按钮（重新跑嵌字，不用重传图） -->
              <div v-if="t.status === 'failed'" class="task-error">
                ❌ {{ t.error }}
                <button class="btn btn-retry" @click="retryRender(t)">↻ 重试</button>
              </div>
            </li>
          </ul>
        </div>

        <div class="block empty-tip" v-else>新建或选择一个批次，开始传漫画图吧</div>
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

        <!-- txt / epub 整本翻译 -->
        <div class="block">
          <label class="uploader">
            <input type="file" accept=".txt,.epub" multiple hidden @change="onNovelDocChange" />
            <div class="uploader-icon">+</div>
            <div class="uploader-text">上传小说 txt / epub（整本翻译，文学风）</div>
            <div class="uploader-hint">txt 按段落切块；epub 保结构翻译（插图标签原样保留）</div>
          </label>
        </div>

        <div class="block grow" v-if="novelDocs.length">
          <div class="block-title">
            txt / epub 翻译任务 <span class="count">{{ novelDocs.length }} 本</span>
          </div>
          <ul class="task-list">
            <li v-for="t in novelDocs" :key="t.id" class="task-item">
              <div class="task-head">
                <span class="task-name">{{ t.filename }}</span>
                <span class="task-actions">
                  <a v-if="t.status === 'done'" class="download-btn"
                     :href="`/api/docs/${t.id}/download`" download>⬇ 下载译文</a>
                  <el-tag size="small" :type="statusTag(t.status).type">{{ statusTag(t.status).text }}</el-tag>
                </span>
              </div>
              <div v-if="t.status === 'failed'" class="task-error">❌ {{ t.error }}</div>
            </li>
          </ul>
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
              <div v-if="t.progress && t.status === 'running'" class="task-progress">{{ t.progress }}</div>
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
.task-progress { margin-top: 6px; font-size: 12px; color: #8a5a00; }
.result-img {
  margin-top: 8px; max-width: 100%; border-radius: 6px;
  border: 1px solid #eef0f3; display: block;
}
.btn-retry { margin-top: 6px; }

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
