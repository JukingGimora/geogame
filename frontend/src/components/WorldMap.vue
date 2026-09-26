<template>
  <view class="world" :style="{ height: height + 'px' }">
    <!-- #ifdef H5 -->
    <view class="cv host" :style="{ height: height + 'px' }" @click="onTap"></view>
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
import { getCurrentInstance, onMounted, ref, watch } from 'vue'
import { BASE_URL } from '../api'
import { CIRCLE_COLORS, THEME } from '../lib/theme'

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
  defineProps<{ height?: number; circles?: CircleState[]; selected?: string }>(),
  { height: 420, circles: () => [], selected: '' },
)
const emit = defineEmits<{ pick: [name: string] }>()

// getCurrentInstance() 一过 await 就返回 null,必须在 setup 阶段先拿住
const instance = getCurrentInstance()
const canvasId = 'world-map'
type Ring = [number, number][]
let loaded = false
let features: { c: string; r: Ring[] }[] = []
// 文化圈的边界线跟国家轮廓来自同一个文件,由 tools/build_circle_outlines.py 算好
let outlines: Record<string, Ring[]> = {}
let box = { w: 0, h: 0 }
let retries = 0

// 以 150°E 为中心:太平洋文化圈不会被地图边缘劈成两半,中国也大致居中。
// 接缝落在大西洋(-30°),那儿几乎全是海。
const CENTER_LNG = 150
const LNG_MIN = -152 // 两边的空海裁掉,画面才不至于又扁又窄
const LNG_MAX = 168

/** 把真实经度换算成"以中心经线为 0"的相对经度 */
function rel(lng: number): number {
  return ((lng - CENTER_LNG + 540) % 360) - 180
}
const LAT_MIN = -58 // 南极不画,省下三分之一的画布
const LAT_MAX = 84

// 等比缩放并居中。按容器直接拉满会把世界压扁,大陆的形状就不对了
function fit() {
  const scale = Math.min(box.w / (LNG_MAX - LNG_MIN), box.h / (LAT_MAX - LAT_MIN))
  return {
    scale,
    offsetX: (box.w - (LNG_MAX - LNG_MIN) * scale) / 2,
    offsetY: (box.h - (LAT_MAX - LAT_MIN) * scale) / 2,
  }
}

function project(lng: number, lat: number): [number, number] {
  const { scale, offsetX, offsetY } = fit()
  return [offsetX + (rel(lng) - LNG_MIN) * scale, offsetY + (LAT_MAX - lat) * scale]
}

function unproject(x: number, y: number): [number, number] {
  const { scale, offsetX, offsetY } = fit()
  const r = LNG_MIN + (x - offsetX) / scale
  return [((r + CENTER_LNG + 540) % 360) - 180, LAT_MAX - (y - offsetY) / scale]
}

// 标签落点手工定,自动算重心会把字压到边缘或海里
// 一个圈可以标好几处:西欧圈分布在西欧、北美、澳新三块地上,只标一处等于没标
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

const state = ref<Record<string, CircleState>>({})
watch(
  () => [props.circles, props.selected] as const,
  () => {
    state.value = Object.fromEntries(props.circles.map((c) => [c.name, c]))
    draw()
  },
  { immediate: true, deep: true },
)

function mix(hex: string, bg: string, t: number): string {
  const c = (h: string, i: number) => parseInt(h.slice(1 + i * 2, 3 + i * 2), 16)
  const v = (i: number) => Math.round(c(hex, i) * t + c(bg, i) * (1 - t))
  return `rgb(${v(0)},${v(1)},${v(2)})`
}

/** 色相说明这是哪个圈,亮度说明你走到哪了 */
function fillFor(circle: string): string {
  const base = CIRCLE_COLORS[circle] ?? THEME.inkFaint
  const s = state.value[circle]
  if (!s) return mix(base, THEME.bgSunken, 0.25)
  if (s.lit) return base                                   // 认出来过:原色
  if (s.played > 0) return mix(base, THEME.bgSunken, 0.6)   // 走过但没认出来
  if (s.photos > 0) return mix(base, THEME.bgSunken, 0.38)  // 有照片可玩
  return mix(base, THEME.bgSunken, 0.2)                     // 还没有照片
}

async function load() {
  if (loaded) return
  const url = `${BASE_URL}/api/v1/geo/world`
  const data = await new Promise<any>((resolve, reject) => {
    uni.request({ url, success: (r) => resolve(r.data), fail: reject })
  })
  features = data.features
  outlines = data.circles ?? {}
  loaded = true
}

/**
 * 按接缝把一个环切成若干段。
 *
 * 地图以 150°E 为中心,接缝在 -30°。俄罗斯、斐济这些横跨接缝的国家,
 * 如果直接连线,会被拉成一条横贯整张图的带子——线上真出现过,像蒙了层雾。
 */
function splitAtSeam(ring: Ring): Ring[] {
  const out: Ring[] = []
  let current: Ring = []
  for (let i = 0; i < ring.length; i++) {
    const p = ring[i]
    if (current.length) {
      const prev = current[current.length - 1]
      if (Math.abs(rel(p[0]) - rel(prev[0])) > 180) {
        out.push(current)
        current = []
      }
    }
    current.push(p)
  }
  if (current.length) out.push(current)
  return out.filter((r) => r.length >= 3)
}

function tracePath(ctx: any, ring: Ring, close = true) {
  ctx.beginPath()
  ring.forEach(([lng, lat]: [number, number], i: number) => {
    const [x, y] = project(lng, lat)
    if (i === 0) ctx.moveTo(x, y)
    else ctx.lineTo(x, y)
  })
  if (close) ctx.closePath()
}

