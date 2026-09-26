<template>
  <view class="picker" :style="{ height: height + 'px' }">
    <!-- #ifdef H5 -->
    <view class="host" :style="{ height: height + 'px' }"></view>
    <!-- #endif -->
    <!-- #ifdef MP-WEIXIN -->
    <canvas
      type="2d"
      :id="canvasId"
      class="cv"
      :style="{ height: height + 'px' }"
      @touchstart="onDown"
      @touchmove="onMove"
      @touchend="onUp"
    ></canvas>
    <!-- #endif -->
    <view v-if="interactive" class="zoom">
      <view class="zoom-btn" @tap="zoomBy(1.6)">＋</view>
      <view class="zoom-btn" @tap="zoomBy(0.625)">－</view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { getCurrentInstance, onMounted, watch } from 'vue'
import { BASE_URL } from '../api'
import { CIRCLE_COLORS, THEME } from '../lib/theme'
import type { LngLat } from '../lib/geo'
import type { MapMarker } from '../lib/mapRender'

/**
 * 世界地图:插旗和看结果都用它。
 *
 * 以前这两处用的是只会画中国的地图组件,题库出国之后,H5 上根本没法给
 * 布哈拉插旗,揭晓时真实位置也落在图外。
 *
 * 一屏放下整个世界时 1 像素约等于 100 公里,所以必须能拖能放大,
 * 否则手指精度本身就成了误差来源。
 */
const props = withDefaults(
  defineProps<{
    height?: number
    interactive?: boolean
    markers?: MapMarker[]
  }>(),
  { height: 320, interactive: false, markers: () => [] },
)
const emit = defineEmits<{ pick: [p: LngLat] }>()

const instance = getCurrentInstance()
const canvasId = 'world-picker'
type Ring = [number, number][]
let features: { c: string; r: Ring[] }[] = []
// 文化圈的边界线跟国家轮廓来自同一个文件,由 tools/build_circle_outlines.py 算好
let outlines: Record<string, Ring[]> = {}
let loaded = false
let box = { w: 0, h: 0 }

const CENTER_LNG = 150
const SPAN_LNG = 360
const LAT_MAX = 84
const LAT_MIN = -58

// 视图状态:scale=1 时整个世界刚好铺满宽度
let scale = 1
let panX = 0
let panY = 0

function rel(lng: number): number {
  return ((lng - CENTER_LNG + 540) % 360) - 180
}

function base() {
  return Math.min(box.w / SPAN_LNG, box.h / (LAT_MAX - LAT_MIN))
}

function project(lng: number, lat: number): [number, number] {
  const k = base() * scale
  return [box.w / 2 + (rel(lng) * k) + panX, box.h / 2 + ((LAT_MAX + LAT_MIN) / 2 - lat) * k + panY]
}

function unproject(x: number, y: number): [number, number] {
  const k = base() * scale
  const r = (x - box.w / 2 - panX) / k
  const lat = (LAT_MAX + LAT_MIN) / 2 - (y - box.h / 2 - panY) / k
  return [((r + CENTER_LNG + 540) % 360) - 180, lat]
}

async function load() {
  if (loaded) return
  const data = await new Promise<any>((resolve, reject) => {
    uni.request({ url: `${BASE_URL}/api/v1/geo/world`, success: (r) => resolve(r.data), fail: reject })
  })
  features = data.features
  outlines = data.circles ?? {}
  loaded = true
}

function splitAtSeam(ring: Ring): Ring[] {
  const out: Ring[] = []
  let cur: Ring = []
  for (const p of ring) {
    if (cur.length && Math.abs(rel(p[0]) - rel(cur[cur.length - 1][0])) > 180) {
      out.push(cur)
      cur = []
    }
    cur.push(p)
  }
  if (cur.length) out.push(cur)
  return out.filter((r) => r.length >= 3)
}

// 和首页那张图用同一批落点,免得两处对不上
const LABELS: [string, number, number][] = [
  ['东亚', 36, 108],
  ['东南亚', -2, 112],
  ['南亚', 22, 78],
  ['伊斯兰', 26, 38],
  ['西欧', 50, 10],
  ['西欧', 44, -100],
  ['西欧', -26, 134],
  ['东欧', 60, 80],
  ['非洲', -8, 22],
  ['拉美', -18, -60],
  ['太平洋', -12, -170],
]

