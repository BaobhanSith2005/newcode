import type { SceneJSON } from '@/types/scene'

/**
 * 内置示例场景。作用：**让渲染端可以脱离后端独立开发调试**。
 * 手写一份 scene.json 就能验证渲染效果，不必每次都跑完整条 AI 链路。
 */
export const demoScene: SceneJSON = {
  schema_version: '1.0',
  scene_id: 'sc_demo',
  room: {
    type: 'living_room',
    width: 5,
    depth: 4,
    height: 2.8,
    floor: { material: 'wood', color: '#c8a97e' },
    wall: { material: 'paint', color: '#f2efe9' }
  },
  openings: [
    { id: 'op_1', type: 'window', wall: 'west', offset: 0.45, width: 2, height: 1.4, sill: 0.9 },
    { id: 'op_2', type: 'door', wall: 'south', offset: 0.85, width: 1, height: 2.05, sill: 0 }
  ],
  objects: [
    {
      id: 'obj_1', category: 'sofa', label: '三人布艺沙发',
      asset: { kind: 'primitive', url: null, fallback: 'sofa' },
      size: { w: 2.6, d: 0.95, h: 0.82 },
      position: [-0.9, 0, -1.53], rotation_y: 0, against_wall: 'north',
      material: { color: '#8d9aaf', name: '灰色' }, confidence: 0.93, source: 'vlm'
    },
    {
      id: 'obj_2', category: 'rug', label: '米色地毯',
      asset: { kind: 'primitive', url: null, fallback: 'plane' },
      size: { w: 2.5, d: 1.75, h: 0.02 },
      position: [-0.8, 0, -0.2], rotation_y: 0, against_wall: null,
      material: { color: '#c9bda6', name: '米色' }, confidence: 0.7, source: 'vlm'
    },
    {
      id: 'obj_3', category: 'coffee_table', label: '木质茶几',
      asset: { kind: 'primitive', url: null, fallback: 'table' },
      size: { w: 1.1, d: 0.6, h: 0.42 },
      position: [-0.9, 0, -0.3], rotation_y: 180, against_wall: null,
      material: { color: '#a9855f', name: '棕色' }, confidence: 0.88, source: 'solver'
    },
    {
      id: 'obj_4', category: 'tv_stand', label: '电视柜',
      asset: { kind: 'primitive', url: null, fallback: 'box' },
      size: { w: 1.6, d: 0.4, h: 0.5 },
      position: [-0.9, 0, 1.8], rotation_y: 180, against_wall: 'south',
      material: { color: '#6f665c', name: '灰色' }, confidence: 0.85, source: 'vlm'
    },
    {
      id: 'obj_5', category: 'tv', label: '壁挂电视',
      asset: { kind: 'primitive', url: null, fallback: 'screen' },
      size: { w: 1.2, d: 0.08, h: 0.7 },
      position: [-0.9, 0.95, 1.96], rotation_y: 180, against_wall: 'south',
      material: { color: '#26282b', name: '黑色' }, confidence: 0.9, source: 'vlm'
    },
    {
      id: 'obj_6', category: 'bookshelf', label: '开放书架',
      asset: { kind: 'primitive', url: null, fallback: 'box' },
      size: { w: 0.9, d: 0.32, h: 1.8 },
      position: [2.34, 0, -0.6], rotation_y: 270, against_wall: 'east',
      material: { color: '#8a7355', name: '棕色' }, confidence: 0.76, source: 'vlm'
    },
    {
      id: 'obj_7', category: 'plant', label: '散尾葵',
      asset: { kind: 'primitive', url: null, fallback: 'plant' },
      size: { w: 0.5, d: 0.5, h: 1.2 },
      position: [1.9, 0, -1.6], rotation_y: 0, against_wall: null,
      material: { color: '#5c7f52', name: '绿色' }, confidence: 0.8, source: 'vlm'
    },
    {
      id: 'obj_8', category: 'floor_lamp', label: '落地灯',
      asset: { kind: 'primitive', url: null, fallback: 'lamp' },
      size: { w: 0.35, d: 0.35, h: 1.6 },
      position: [-2.2, 0, 0.9], rotation_y: 90, against_wall: null,
      material: { color: '#d8cfa8', name: '米色' }, confidence: 0.72, source: 'vlm'
    },
    {
      id: 'obj_9', category: 'armchair', label: '单人沙发',
      asset: { kind: 'primitive', url: null, fallback: 'sofa' },
      size: { w: 0.85, d: 0.85, h: 0.9 },
      position: [1.0, 0, -0.3], rotation_y: 270, against_wall: null,
      material: { color: '#9aa79b', name: '绿色' }, confidence: 0.78, source: 'vlm'
    }
  ],
  lighting: { preset: 'daylight', ambient_intensity: 0.65, main_intensity: 1.15 },
  meta: { notes: '内置示例：现代风格客厅' }
}
