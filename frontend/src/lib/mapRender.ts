import chinaGeo from './china-geo'
import { CHINA_BOUNDS, invMercY, mercY, type LngLat } from './geo'
import { PROVINCE_ADCODE, getBoundary, type GeoFeature } from './geoDetail'

export const CITY_SCALE = 3.5
export const COUNTY_SCALE = Number.POSITIVE_INFINITY // 市级为最细颗粒度;县级渲染代码保留,改此值即启用
export const MAX_SCALE = 24

export interface MapView {
  scale: number
  panX: number
  panY: number
}

export interface MapMarker extends LngLat {
  kind: 'guess' | 'truth' | 'ai' | 'pick'
}

export interface FogPoint extends LngLat {
  radiusKm: number
}

const COLORS = {
  bg: '#171e29',
  land: '#223046',
  landAlt: '#26364e',
  border: '#3b4c63',
  label: '#8fa3bd',
  fog: 'rgba(10,12,16,0.78)',
  pick: '#f5a33c',
  truth: '#6fe0a8',
  ai: '#e08484',
  line: '#e9dfc9',
}

interface Projector {
  toCanvas(p: LngLat): [number, number]
  toLngLat(x: number, y: number): LngLat
}

const DEG = Math.PI / 180

export function makeProjector(width: number, height: number, view: MapView): Projector {
  const { lngMin, lngMax, latMin, latMax } = CHINA_BOUNDS
  const xMin = lngMin * DEG
  const xMax = lngMax * DEG
  const yTop = mercY(latMax)
  const yBottom = mercY(latMin)
  const pad = 12
  const baseScale = Math.min((width - pad * 2) / (xMax - xMin), (height - pad * 2) / (yTop - yBottom))
  const s = baseScale * view.scale
  const cx = width / 2 + view.panX
  const cy = height / 2 + view.panY
  const midX = (xMin + xMax) / 2
  const midY = (yTop + yBottom) / 2
  return {
    toCanvas(p: LngLat) {
      return [cx + (p.lng * DEG - midX) * s, cy - (mercY(p.lat) - midY) * s]
    },
    toLngLat(x: number, y: number) {
      const lng = ((x - cx) / s + midX) / DEG
      const lat = invMercY((cy - y) / s + midY)
      return { lng: Math.round(lng * 1e4) / 1e4, lat: Math.round(lat * 1e4) / 1e4 }
    },
  }
}

type Ctx = CanvasRenderingContext2D

function tracePolygon(ctx: Ctx, proj: Projector, rings: readonly (readonly (readonly number[])[])[]) {
  for (const ring of rings) {
    ring.forEach(([lng, lat], i) => {
      const [x, y] = proj.toCanvas({ lng, lat })
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
    })
    ctx.closePath()
  }
}