function paint(ctx: any) {
  ctx.fillStyle = THEME.bgSunken
  ctx.fillRect(0, 0, box.w, box.h)
  for (const f of features) {
    const muted = props.selected && props.selected !== f.c
    const color = fillFor(f.c)
    ctx.fillStyle = muted ? mix(color, THEME.bgSunken, 0.35) : color
    // 用同色描边而不是底色:同一个文化圈里的国家会连成一片,
    // 玩家看到的是"一个文化圈",不是一堆国家拼图
    ctx.strokeStyle = ctx.fillStyle
    ctx.lineWidth = 1
    for (const ring of f.r) {
      for (const piece of splitAtSeam(ring)) {
        tracePath(ctx, piece)
        ctx.fill()
        ctx.stroke()
      }
    }
  }
  paintOutlines(ctx)
  paintLabels(ctx)
}

/** 圈的边界线。国界是拼图,这条线才是"文化圈"本身 */
function paintOutlines(ctx: any) {
  for (const [name, loops] of Object.entries(outlines)) {
    const picked = props.selected === name
    const color = CIRCLE_COLORS[name] ?? THEME.inkFaint
    ctx.strokeStyle = picked ? '#fff' : mix(color, THEME.bgSunken, 0.85)
    ctx.lineWidth = picked ? 2.4 : 1.6
    for (const loop of loops) {
      // 被接缝切开的那半圈不能闭合:闭合会在大西洋上拉一道横贯全图的直线
      const pieces = splitAtSeam(loop as Ring)
      for (const piece of pieces) {
        tracePath(ctx, piece, pieces.length === 1)
        ctx.stroke()
      }
    }
  }
}

/** 圈名标在自己那块地上,否则这张图只是"一堆颜色" */
function paintLabels(ctx: any) {
  ctx.font = `${Math.max(9, Math.round(box.w / 34))}px sans-serif`
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  for (const [name, lat, lng] of LABELS) {
    const [x, y] = project(lng, lat)
    const dimmed = props.selected && props.selected !== name
    ctx.fillStyle = dimmed ? 'rgba(255,255,255,0.35)' : 'rgba(255,255,255,0.9)'
    ctx.fillText(name, x, y)
  }
}

async function draw() {
  await load()
  // #ifdef H5
  const root = instance?.proxy?.$el as HTMLElement | undefined
  const host = root?.querySelector('.host') as HTMLElement | null
  if (!host) return
  const width = host.getBoundingClientRect().width
  if (width < 1) {
    setTimeout(draw, 60)
    return
  }
  const dpr = window.devicePixelRatio || 1
  box = { w: width, h: props.height }
  let canvas = host.querySelector('canvas') as HTMLCanvasElement | null
  if (!canvas) {
    canvas = document.createElement('canvas')
    canvas.style.cssText = `width:${box.w}px;height:${box.h}px;display:block`
    host.appendChild(canvas)
  }
  canvas.width = box.w * dpr
  canvas.height = box.h * dpr
  const ctx = canvas.getContext('2d')!
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  paint(ctx)
  // #endif
  // #ifdef MP-WEIXIN
  // 组件里查节点必须 .in(组件实例),否则查的是页面根节点下的同名节点——查不到,画布就是空的
  const query = uni.createSelectorQuery().in(instance?.proxy as any)
  query
    .select(`#${canvasId}`)
    .fields({ node: true, size: true } as any, undefined as any)
    .exec((res: any) => {
      const node = res?.[0]?.node
      if (!node) {
        // 首次渲染可能还没挂上,退一帧再试
        if (retries < 5) {
          retries += 1
          setTimeout(draw, 80)
        }
        return
      }
      retries = 0
      const dpr = uni.getWindowInfo().pixelRatio || 2
      box = { w: res[0].width, h: res[0].height }
      node.width = box.w * dpr
      node.height = box.h * dpr
      const ctx = node.getContext('2d')
      // 必须 setTransform 而不是 scale:重画时 scale 会在上一次的基础上再乘一遍,
      // 第二次就把整张图放大到屏幕外,看着像"地图页什么都没有"
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
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
  // 三端给的事件对象长得不一样:H5 是原生 MouseEvent,小程序把坐标放在 detail 里,
  // 触摸设备走 changedTouches。哪个有值用哪个,少一个分支就变成"点了没反应"。
  const touch = e?.changedTouches?.[0] ?? e?.touches?.[0]
  const clientX = touch?.clientX ?? e?.clientX
  const clientY = touch?.clientY ?? e?.clientY
  const pageX = e?.detail?.x ?? touch?.pageX ?? e?.pageX
  const pageY = e?.detail?.y ?? touch?.pageY ?? e?.pageY

  // #ifdef H5
  const root = instance?.proxy?.$el as HTMLElement | undefined
  const host = root?.querySelector('.host') as HTMLElement | null
  if (host) {
    const rect = host.getBoundingClientRect()
    const x = clientX ?? (pageX != null ? pageX - window.scrollX : undefined)
    const y = clientY ?? (pageY != null ? pageY - window.scrollY : undefined)
    if (typeof x === 'number' && typeof y === 'number') hit(x - rect.left, y - rect.top)
    return
  }
  // #endif

  if (typeof pageX !== 'number' || typeof pageY !== 'number') return
  uni
    .createSelectorQuery()
    .in(instance?.proxy as any)
    .select(`#${canvasId}`)
    .boundingClientRect(((rect: any) => {
      hit(rect ? pageX - rect.left : pageX, rect ? pageY - rect.top : pageY)
    }) as any)
    .exec()
}

function hit(x: number, y: number) {
  const [lng, lat] = unproject(x, y)
  for (const f of features) {
    if (f.r.some((ring) => inRing(lng, lat, ring))) {
      emit('pick', f.c)
      return
    }
  }
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
