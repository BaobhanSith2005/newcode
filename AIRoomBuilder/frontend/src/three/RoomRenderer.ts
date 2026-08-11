/**
 * scene.json → Three.js 场景。
 *
 * 这是渲染侧唯一的入口，它**只消费 scene.json**，不关心 AI、不关心后端。
 * 这种隔离让你可以直接手写一份 scene.json 来调试渲染，无需跑通整条 AI 链路。
 */
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'

import type { Opening, SceneJSON, SceneObject } from '@/types/scene'
import { createProxy } from './primitives'

const LIGHT_PRESETS = {
  daylight: { sky: '#dfe8f2', sun: '#fff6e6', ambient: '#ffffff' },
  evening: { sky: '#2b3140', sun: '#ffc98a', ambient: '#8f9bb3' },
  neutral: { sky: '#eceef0', sun: '#ffffff', ambient: '#ffffff' }
} as const

interface WallRecord {
  mesh: THREE.Mesh
  center: THREE.Vector3
  normal: THREE.Vector3
}

export class RoomRenderer {
  private container: HTMLElement
  private renderer: THREE.WebGLRenderer
  private scene = new THREE.Scene()
  private camera: THREE.PerspectiveCamera
  private controls: OrbitControls
  private raycaster = new THREE.Raycaster()
  private pointer = new THREE.Vector2()

  private roomGroup = new THREE.Group()
  private objectGroup = new THREE.Group()
  private walls: WallRecord[] = []
  private loader = new GLTFLoader()
  private selectedWrapper: THREE.Object3D | null = null
  private highlightStore = new WeakMap<THREE.Material, { color: THREE.Color; intensity: number }>()
  private resizeObserver: ResizeObserver
  private rafId = 0
  private disposed = false

  onSelect: ((id: string | null) => void) | null = null

