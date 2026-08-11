/** 与 docs/scene.schema.json 保持同步。改动任一侧都必须同步另一侧。 */

export type WallSide = 'north' | 'south' | 'east' | 'west' | 'center'

export interface Surface {
  material?: string
  color?: string
}

export interface RoomSpec {
  type: string
  width: number
  depth: number
  height: number
  size_source?: 'model' | 'preset' | 'user'
  floor?: Surface
  wall?: Surface
  ceiling?: Surface
}

export interface Opening {
  id: string
  type: 'window' | 'door'
  wall: Exclude<WallSide, 'center'>
  offset: number
  width: number
  height: number
  sill: number
}

export interface SceneObject {
  id: string
  category: string
  label?: string
  asset?: {
    kind: 'gltf' | 'primitive'
    url: string | null
    fallback: string
  }
  size: { w: number; d: number; h: number }
  position: [number, number, number]
  rotation_y: number
  against_wall?: WallSide | null
  material?: { color?: string; name?: string }
  color?: string
  confidence?: number
  source?: 'vlm' | 'user' | 'solver'
}

export interface SceneJSON {
  schema_version: string
  scene_id?: string
  room: RoomSpec
  openings?: Opening[]
  objects: SceneObject[]
  lighting?: {
    preset?: 'daylight' | 'evening' | 'neutral'
    ambient_intensity?: number
    main_intensity?: number
  }
  meta?: Record<string, unknown>
}
