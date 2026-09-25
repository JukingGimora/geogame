<template>
  <view class="world" :style="{ height: height + 'px' }">
    <!-- #ifdef H5 -->
    <canvas :id="canvasId" class="cv" :style="{ height: height + 'px' }" @click="onTap"></canvas>
    <!-- #endif -->
    <!-- #ifdef MP-WEIXIN -->
    <canvas
      type="2d"
      :id="canvasId"
      class="cv"
      :style="{ height: height + 'px' }"
      @tap="onTap"
    ></canvas>
    <!-- #endif -->
  </view>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { BASE_URL } from '../api'
import { THEME } from '../lib/theme'

/**
 * 世界地图,按文化圈上色。
 *
 * 玩过的圈亮,没玩过的暗——地图本身就是进度条,不需要再写一行"你点亮了 3/9"。
 * 轮廓数据后端已经标好每块属于哪个圈,前端不判国界。
 */
interface CircleState {
  name: string
  photos: number
  played: number
  lit: boolean
}

const props = withDefaults(
  defineProps<{ height?: number; circles?: CircleState[] }>(),
  { height: 420, circles: () => [] },
)
const emit = defineEmits<{ pick: [name: string] }>()

const canvasId = 'world-map'
type Ring = [number, number][]
let loaded = false
let features: { c: string; r: Ring[] }[] = []
let box = { w: 0, h: 0 }

// 等距圆柱投影:南北极的形变无所谓,我们只要认得出哪块是哪块
const LNG_MIN = -180
const LNG_MAX = 180
const LAT_MIN = -58 // 南极不画,省下三分之一的画布
const LAT_MAX = 84

function project(lng: number, lat: number): [number, number] {
  const x = ((lng - LNG_MIN) / (LNG_MAX - LNG_MIN)) * box.w
  const y = ((LAT_MAX - lat) / (LAT_MAX - LAT_MIN)) * box.h
  return [x, y]
}

function unproject(x: number, y: number): [number, number] {
  const lng = LNG_MIN + (x / box.w) * (LNG_MAX - LNG_MIN)
  const lat = LAT_MAX - (y / box.h) * (LAT_MAX - LAT_MIN)
  return [lng, lat]
}

const state = ref<Record<string, CircleState>>({})
watch(
  () => props.circles,
  (list) => {
    state.value = Object.fromEntries(list.map((c) => [c.name, c]))
    draw()
  },
  { immediate: true, deep: true },
)

function fillFor(circle: string): string {
  const s = state.value[circle]
  if (!s) return THEME.card
  if (s.lit) return THEME.accent          // 认出来过:最亮
  if (s.played > 0) return '#6b5230'      // 走过但没认出来:半亮
  if (s.photos > 0) return '#332a1c'      // 有照片可玩:微亮
  return '#241d15'                        // 还没有照片:最暗
}

async function load() {
  if (loaded) return
  const url = `${BASE_URL}/api/v1/geo/world`
  const data = await new Promise<any>((resolve, reject) => {
    uni.request({ url, success: (r) => resolve(r.data), fail: reject })
  })
  features = data.features
  loaded = true
}

function paint(ctx: any) {
  ctx.fillStyle = THEME.bgSunken
  ctx.fillRect(0, 0, box.w, box.h)
  for (const f of features) {
    ctx.fillStyle = fillFor(f.c)
    ctx.strokeStyle = THEME.bgSunken
    ctx.lineWidth = 0.6
    for (const ring of f.r) {
      ctx.beginPath()
      ring.forEach(([lng, lat]: [number, number], i: number) => {
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

async function draw() {
  await load()
  // #ifdef H5
  const el = document.getElementById(canvasId) as HTMLCanvasElement | null
  if (!el) return
  const dpr = window.devicePixelRatio || 1
  box = { w: el.clientWidth, h: el.clientHeight }
  el.width = box.w * dpr
  el.height = box.h * dpr
  const ctx = el.getContext('2d')!
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  paint(ctx)
  // #endif
  // #ifdef MP-WEIXIN
  const query = uni.createSelectorQuery()
  query
    .select(`#${canvasId}`)
    .fields({ node: true, size: true } as any, undefined as any)
    .exec((res: any) => {
      const node = res?.[0]?.node
      if (!node) return
      const dpr = uni.getWindowInfo().pixelRatio || 2
      box = { w: res[0].width, h: res[0].height }
      node.width = box.w * dpr
      node.height = box.h * dpr
      const ctx = node.getContext('2d')
      ctx.scale(dpr, dpr)
      paint(ctx)
    })
  // #endif
}

function inRing(lng: number, lat: number, ring: Ring): boolean {
  let inside = false
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i]
    const [xj, yj] = ring[j]
    if (yi > lat !== yj > lat && lng < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) inside = !inside
  }
  return inside
}

function onTap(e: any) {
  const x = e.detail?.x ?? e.offsetX
  const y = e.detail?.y ?? e.offsetY
  if (typeof x !== 'number' || typeof y !== 'number') return
  // 小程序给的是页面坐标,减掉画布在页面里的位置
  const query = uni.createSelectorQuery()
  query
    .select(`#${canvasId}`)
    .boundingClientRect(((rect: any) => {
      const localX = rect ? x - rect.left : x
      const localY = rect ? y - rect.top : y
      const [lng, lat] = unproject(localX, localY)
      for (const f of features) {
        if (f.r.some((ring) => inRing(lng, lat, ring))) {
          emit('pick', f.c)
          return
        }
      }
    }) as any)
    .exec()
}

onMounted(draw)
</script>

<style scoped>
.world {
  width: 100%;
  border-radius: 12rpx;
  overflow: hidden;
  background: var(--bg-sunken);
}
.cv {
  width: 100%;
  display: block;
}
</style>
