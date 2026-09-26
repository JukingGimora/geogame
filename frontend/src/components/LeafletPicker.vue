<template>
  <view class="leaflet-host" :style="{ height: height + 'px' }">
    <view :id="hostId" class="canvas-box" />
  </view>
</template>

<script setup lang="ts">
import { getCurrentInstance, onMounted, onUnmounted, watch } from 'vue'
import type { LngLat } from '../lib/geo'
import type { MapMarker } from '../lib/mapRender'
import { MAP_THEME } from '../lib/theme'

/**
 * H5 的插针地图:真地图,有城市名和道路,拖得动放得大。
 *
 * 小程序用的是微信自带的地图组件(腾讯),那边本来就够用,这里只管 H5。
 * 原来 H5 跟小程序共用一张手画的 canvas——只有国界轮廓,放大了什么也没有,
 * 等于让人在一张空白纸上找位置,难的不是猜地方而是操作。
 *
 * 瓦片走 OpenStreetMap 的公共服务器:免费、不要 key、全球都有。
 * 它有使用约定(不许当自己的服务用、要署名),所以署名那行不能去掉。
 */
const props = withDefaults(
  defineProps<{ height?: number; markers?: MapMarker[] }>(),
  { height: 320, markers: () => [] },
)
const emit = defineEmits<{ pick: [p: LngLat] }>()

const instance = getCurrentInstance()
const hostId = `leaflet-${Math.random().toString(36).slice(2, 8)}`

let map: any = null
let layer: any = null
let L: any = null

// 用 Esri 而不是 OSM:OSM 的标注是当地文字(亚美尼亚是 Երևան、俄罗斯是西里尔、泰国是泰文),
// 玩家不认识就没法玩。Esri 这套是罗马化的(Yerevan、Vanadzor),全球一致。
const TILES =
  'https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}'
const ATTRIBUTION = 'Tiles &copy; Esri'
const MAX_ZOOM = 17

function pin(kind: MapMarker['kind']): string {
  const colour =
    kind === 'truth' ? MAP_THEME.truth : kind === 'ai' ? MAP_THEME.ai : MAP_THEME.pick
  // 用 DivIcon 画圆点:省一次图片请求,颜色也能跟游戏的配色走
  return `<span style="display:block;width:14px;height:14px;border-radius:50%;
    background:${colour};border:2px solid #fff;box-shadow:0 0 6px rgba(0,0,0,.6)"></span>`
}

function draw() {
  if (!map || !L) return
  layer.clearLayers()
  const pts: any[] = []
  for (const m of props.markers) {
    const icon = L.divIcon({ html: pin(m.kind), className: '', iconSize: [14, 14], iconAnchor: [7, 7] })
    L.marker([m.lat, m.lng], { icon }).addTo(layer)
    pts.push([m.lat, m.lng])
  }
  // 揭晓时把猜测和真实位置连起来,并且一起框进视野
  const guess = props.markers.find((m) => m.kind === 'guess' || m.kind === 'pick')
  const truth = props.markers.find((m) => m.kind === 'truth')
  if (guess && truth) {
    L.polyline([[guess.lat, guess.lng], [truth.lat, truth.lng]], {
      color: MAP_THEME.line, weight: 2, dashArray: '6 6',
    }).addTo(layer)
    map.fitBounds(L.latLngBounds(pts).pad(0.35), { animate: false })
  }
}

onMounted(async () => {
  L = (await import('leaflet')).default
  await import('leaflet/dist/leaflet.css')
  const root = instance?.proxy?.$el as HTMLElement | undefined
  const host = root?.querySelector('.canvas-box') as HTMLElement | null
  if (!host) return

  map = L.map(host, { zoomControl: true, attributionControl: true, worldCopyJump: true })
  // 起始视野给整个世界,但不让它缩到能看见好几个地球
  map.setView([20, 10], 2)
  map.setMinZoom(2)
  L.tileLayer(TILES, { attribution: ATTRIBUTION, maxZoom: MAX_ZOOM, noWrap: false }).addTo(map)
  layer = L.layerGroup().addTo(map)

  map.on('click', (e: any) => {
    const lat = e.latlng.lat
    // 横着拖过接缝之后经度会累加到 190、-200,绕回来再往上报
    const lng = ((e.latlng.lng + 540) % 360) - 180
    emit('pick', { lat, lng })
  })
  draw()
})

onUnmounted(() => {
  map?.remove()
  map = null
})

watch(() => props.markers, draw, { deep: true })
</script>

<style scoped>
.leaflet-host {
  width: 100%;
  border-radius: 8rpx;
  overflow: hidden;
  background: var(--bg-sunken);
}
.canvas-box {
  width: 100%;
  height: 100%;
}
</style>
