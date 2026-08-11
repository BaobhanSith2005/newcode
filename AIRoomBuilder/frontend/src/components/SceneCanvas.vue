<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { RoomRenderer } from '@/three/RoomRenderer'
import type { SceneJSON } from '@/types/scene'

const props = defineProps<{ scene: SceneJSON | null; selected: string | null }>()
const emit = defineEmits<{ (e: 'select', id: string | null): void }>()

const host = ref<HTMLDivElement>()
let renderer: RoomRenderer | null = null

onMounted(() => {
  if (!host.value) return
  renderer = new RoomRenderer(host.value)
  renderer.onSelect = (id) => emit('select', id)
  if (props.scene) void renderer.setScene(props.scene)
})

onBeforeUnmount(() => {
  renderer?.dispose()
  renderer = null
})

watch(() => props.scene, (s) => { if (s) void renderer?.setScene(s) })
watch(() => props.selected, (id) => renderer?.select(id))

defineExpose({
  setViewMode: (m: 'free' | 'top') => renderer?.setViewMode(m),
  screenshot: () => renderer?.screenshot() ?? ''
})
</script>

<template>
  <div ref="host" class="canvas-host">
    <div v-if="!scene" class="canvas-empty">
      <div class="empty-title">还没有场景</div>
      <div class="empty-sub">上传一张房间照片，或加载内置示例</div>
    </div>
  </div>
</template>

<style scoped>
.canvas-host {
  position: relative;
  width: 100%;
  height: 100%;
  background: #eef1f4;
  overflow: hidden;
}
.canvas-empty {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: #8a9099;
  pointer-events: none;
}
.empty-title { font-size: 16px; font-weight: 600; color: #6b7280; }
.empty-sub { font-size: 13px; }
</style>