function mix(hex: string, bg: string, t: number): string {
  const c = (h: string, i: number) => parseInt(h.slice(1 + i * 2, 3 + i * 2), 16)
  const v = (i: number) => Math.round(c(hex, i) * t + c(bg, i) * (1 - t))
  return `rgb(${v(0)},${v(1)},${v(2)})`
}

function paint(ctx: any) {
  ctx.fillStyle = THEME.bgSunken
  ctx.fillRect(0, 0, box.w, box.h)
  // 南极那圈在等距圆柱投影下会摊成一条横带,裁掉视野外的部分就干净了
  ctx.save()
  ctx.beginPath()
  ctx.rect(0, 0, box.w, box.h)
  ctx.clip()
  for (const f of features) {
    // 插旗时地图是背景,别跟标记抢眼:文化圈的颜色压到很暗
    const color = mix(CIRCLE_COLORS[f.c] ?? THEME.inkFaint, THEME.bgSunken, 0.3)
    ctx.fillStyle = color
    ctx.strokeStyle = color
    ctx.lineWidth = 1
    for (const ring of f.r) {
      for (const piece of splitAtSeam(ring)) {
        ctx.beginPath()
        piece.forEach(([lng, lat], i) => {
          const [x, y] = project(lng, lat)
          if (i === 0) ctx.moveTo(x, y)
          else ctx.lineTo(x, y)
        })
        ctx.closePath()
        ctx.fill()
        ctx.stroke()
      }
    }
  }
  // 圈的范围线:提示③说的就是"在南亚文化圈",插旗时得知道那圈在哪。
  // 放大之后收起来,不然挡住要看的细节
  if (scale < 3) {
    ctx.font = `${Math.max(9, Math.round(box.w / 38))}px sans-serif`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    for (const [name, loops] of Object.entries(outlines)) {
      const color = CIRCLE_COLORS[name] ?? THEME.inkFaint
      ctx.strokeStyle = mix(color, THEME.bgSunken, 0.55)
      ctx.lineWidth = 1
      for (const loop of loops) {
        // 被接缝切开的那半圈不能闭合,否则大西洋上会多一道横线
        const pieces = splitAtSeam(loop as Ring)
        for (const piece of pieces) {
          ctx.beginPath()
          piece.forEach(([lng, lat], i) => {
            const [x, y] = project(lng, lat)
            if (i === 0) ctx.moveTo(x, y)
            else ctx.lineTo(x, y)
          })
          if (pieces.length === 1) ctx.closePath()
          ctx.stroke()
        }
      }
    }
    for (const [name, lat, lng] of LABELS) {
      const [x, y] = project(lng, lat)
      ctx.fillStyle = 'rgba(233,223,201,0.45)'
      ctx.fillText(name, x, y)
    }
  }
  ctx.restore()
  for (const m of props.markers) {
    const [x, y] = project(m.lng, m.lat)
    const color =
      m.kind === 'truth' ? THEME.good : m.kind === 'ai' ? THEME.warn : THEME.accent
    if (m.kind === 'truth') {
      const guess = props.markers.find((g) => g.kind === 'guess')
      if (guess) {
        const [gx, gy] = project(guess.lng, guess.lat)
        ctx.strokeStyle = 'rgba(233,223,201,0.5)'
        ctx.setLineDash?.([4, 4])
        ctx.beginPath()
        ctx.moveTo(gx, gy)
        ctx.lineTo(x, y)
        ctx.stroke()
        ctx.setLineDash?.([])
      }
    }
    ctx.fillStyle = color
    ctx.beginPath()
    ctx.arc(x, y, 6, 0, Math.PI * 2)
    ctx.fill()
  }
}

function h5Canvas(): HTMLCanvasElement | null {
  const root = instance?.proxy?.$el as HTMLElement | undefined
  const host = root?.querySelector('.host') as HTMLElement | null
  if (!host) return null
  const width = host.getBoundingClientRect().width
  if (width < 1) return null
  box = { w: width, h: props.height }
  let canvas = host.querySelector('canvas') as HTMLCanvasElement | null
  if (!canvas) {
    canvas = document.createElement('canvas')
    canvas.style.cssText = `width:${box.w}px;height:${box.h}px;display:block;touch-action:none`
    host.appendChild(canvas)
    bindH5(canvas)
  }
  const dpr = window.devicePixelRatio || 1
  canvas.width = box.w * dpr
  canvas.height = box.h * dpr
  const ctx = canvas.getContext('2d')!
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  return canvas
}

