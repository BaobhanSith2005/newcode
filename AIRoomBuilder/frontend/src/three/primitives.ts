/**
 * 参数化替身几何体。
 *
 * 存在意义：模型库永远不可能覆盖所有品类，而「场景里一半物体不显示」是 Demo 的致命伤。
 * 这里按真实尺寸生成有基本造型的替身（不是灰盒子），保证任何分析结果都能出图。
 *
 * 所有构造函数返回的 Group 满足：
 *   - 原点位于**底面中心**
 *   - 整体包围盒恰好为 w(X) × h(Y) × d(Z)
 *   - 正面朝向 +Z
 */
import * as THREE from 'three'

export interface ProxyParams {
  w: number
  d: number
  h: number
  color: string
}

function mat(color: string, rough = 0.85): THREE.MeshStandardMaterial {
  return new THREE.MeshStandardMaterial({ color, roughness: rough, metalness: 0.02 })
}

function box(w: number, h: number, d: number, m: THREE.Material, x = 0, y = 0, z = 0) {
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), m)
  mesh.position.set(x, y, z)
  mesh.castShadow = true
  mesh.receiveShadow = true
  return mesh
}

function shade(color: string, amount: number): string {
  const c = new THREE.Color(color)
  c.offsetHSL(0, 0, amount)
  return `#${c.getHexString()}`
}

/* --------------------------------------------------------------- 各品类替身 */

function buildBox({ w, d, h, color }: ProxyParams) {
  const g = new THREE.Group()
  g.add(box(w, h, d, mat(color), 0, h / 2, 0))
  return g
}

function buildSofa({ w, d, h, color }: ProxyParams) {
  const g = new THREE.Group()
  const m = mat(color)
  const mDark = mat(shade(color, -0.06))
  const armW = Math.min(0.18, w * 0.12)
  const backD = Math.min(0.18, d * 0.22)
  const seatH = h * 0.45

  g.add(box(w, seatH, d, mDark, 0, seatH / 2, 0))                                  // 座体
  g.add(box(w, h - seatH, backD, m, 0, seatH + (h - seatH) / 2, -d / 2 + backD / 2)) // 靠背
  g.add(box(armW, h * 0.72, d - backD, m, -w / 2 + armW / 2, h * 0.36, backD / 2))   // 左扶手
  g.add(box(armW, h * 0.72, d - backD, m, w / 2 - armW / 2, h * 0.36, backD / 2))    // 右扶手
  // 坐垫
  const cushionW = (w - armW * 2) / 2 - 0.03
  for (const sx of [-1, 1]) {
    g.add(box(cushionW, 0.1, d - backD - 0.08, mat(shade(color, 0.07)),
      sx * (cushionW / 2 + 0.02), seatH + 0.05, backD / 2))
  }
  return g
}

function buildBed({ w, d, h, color }: ProxyParams) {
  const g = new THREE.Group()
  const frameH = h * 0.4
  g.add(box(w, frameH, d, mat(shade(color, -0.12)), 0, frameH / 2, 0))            // 床架
  g.add(box(w - 0.06, h - frameH, d - 0.06, mat(shade(color, 0.1)),
    0, frameH + (h - frameH) / 2, 0))                                              // 床垫
  g.add(box(w, h * 1.2, 0.08, mat(shade(color, -0.18)), 0, h * 0.6, -d / 2 + 0.04)) // 床头板
  const pw = Math.min(0.55, w / 2 - 0.1)
  for (const sx of [-1, 1]) {
    g.add(box(pw, 0.12, 0.35, mat('#ffffff'), sx * (pw / 2 + 0.04), h + 0.02, -d / 2 + 0.32))
  }
  return g
}

function buildTable({ w, d, h, color }: ProxyParams) {
  const g = new THREE.Group()
  const topH = 0.05
  const leg = Math.min(0.07, w * 0.08)
  g.add(box(w, topH, d, mat(color), 0, h - topH / 2, 0))
  const mLeg = mat(shade(color, -0.15))
  for (const sx of [-1, 1]) {
    for (const sz of [-1, 1]) {
      g.add(box(leg, h - topH, leg, mLeg,
        sx * (w / 2 - leg / 2 - 0.03), (h - topH) / 2, sz * (d / 2 - leg / 2 - 0.03)))
    }
  }
  return g
}

function buildChair({ w, d, h, color }: ProxyParams) {
  const g = new THREE.Group()
  const seatH = h * 0.45
  const leg = 0.045
  g.add(box(w, 0.06, d, mat(color), 0, seatH, 0))
  g.add(box(w, h - seatH, 0.06, mat(color), 0, seatH + (h - seatH) / 2, -d / 2 + 0.03))
  const mLeg = mat(shade(color, -0.2))
  for (const sx of [-1, 1]) {
    for (const sz of [-1, 1]) {
      g.add(box(leg, seatH, leg, mLeg,
        sx * (w / 2 - leg), seatH / 2, sz * (d / 2 - leg)))
    }
  }
  return g
}

function buildPlane({ w, d, h, color }: ProxyParams) {
  const g = new THREE.Group()
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(w, Math.max(h, 0.012), d),
    new THREE.MeshStandardMaterial({ color, roughness: 0.95 }))
  mesh.position.y = Math.max(h, 0.012) / 2
  mesh.receiveShadow = true
  g.add(mesh)
  return g
}

