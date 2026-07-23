export interface LngLat {
  lng: number
  lat: number
}

export const CHINA_BOUNDS = { lngMin: 73, lngMax: 135.5, latMin: 17.5, latMax: 54 }

export function mercY(lat: number): number {
  const rad = (lat * Math.PI) / 180
  return Math.log(Math.tan(Math.PI / 4 + rad / 2))
}

export function invMercY(y: number): number {
  return ((2 * Math.atan(Math.exp(y)) - Math.PI / 2) * 180) / Math.PI
}

export function haversineKm(a: LngLat, b: LngLat): number {
  const R = 6371.0088
  const p1 = (a.lat * Math.PI) / 180
  const p2 = (b.lat * Math.PI) / 180
  const dp = ((b.lat - a.lat) * Math.PI) / 180
  const dl = ((b.lng - a.lng) * Math.PI) / 180
  const h = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(h))
}
