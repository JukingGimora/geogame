<template>
  <view class="cmap" :style="{ height: height + 'px' }">
    <!-- #ifdef H5 -->
    <view class="cmap-host"></view>
    <!-- #endif -->
    <!-- #ifdef MP-WEIXIN -->
    <canvas
      :id="canvasId"
      type="2d"
      class="cmap-canvas"
      @touchstart="onWaTouchStart"
      @touchmove="onWaTouchMove"
      @touchend="onWaTouchEnd"
    ></canvas>
    <!-- #endif -->
    <view class="cmap-zoom">
      <view class="cmap-btn" @tap="zoomBy(1.5)">＋</view>
      <view class="cmap-btn" @tap="zoomBy(1 / 1.5)">－</view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { getCurrentInstance, onMounted, ref, watch } from 'vue'
import { MAX_SCALE, drawMap, makeProjector, type FogPoint, type MapMarker, type MapView } from '../lib/mapRender'
import { ensureBoundary } from '../lib/geoDetail'
import type { LngLat } from '../lib/geo'

const props = withDefaults(
  defineProps<{
    height?: number
    interactive?: boolean
    markers?: MapMarker[]
    fogPoints?: FogPoint[] | null
    showLabels?: boolean
  }>(),
  { height: 420, interactive: false, markers: () => [], fogPoints: null, showLabels: true },
)

const emit = defineEmits<{ pick: [p: LngLat] }>()

const canvasId = `cmap-${Math.random().toString(36).slice(2, 8)}`
const view = ref<MapView>({ scale: 1, panX: 0, panY: 0 })

let ctx: CanvasRenderingContext2D | null = null
let cssW = 0
let cssH = 0
let dpr = 1
let backingW = 0
let backingH = 0

let interacting = false
let settleTimer: ReturnType<typeof setTimeout> | null = null

function render() {
  if (!ctx) return
  ctx.setTransform(backingW / cssW, 0, 0, backingH / cssH, 0, 0)
  drawMap(ctx, cssW, cssH, view.value, {
    markers: props.markers,
    fogPoints: props.fogPoints,
    showLabels: props.showLabels,
    requestDetail: (adcode) => ensureBoundary(adcode, scheduleRender),
    skipDetail: interacting,
  })
}

let renderScheduled = false
function scheduleRender() {
  if (interacting) return // 交互中加载完的边界数据不用立刻重绘,skipDetail反正不画它,等scheduleSettle统一补上
  if (renderScheduled) return
  renderScheduled = true
  setTimeout(() => {
    renderScheduled = false
    render()
  }, 80)
}

function beginInteracting() {
  interacting = true
  if (settleTimer) clearTimeout(settleTimer)
}

function scheduleSettle() {
  if (settleTimer) clearTimeout(settleTimer)
  settleTimer = setTimeout(() => {
    interacting = false
    render()
  }, 150)
}

function zoomBy(factor: number) {
  const next = Math.min(MAX_SCALE, Math.max(1, view.value.scale * factor))
  const ratio = next / view.value.scale
  view.value = { scale: next, panX: view.value.panX * ratio, panY: view.value.panY * ratio }
  interacting = true
  render()
  scheduleSettle()
}

watch(() => [props.markers, props.fogPoints], render, { deep: true })

onMounted(() => {
  // #ifdef H5
  setupH5()
  // #endif
  // #ifdef MP-WEIXIN
  setupWeapp()
  // #endif
})