export function drawMap(
  ctx: Ctx,
  width: number,
  height: number,
  view: MapView,
  opts: {
    markers?: MapMarker[]
    fogPoints?: FogPoint[] | null
    showLabels?: boolean
    requestDetail?: (adcode: number) => void
  } = {},
) {
  if (width < 1 || height < 1) return
  const proj = makeProjector(width, height, view)
  ctx.clearRect(0, 0, width, height)
  ctx.fillStyle = COLORS.bg
  ctx.fillRect(0, 0, width, height)

  chinaGeo.features.forEach((feat, idx) => {
    const geom = feat.geometry
    const polys = geom.type === 'MultiPolygon' ? geom.coordinates : [geom.coordinates]
    ctx.beginPath()
    for (const poly of polys) tracePolygon(ctx, proj, poly)
    ctx.fillStyle = idx % 2 === 0 ? COLORS.land : COLORS.landAlt
    ctx.fill()
    ctx.strokeStyle = COLORS.border
    ctx.lineWidth = 0.8
    ctx.stroke()
  })

  if (opts.fogPoints) {
    const fogCanvas = makeFogLayer(width, height, proj, opts.fogPoints)
    if (fogCanvas) ctx.drawImage(fogCanvas, 0, 0, width, height)
    ctx.strokeStyle = 'rgba(110,130,160,0.28)'
    ctx.lineWidth = 0.6
    for (const feat of chinaGeo.features) {
      const geom = feat.geometry
      const polys = geom.type === 'MultiPolygon' ? geom.coordinates : [geom.coordinates]
      ctx.beginPath()
      for (const poly of polys) tracePolygon(ctx, proj, poly)
      ctx.stroke()
    }
  }

  if (view.scale >= CITY_SCALE) {
    drawDetailLevels(ctx, proj, width, height, view, opts)
  }

  if (opts.showLabels && view.scale > 2.2 && view.scale < CITY_SCALE) {
    ctx.font = '11px sans-serif'
    ctx.fillStyle = COLORS.label
    ctx.textAlign = 'center'
    for (const feat of chinaGeo.features) {
      const [lng, lat] = feat.properties.center
      const [x, y] = proj.toCanvas({ lng, lat })
      if (x > 0 && x < width && y > 0 && y < height) ctx.fillText(feat.properties.name, x, y)
    }
  }

  const markers = opts.markers ?? []
  const byKind = (k: MapMarker['kind']) => markers.filter((m) => m.kind === k)
  const guess = byKind('guess')[0]
  const truth = byKind('truth')[0]
  if (guess && truth) {
    const [x1, y1] = proj.toCanvas(guess)
    const [x2, y2] = proj.toCanvas(truth)
    ctx.strokeStyle = COLORS.line
    ctx.lineWidth = 1.2
    ctx.setLineDash([5, 4])
    ctx.beginPath()
    ctx.moveTo(x1, y1)
    ctx.lineTo(x2, y2)
    ctx.stroke()
    ctx.setLineDash([])
  }
  for (const m of markers) {
    const [x, y] = proj.toCanvas(m)
    const color = m.kind === 'truth' ? COLORS.truth : m.kind === 'ai' ? COLORS.ai : COLORS.pick
    ctx.fillStyle = color
    ctx.beginPath()
    ctx.arc(x, y, 6, 0, Math.PI * 2)
    ctx.fill()
    ctx.strokeStyle = COLORS.bg
    ctx.lineWidth = 2
    ctx.stroke()
    if (m.kind === 'pick') {
      ctx.strokeStyle = color
      ctx.lineWidth = 1
      ctx.beginPath()
      ctx.moveTo(x - 14, y)
      ctx.lineTo(x + 14, y)
      ctx.moveTo(x, y - 14)
      ctx.lineTo(x, y + 14)
      ctx.stroke()
    }
  }
}

interface BBox {
  lngMin: number
  lngMax: number
  latMin: number
  latMax: number
}

const bboxCache = new WeakMap<object, BBox>()

function bboxOf(feat: { geometry: { type: string; coordinates: unknown } }): BBox {
  const hit = bboxCache.get(feat)
  if (hit) return hit
  const box: BBox = { lngMin: 180, lngMax: -180, latMin: 90, latMax: -90 }
  const polys = (
    feat.geometry.type === 'MultiPolygon' ? feat.geometry.coordinates : [feat.geometry.coordinates]
  ) as number[][][][]
  for (const poly of polys)
    for (const ring of poly)
      for (const [lng, lat] of ring) {
        if (lng < box.lngMin) box.lngMin = lng
        if (lng > box.lngMax) box.lngMax = lng
        if (lat < box.latMin) box.latMin = lat
        if (lat > box.latMax) box.latMax = lat
      }
  bboxCache.set(feat, box)
  return box
}

function viewportBBox(proj: Projector, width: number, height: number): BBox {
  const tl = proj.toLngLat(0, 0)
  const br = proj.toLngLat(width, height)
  return { lngMin: tl.lng, lngMax: br.lng, latMin: br.lat, latMax: tl.lat }
}

function intersects(a: BBox, b: BBox): boolean {
  return a.lngMin <= b.lngMax && a.lngMax >= b.lngMin && a.latMin <= b.latMax && a.latMax >= b.latMin
}

