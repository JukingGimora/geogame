import type { FogPoint } from './mapRender'

const KEY = 'geogame_fog_points'

export function loadFogPoints(): FogPoint[] {
  try {
    return JSON.parse(uni.getStorageSync(KEY) || '[]')
  } catch {
    return []
  }
}

export function addFogPoint(p: FogPoint): void {
  const points = loadFogPoints()
  points.push(p)
  uni.setStorageSync(KEY, JSON.stringify(points.slice(-500)))
}