// #ifdef H5
function setupH5() {
  const rootEl = getCurrentInstance()?.proxy?.$el as HTMLElement | undefined
  const host = rootEl?.querySelector('.cmap-host') as HTMLElement | null
  if (!rootEl || !host) return
  const canvas = document.createElement('canvas')
  cssW = rootEl.getBoundingClientRect().width
  if (cssW < 1) {
    setTimeout(setupH5, 60)
    return
  }
  cssH = props.height
  dpr = window.devicePixelRatio || 1
  canvas.width = Math.round(cssW * dpr)
  canvas.height = Math.round(cssH * dpr)
  canvas.style.cssText = `width:${cssW}px;height:${cssH}px;display:block;touch-action:none;`
  host.appendChild(canvas)
  backingW = canvas.width
  backingH = canvas.height
  ctx = canvas.getContext('2d')

  let dragging = false
  let moved = false
  let lastX = 0
  let lastY = 0
  let pinchDist = 0

  canvas.addEventListener('pointerdown', (e) => {
    dragging = true
    moved = false
    lastX = e.clientX
    lastY = e.clientY
    beginInteracting()
  })
  canvas.addEventListener('pointermove', (e) => {
    if (!dragging) return
    const dx = e.clientX - lastX
    const dy = e.clientY - lastY
    if (Math.abs(dx) + Math.abs(dy) > 3) moved = true
    view.value.panX += dx
    view.value.panY += dy
    lastX = e.clientX
    lastY = e.clientY
    render()
  })
  canvas.addEventListener('pointerup', (e) => {
    dragging = false
    if (!moved && props.interactive) {
      const r = canvas.getBoundingClientRect()
      emitPick(e.clientX - r.left, e.clientY - r.top)
    }
    scheduleSettle()
  })
  canvas.addEventListener('pointerleave', () => (dragging = false))
  canvas.addEventListener(
    'wheel',
    (e) => {
      e.preventDefault()
      zoomBy(e.deltaY < 0 ? 1.2 : 1 / 1.2)
    },
    { passive: false },
  )
  canvas.addEventListener('touchmove', (e) => {
    if (e.touches.length === 2) {
      const d = Math.hypot(
        e.touches[0].clientX - e.touches[1].clientX,
        e.touches[0].clientY - e.touches[1].clientY,
      )
      if (pinchDist > 0) zoomBy(d / pinchDist)
      pinchDist = d
    }
  })
  canvas.addEventListener('touchend', () => (pinchDist = 0))

  render()
}
// #endif

// #ifdef MP-WEIXIN
let waLastX = 0
let waLastY = 0
let waMoved = false
let waPinchDist = 0
let waLastRenderAt = 0

function throttledRender() {
  const now = Date.now()
  if (now - waLastRenderAt < 32) return
  waLastRenderAt = now
  render()
}

function onWaTouchStart(e: any) {
  const touch = e.touches[0]
  waLastX = touch.x
  waLastY = touch.y
  waMoved = false
  waPinchDist = 0
  beginInteracting()
}

function onWaTouchMove(e: any) {
  if (e.touches.length === 2) {
    const d = Math.hypot(e.touches[0].x - e.touches[1].x, e.touches[0].y - e.touches[1].y)
    if (waPinchDist > 0) zoomBy(d / waPinchDist)
    waPinchDist = d
    waMoved = true
    waLastX = e.touches[0].x
    waLastY = e.touches[0].y
    return
  }
  const touch = e.touches[0]
  const dx = touch.x - waLastX
  const dy = touch.y - waLastY
  if (Math.abs(dx) + Math.abs(dy) > 3) waMoved = true
  view.value.panX += dx
  view.value.panY += dy
  waLastX = touch.x
  waLastY = touch.y
  throttledRender()
}

function onWaTouchEnd(e: any) {
  waPinchDist = 0
  if (!waMoved && props.interactive) {
    const touch = e.changedTouches?.[0]
    if (touch) emitPick(touch.x, touch.y)
  } else if (waMoved) {
    render()
  }
  scheduleSettle()
}

function setupWeapp() {
  const inst = getCurrentInstance()
  uni
    .createSelectorQuery()
    .in(inst?.proxy)
    .select(`#${canvasId}`)
    .fields({ node: true, size: true }, () => {})
    .exec((res) => {
      const node = res?.[0]?.node
      if (!node) return
      cssW = res[0].width
      cssH = res[0].height
      dpr = uni.getSystemInfoSync().pixelRatio
      node.width = cssW * dpr
      node.height = cssH * dpr
      backingW = node.width
      backingH = node.height
      ctx = node.getContext('2d')
      render()
    })
}
// #endif

function emitPick(x: number, y: number) {
  const proj = makeProjector(cssW, cssH, view.value)
  emit('pick', proj.toLngLat(x, y))
}
</script>

<style scoped>
.cmap {
  position: relative;
  width: 100%;
  background: #171e29;
  border-radius: 12px;
  overflow: hidden;
}
.cmap-canvas,
.cmap-host {
  width: 100%;
  height: 100%;
  display: block;
}
.cmap-zoom {
  position: absolute;
  right: 10px;
  bottom: 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.cmap-btn {
  width: 34px;
  height: 34px;
  line-height: 34px;
  text-align: center;
  background: rgba(35, 45, 62, 0.9);
  color: #c9d4e3;
  border-radius: 8px;
  font-size: 18px;
  user-select: none;
}
</style>