function strokeFeatures(ctx: Ctx, proj: Projector, features: GeoFeature[], style: string, lineWidth: number) {
  ctx.strokeStyle = style
  ctx.lineWidth = lineWidth
  for (const feat of features) {
    const geom = feat.geometry
    const polys = (geom.type === 'MultiPolygon' ? geom.coordinates : [geom.coordinates]) as number[][][][]
    ctx.beginPath()
    for (const poly of polys) tracePolygon(ctx, proj, poly)
    ctx.stroke()
  }
}

function labelFeatures(
  ctx: Ctx,
  proj: Projector,
  features: GeoFeature[],
  width: number,
  height: number,
  style: string,
) {
  ctx.font = '11px sans-serif'
  ctx.fillStyle = style
  ctx.textAlign = 'center'
  for (const feat of features) {
    const c = feat.properties.center || feat.properties.centroid
    if (!c) continue
    const [x, y] = proj.toCanvas({ lng: c[0], lat: c[1] })
    if (x > 0 && x < width && y > 0 && y < height) ctx.fillText(feat.properties.name, x, y)
  }
}

function drawDetailLevels(
  ctx: Ctx,
  proj: Projector,
  width: number,
  height: number,
  view: MapView,
  opts: { showLabels?: boolean; requestDetail?: (adcode: number) => void },
) {
  const vp = viewportBBox(proj, width, height)
  for (const feat of chinaGeo.features) {
    if (!intersects(bboxOf(feat as never), vp)) continue
    const adcode = PROVINCE_ADCODE[feat.properties.name]
    if (!adcode) continue
    const cities = getBoundary(adcode)
    if (!cities) {
      opts.requestDetail?.(adcode)
      continue
    }
    strokeFeatures(ctx, proj, cities.features, 'rgba(120,140,170,0.55)', 0.7)
    if (opts.showLabels && view.scale < COUNTY_SCALE) {
      labelFeatures(ctx, proj, cities.features, width, height, COLORS.label)
    }
    if (view.scale >= COUNTY_SCALE) {
      for (const city of cities.features) {
        if (!intersects(bboxOf(city), vp)) continue
        const counties = getBoundary(city.properties.adcode)
        if (!counties) {
          opts.requestDetail?.(city.properties.adcode)
          continue
        }
        strokeFeatures(ctx, proj, counties.features, 'rgba(120,140,170,0.4)', 0.5)
        if (opts.showLabels) {
          labelFeatures(ctx, proj, counties.features, width, height, 'rgba(143,163,189,0.85)')
        }
      }
    }
  }
}

function makeFogLayer(
  width: number,
  height: number,
  proj: Projector,
  points: FogPoint[],
): HTMLCanvasElement | null {
  if (typeof document === 'undefined') return null
  const layer = document.createElement('canvas')
  layer.width = width
  layer.height = height
  const fctx = layer.getContext('2d')
  if (!fctx) return null
  fctx.fillStyle = COLORS.fog
  fctx.fillRect(0, 0, width, height)
  fctx.globalCompositeOperation = 'destination-out'
  for (const p of points) {
    const [x, y] = proj.toCanvas(p)
    const r = Math.max(14, kmToPx(p.radiusKm, proj))
    const grad = fctx.createRadialGradient(x, y, r * 0.3, x, y, r)
    grad.addColorStop(0, 'rgba(0,0,0,0.95)')
    grad.addColorStop(1, 'rgba(0,0,0,0)')
    fctx.fillStyle = grad
    fctx.beginPath()
    fctx.arc(x, y, r, 0, Math.PI * 2)
    fctx.fill()
  }
  return layer
}

function kmToPx(km: number, proj: Projector): number {
  const [x1] = proj.toCanvas({ lng: 100, lat: 35 })
  const [x2] = proj.toCanvas({ lng: 101, lat: 35 })
  const pxPerDegLng = Math.abs(x2 - x1)
  return (km / 91) * pxPerDegLng
}