  constructor(container: HTMLElement) {
    this.container = container
    const w = container.clientWidth || 800
    const h = container.clientHeight || 600

    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false })
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    this.renderer.setSize(w, h)
    this.renderer.shadowMap.enabled = true
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap
    this.renderer.outputColorSpace = THREE.SRGBColorSpace
    container.appendChild(this.renderer.domElement)

    this.camera = new THREE.PerspectiveCamera(50, w / h, 0.05, 200)
    this.camera.position.set(5, 4.5, 6)

    this.controls = new OrbitControls(this.camera, this.renderer.domElement)
    this.controls.enableDamping = true
    this.controls.dampingFactor = 0.08
    this.controls.maxPolarAngle = Math.PI / 2 - 0.02   // 不允许钻到地板下面
    this.controls.minDistance = 1.5
    this.controls.maxDistance = 40

    this.scene.add(this.roomGroup, this.objectGroup)

    this.resizeObserver = new ResizeObserver(() => this.resize())
    this.resizeObserver.observe(container)
    this.renderer.domElement.addEventListener('click', this.handleClick)

    this.animate()
  }

  /* ------------------------------------------------------------- 生命周期 */

  private animate = () => {
    if (this.disposed) return
    this.rafId = requestAnimationFrame(this.animate)
    this.controls.update()
    this.updateWallVisibility()
    this.renderer.render(this.scene, this.camera)
  }

  private resize() {
    const w = this.container.clientWidth
    const h = this.container.clientHeight
    if (!w || !h) return
    this.camera.aspect = w / h
    this.camera.updateProjectionMatrix()
    this.renderer.setSize(w, h)
  }

  dispose() {
    this.disposed = true
    cancelAnimationFrame(this.rafId)
    this.resizeObserver.disconnect()
    this.renderer.domElement.removeEventListener('click', this.handleClick)
    this.clearGroup(this.roomGroup)
    this.clearGroup(this.objectGroup)
    this.controls.dispose()
    this.renderer.dispose()
    this.renderer.domElement.remove()
  }

  private clearGroup(group: THREE.Group) {
    group.traverse((o) => {
      const mesh = o as THREE.Mesh
      if (mesh.geometry) mesh.geometry.dispose()
      const m = mesh.material as THREE.Material | THREE.Material[] | undefined
      if (Array.isArray(m)) m.forEach((x) => x.dispose())
      else m?.dispose()
    })
    group.clear()
  }

  /* --------------------------------------------------------------- 主入口 */

  async setScene(data: SceneJSON) {
    this.clearGroup(this.roomGroup)
    this.clearGroup(this.objectGroup)
    this.walls = []
    this.selectedWrapper = null

    const preset = LIGHT_PRESETS[data.lighting?.preset ?? 'daylight']
    this.scene.background = new THREE.Color(preset.sky)
    this.buildLights(data, preset)
    this.buildShell(data)
    await this.buildObjects(data.objects ?? [])
    this.frameCamera(data)
  }

  private buildLights(data: SceneJSON, preset: (typeof LIGHT_PRESETS)[keyof typeof LIGHT_PRESETS]) {
    const { width: W, depth: D, height: H } = data.room
    const ambI = data.lighting?.ambient_intensity ?? 0.65
    const mainI = data.lighting?.main_intensity ?? 1.15

    const hemi = new THREE.HemisphereLight(preset.sky, '#8b8377', ambI * 1.4)
    const sun = new THREE.DirectionalLight(preset.sun, mainI)
    sun.position.set(W * 0.9, H * 2.4, D * 0.9)
    sun.castShadow = true
    sun.shadow.mapSize.set(2048, 2048)
    sun.shadow.camera.near = 0.5
    sun.shadow.camera.far = 60
    const span = Math.max(W, D) * 0.85
    Object.assign(sun.shadow.camera, { left: -span, right: span, top: span, bottom: -span })
    sun.shadow.camera.updateProjectionMatrix()
    sun.shadow.bias = -0.0008

    const fill = new THREE.DirectionalLight('#ffffff', mainI * 0.28)
    fill.position.set(-W, H * 1.6, -D)

    this.roomGroup.add(hemi, sun, fill)
  }

  /** 房间壳体：地板 + 四面带门窗洞的墙 + 踢脚线 */
  private buildShell(data: SceneJSON) {
    const { width: W, depth: D, height: H } = data.room
    const floorColor = data.room.floor?.color ?? '#c8a97e'
    const wallColor = data.room.wall?.color ?? '#f2efe9'

    const floor = new THREE.Mesh(
      new THREE.BoxGeometry(W, 0.06, D),
      new THREE.MeshStandardMaterial({ color: floorColor, roughness: 0.75 })
    )
    floor.position.y = -0.03
    floor.receiveShadow = true
    floor.userData.isFloor = true
    this.roomGroup.add(floor)

    const wallMat = new THREE.MeshStandardMaterial({
      color: wallColor, roughness: 0.95, side: THREE.DoubleSide
    })

    // 每面墙：起点、沿墙方向的绕 Y 旋转、朝向房间内侧的法线
    const defs = [
      { side: 'north', len: W, rotY: 0, pos: new THREE.Vector3(-W / 2, 0, -D / 2), n: new THREE.Vector3(0, 0, 1) },
      { side: 'south', len: W, rotY: 0, pos: new THREE.Vector3(-W / 2, 0, D / 2), n: new THREE.Vector3(0, 0, -1) },
      { side: 'west', len: D, rotY: -Math.PI / 2, pos: new THREE.Vector3(-W / 2, 0, -D / 2), n: new THREE.Vector3(1, 0, 0) },
      { side: 'east', len: D, rotY: -Math.PI / 2, pos: new THREE.Vector3(W / 2, 0, -D / 2), n: new THREE.Vector3(-1, 0, 0) }
    ] as const

    for (const def of defs) {
      const openings = (data.openings ?? []).filter((o) => o.wall === def.side)
      const shape = new THREE.Shape()
      shape.moveTo(0, 0)
      shape.lineTo(def.len, 0)
      shape.lineTo(def.len, H)
      shape.lineTo(0, H)
      shape.closePath()

      for (const op of openings) {
        const c = op.offset * def.len
        const half = Math.min(op.width, def.len * 0.9) / 2
        const y0 = op.sill
        const y1 = Math.min(op.sill + op.height, H - 0.05)
        const x0 = Math.max(0.05, c - half)
        const x1 = Math.min(def.len - 0.05, c + half)
        if (x1 <= x0 || y1 <= y0) continue
        const hole = new THREE.Path()
        hole.moveTo(x0, y0)
        hole.lineTo(x1, y0)
        hole.lineTo(x1, y1)
        hole.lineTo(x0, y1)
        hole.closePath()
        shape.holes.push(hole)
      }

      const mesh = new THREE.Mesh(new THREE.ShapeGeometry(shape), wallMat)
      mesh.rotation.y = def.rotY
      mesh.position.copy(def.pos)
      mesh.receiveShadow = true
      this.roomGroup.add(mesh)

      const center = def.pos.clone()
      center.y = H / 2
      center.addScaledVector(new THREE.Vector3(Math.cos(def.rotY), 0, -Math.sin(def.rotY)),
        def.len / 2)
      this.walls.push({ mesh, center, normal: def.n.clone() })

      openings.filter((o) => o.type === 'window').forEach((op) => this.addGlass(op, def, H))
    }
  }

  private addGlass(op: Opening, def: { len: number; rotY: number; pos: THREE.Vector3 }, H: number) {
    const w = Math.min(op.width, def.len * 0.9)
    const h = Math.min(op.height, H - op.sill - 0.05)
    if (w <= 0 || h <= 0) return
    const glass = new THREE.Mesh(
      new THREE.PlaneGeometry(w, h),
      new THREE.MeshStandardMaterial({
        color: '#cfe4f5', transparent: true, opacity: 0.34,
        roughness: 0.05, metalness: 0.1, side: THREE.DoubleSide
      })
    )
    const along = new THREE.Vector3(Math.cos(def.rotY), 0, -Math.sin(def.rotY))
    glass.position.copy(def.pos).addScaledVector(along, op.offset * def.len)
    glass.position.y = op.sill + h / 2
    glass.rotation.y = def.rotY
    this.roomGroup.add(glass)
  }

  /** 近处的墙会挡住视线，按相机位置动态隐藏 */
  private updateWallVisibility() {
    for (const w of this.walls) {
      const toCam = this.camera.position.clone().sub(w.center)
      w.mesh.visible = toCam.dot(w.normal) > 0
    }
  }

  /* --------------------------------------------------------------- 家具 */

  private async buildObjects(objects: SceneObject[]) {
    await Promise.all(objects.map((o) => this.addObject(o)))
  }

  private async addObject(obj: SceneObject) {
    const { w, d, h } = obj.size
    const color = obj.material?.color ?? obj.color ?? '#b0b0b0'
    let node: THREE.Object3D | null = null

    // 绿植：内置程序化盆栽比 .glb 更可控好看，且保留自身固有色（不被 OpenCV 误染）
    if (!(obj.category === 'plant') && obj.asset?.kind === 'gltf' && obj.asset.url) {
      try {
        const gltf = await this.loader.loadAsync(obj.asset.url)
        node = this.normalizeGltf(gltf.scene, w, d, h)
        this.applyColor(node, color)
      } catch {
        node = null   // 静默降级：模型缺失是常态，不该让整个场景挂掉
      }
    }
    if (!node) {
      node = createProxy(obj.asset?.fallback ?? 'box', { w, d, h, color })
    }

    const wrapper = new THREE.Group()
    wrapper.add(node)
    wrapper.position.set(obj.position[0], obj.position[1], obj.position[2])
    wrapper.rotation.y = THREE.MathUtils.degToRad(obj.rotation_y ?? 0)
    wrapper.userData.objectId = obj.id
    wrapper.userData.label = obj.label ?? obj.category
    wrapper.traverse((n) => {
      const m = n as THREE.Mesh
      if (m.isMesh) {
        m.castShadow = true
        m.receiveShadow = true
        m.userData.objectId = obj.id
      }
    })
    this.objectGroup.add(wrapper)
  }

  /** 把 glb 的材质颜色统一设置为 scene.json 指定的颜色。 */
  private applyColor(root: THREE.Object3D, color: string) {
    const c = new THREE.Color(color)
    root.traverse((n) => {
      const mesh = n as THREE.Mesh
      if (mesh.isMesh) {
        const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material]
        materials.forEach((m: THREE.Material) => {
          if ('color' in m && (m as THREE.MeshStandardMaterial).color) {
            ;(m as THREE.MeshStandardMaterial).color.set(c)
          }
        })
      }
    })
  }

  /** 把任意来源的 glb 归一化到 scene.json 声明的尺寸，原点对齐底面中心 */
  private normalizeGltf(root: THREE.Object3D, w: number, d: number, h: number) {
    const box = new THREE.Box3().setFromObject(root)
    const size = box.getSize(new THREE.Vector3())
    if (size.x < 1e-6 || size.y < 1e-6 || size.z < 1e-6) return root

    const scale = Math.min(w / size.x, h / size.y, d / size.z)
    root.scale.setScalar(scale)

    const scaled = new THREE.Box3().setFromObject(root)
    const center = scaled.getCenter(new THREE.Vector3())
    root.position.x -= center.x
    root.position.z -= center.z
    root.position.y -= scaled.min.y
    return root
  }

  /* --------------------------------------------------------------- 交互 */

  private handleClick = (ev: MouseEvent) => {
    const rect = this.renderer.domElement.getBoundingClientRect()
    this.pointer.x = ((ev.clientX - rect.left) / rect.width) * 2 - 1
    this.pointer.y = -((ev.clientY - rect.top) / rect.height) * 2 + 1
    this.raycaster.setFromCamera(this.pointer, this.camera)
    const hits = this.raycaster.intersectObjects(this.objectGroup.children, true)
    const id = (hits[0]?.object.userData.objectId as string | undefined) ?? null
    this.select(id)
    this.onSelect?.(id)
  }

  select(id: string | null) {
    // 还原上一个选中物体的高亮
    if (this.selectedWrapper) {
      this.clearHighlight(this.selectedWrapper)
      this.selectedWrapper = null
    }
    if (!id) return
    const target = this.objectGroup.children.find((c) => c.userData.objectId === id)
    if (!target) return
    this.applyHighlight(target)
    this.selectedWrapper = target
  }

  /** 给选中物体叠加一层柔和的发光高亮（emissive），比硬线框更克制。 */
  private applyHighlight(node: THREE.Object3D) {
    node.traverse((n) => {
      const mesh = n as THREE.Mesh
      if (!mesh.isMesh) return
      const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material]
      materials.forEach((m) => {
        const sm = m as THREE.MeshStandardMaterial
        if (!('emissive' in sm) || !sm.emissive) return
        if (!this.highlightStore.has(sm)) {
          this.highlightStore.set(sm, {
            color: sm.emissive.clone(),
            intensity: sm.emissiveIntensity
          })
        }
        sm.emissive.set('#2f6feb')
        sm.emissiveIntensity = 0.35
      })
    })
  }

  /** 还原上一次高亮时保存的原始 emissive，避免污染其它物体。 */
  private clearHighlight(node: THREE.Object3D) {
    node.traverse((n) => {
      const mesh = n as THREE.Mesh
      if (!mesh.isMesh) return
      const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material]
      materials.forEach((m) => {
        const sm = m as THREE.MeshStandardMaterial
        const saved = this.highlightStore.get(sm)
        if (saved && 'emissive' in sm && sm.emissive) {
          sm.emissive.copy(saved.color)
          sm.emissiveIntensity = saved.intensity
          this.highlightStore.delete(sm)
        }
      })
    })
  }

  /** 相机自动取景，保证整个房间入画 */
  private frameCamera(data: SceneJSON) {
    const { width: W, depth: D, height: H } = data.room
    const radius = Math.sqrt(W * W + D * D) / 2
    const dist = radius / Math.tan(THREE.MathUtils.degToRad(this.camera.fov / 2)) * 1.15
    this.camera.position.set(W * 0.55, Math.max(H * 1.25, 3.2), D * 0.55 + dist * 0.55)
    this.controls.target.set(0, H * 0.35, 0)
    this.controls.update()
  }

  setViewMode(mode: 'free' | 'top') {
    const box = new THREE.Box3().setFromObject(this.roomGroup)
    const size = box.getSize(new THREE.Vector3())
    if (mode === 'top') {
      this.camera.position.set(0, Math.max(size.x, size.z) * 1.5, 0.001)
      this.controls.target.set(0, 0, 0)
    } else {
      this.camera.position.set(size.x * 0.6, Math.max(size.y * 1.3, 3.2), size.z * 1.1)
      this.controls.target.set(0, size.y * 0.35, 0)
    }
    this.controls.update()
  }

  screenshot(): string {
    this.renderer.render(this.scene, this.camera)
    return this.renderer.domElement.toDataURL('image/png')
  }
}