function leafGeometry(len: number, wid: number): THREE.ExtrudeGeometry {
  const s = new THREE.Shape()
  s.moveTo(0, 0)
  s.bezierCurveTo(wid, len * 0.32, wid * 0.55, len * 0.82, 0, len)
  s.bezierCurveTo(-wid * 0.55, len * 0.82, -wid, len * 0.32, 0, 0)
  const geo = new THREE.ExtrudeGeometry(s, { depth: 0.014, bevelEnabled: false, curveSegments: 10 })
  geo.translate(0, 0, -0.007)   // 居中厚度，叶尖朝 +Y
  return geo
}

function buildPlant({ w, d, h }: ProxyParams) {
  const g = new THREE.Group()
  const r = Math.min(w, d) / 2
  const potH = h * 0.3

  // 花盆：LatheGeometry 陶盆轮廓（上宽下窄、盆口微外翻）
  const profile: [number, number][] = [
    [0.0, 0.0], [0.62, 0.0], [0.6, potH * 0.22],
    [0.72, potH * 0.88], [0.8, potH], [0.74, potH + 0.02]
  ]
  const pts = profile.map(([x, y]) => new THREE.Vector2(x * r, y))
  const pot = new THREE.Mesh(new THREE.LatheGeometry(pts, 28), mat('#b06a3c', 0.92))
  pot.castShadow = true
  pot.receiveShadow = true
  g.add(pot)

  // 土面
  const soil = new THREE.Mesh(
    new THREE.CylinderGeometry(r * 0.7, r * 0.7, 0.02, 24), mat('#3b2a1d', 1))
  soil.position.y = potH - 0.004
  g.add(soil)

  // 主茎：略弯，从盆口向上
  const trunkH = h - potH
  const curve = new THREE.CatmullRomCurve3([
    new THREE.Vector3(0, potH, 0),
    new THREE.Vector3(0, potH + trunkH * 0.4, 0),
    new THREE.Vector3(r * 0.05, potH + trunkH * 0.74, 0),
    new THREE.Vector3(r * 0.1, potH + trunkH, 0)
  ])
  const trunk = new THREE.Mesh(
    new THREE.TubeGeometry(curve, 14, r * 0.055, 8, false), mat('#6b8e3f', 0.85))
  trunk.castShadow = true
  g.add(trunk)

  // 叶片：沿茎上部确定性螺旋分布
  const leafColors = ['#3f7d3a', '#4f9d4a', '#357032', '#5aa84f']
  const leafDefs = [
    { at: 0.6, ang: 0.0, tilt: 0.5, len: 0.95 },
    { at: 0.72, ang: 2.2, tilt: 0.42, len: 0.82 },
    { at: 0.85, ang: 4.3, tilt: 0.55, len: 0.88 },
    { at: 0.97, ang: 1.1, tilt: 0.34, len: 0.7 }
  ]
  leafDefs.forEach((lf, i) => {
    const p = curve.getPoint(lf.at)
    const lg = leafGeometry(Math.max(h * 0.5 * lf.len, r * 1.25), r * 0.55 * lf.len)
    const leaf = new THREE.Mesh(lg, new THREE.MeshStandardMaterial({
      color: leafColors[i], roughness: 0.7, side: THREE.DoubleSide
    }))
    leaf.position.copy(p)
    leaf.rotation.order = 'YXZ'
    leaf.rotation.y = lf.ang
    leaf.rotation.x = lf.tilt        // 向外下方散开
    leaf.castShadow = true
    g.add(leaf)
  })
  return g
}

function buildLamp({ w, d, h, color }: ProxyParams) {
  const g = new THREE.Group()
  const r = Math.min(w, d) / 2
  const base = new THREE.Mesh(new THREE.CylinderGeometry(r * 0.75, r * 0.85, 0.04, 16),
    mat('#3e3e42'))
  base.position.y = 0.02
  g.add(base)
  const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.018, 0.018, h * 0.78, 10),
    mat('#5a5a5f'))
  pole.position.y = h * 0.39
  g.add(pole)
  const sh = new THREE.Mesh(new THREE.CylinderGeometry(r * 0.95, r * 0.72, h * 0.2, 18, 1, true),
    new THREE.MeshStandardMaterial({ color, roughness: 0.6, side: THREE.DoubleSide,
      emissive: new THREE.Color(color), emissiveIntensity: 0.35 }))
  sh.position.y = h * 0.88
  g.add(sh)
  return g
}

function buildScreen({ w, d, h, color }: ProxyParams) {
  const g = new THREE.Group()
  g.add(box(w, h, Math.max(d, 0.05), mat('#1b1d20', 0.4), 0, h / 2, 0))
  const panel = new THREE.Mesh(
    new THREE.PlaneGeometry(w * 0.94, h * 0.9),
    new THREE.MeshStandardMaterial({ color: '#2b3440', roughness: 0.25,
      emissive: new THREE.Color('#16202c'), emissiveIntensity: 0.5 }))
  panel.position.set(0, h / 2, Math.max(d, 0.05) / 2 + 0.002)
  g.add(panel)
  return g
}

const BUILDERS: Record<string, (p: ProxyParams) => THREE.Group> = {
  box: buildBox,
  sofa: buildSofa,
  bed: buildBed,
  table: buildTable,
  chair: buildChair,
  plane: buildPlane,
  plant: buildPlant,
  lamp: buildLamp,
  screen: buildScreen
}

export function createProxy(kind: string, params: ProxyParams): THREE.Group {
  return (BUILDERS[kind] ?? buildBox)(params)
}