async function draw() {
  await load()
  // #ifdef H5
  const canvas = h5Canvas()
  if (!canvas) {
    setTimeout(draw, 60)
    return
  }
  paint(canvas.getContext('2d'))
  // #endif
  // #ifdef MP-WEIXIN
  uni
    .createSelectorQuery()
    .in(instance?.proxy as any)
    .select(`#${canvasId}`)
    .fields({ node: true, size: true } as any, undefined as any)
    .exec((res: any) => {
      const node = res?.[0]?.node
      if (!node) {
        setTimeout(draw, 80)
        return
      }
      const dpr = uni.getWindowInfo().pixelRatio || 2
      box = { w: res[0].width, h: res[0].height }
      node.width = box.w * dpr
      node.height = box.h * dpr
      const ctx = node.getContext('2d')
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      paint(ctx)
    })
  // #endif
}

function zoomBy(k: number) {
  scale = Math.min(24, Math.max(1, scale * k))
  panX *= k
  panY *= k
  clampPan()
  draw()
}

function clampPan() {
  const k = base() * scale
  const halfW = (SPAN_LNG * k) / 2
  const halfH = ((LAT_MAX - LAT_MIN) * k) / 2
  panX = Math.max(-(halfW - box.w / 2), Math.min(halfW - box.w / 2, panX))
  panY = Math.max(-(halfH - box.h / 2), Math.min(halfH - box.h / 2, panY))
}

// 拖动与点击:同一根手指,移动超过阈值算拖,否则算插旗
let dragging = false
let moved = false
let lastX = 0
let lastY = 0

function start(x: number, y: number) {
  dragging = true
  moved = false
  lastX = x
  lastY = y
}

function move(x: number, y: number) {
  if (!dragging) return
  const dx = x - lastX
  const dy = y - lastY
  if (Math.abs(dx) + Math.abs(dy) > 3) moved = true
  panX += dx
  panY += dy
  lastX = x
  lastY = y
  clampPan()
  draw()
}

function end(x: number, y: number) {
  dragging = false
  if (moved || !props.interactive) return
  const [lng, lat] = unproject(x, y)
  emit('pick', { lat: Math.round(lat * 1e4) / 1e4, lng: Math.round(lng * 1e4) / 1e4 })
}

// #ifdef H5
function bindH5(canvas: HTMLCanvasElement) {
  const local = (e: MouseEvent | Touch) => {
    const r = canvas.getBoundingClientRect()
    return [e.clientX - r.left, e.clientY - r.top] as const
  }
  canvas.addEventListener('mousedown', (e) => start(...local(e)))
  canvas.addEventListener('mousemove', (e) => move(...local(e)))
  canvas.addEventListener('mouseup', (e) => end(...local(e)))
  canvas.addEventListener('mouseleave', () => (dragging = false))
  canvas.addEventListener('touchstart', (e) => start(...local(e.touches[0])), { passive: true })
  canvas.addEventListener('touchmove', (e) => move(...local(e.touches[0])), { passive: true })
  canvas.addEventListener('touchend', (e) => end(...local(e.changedTouches[0])), { passive: true })
  canvas.addEventListener('wheel', (e) => {
    e.preventDefault()
    zoomBy(e.deltaY < 0 ? 1.15 : 1 / 1.15)
  })
}
// #endif

// #ifdef MP-WEIXIN
function onDown(e: any) {
  const t = e.touches?.[0]
  if (t) start(t.x, t.y)
}
function onMove(e: any) {
  const t = e.touches?.[0]
  if (t) move(t.x, t.y)
}
function onUp(e: any) {
  const t = e.changedTouches?.[0]
  if (t) end(t.x, t.y)
}
// #endif

watch(() => props.markers, draw, { deep: true })
onMounted(draw)
</script>

<style scoped>
.picker {
  position: relative;
  width: 100%;
  border-radius: 12rpx;
  overflow: hidden;
  background: var(--bg-sunken);
}
.host,
.cv {
  width: 100%;
  display: block;
}
.zoom {
  position: absolute;
  right: 16rpx;
  bottom: 16rpx;
  display: flex;
  flex-direction: column;
  gap: 10rpx;
}
.zoom-btn {
  width: 56rpx;
  height: 56rpx;
  line-height: 56rpx;
  text-align: center;
  border-radius: 8rpx;
  background: var(--card);
  color: var(--ink);
  font-size: 30rpx;
}
</style>
