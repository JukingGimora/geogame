<template>
  <view class="picker-wrap" :style="{ height: height + 'px' }">
    <map
      :id="mapId"
      class="native-map"
      :style="{ height: height + 'px' }"
      :latitude="center.lat"
      :longitude="center.lng"
      :scale="scale"
      :markers="markerList"
      @tap="onTap"
      @poitap="onTap"
      @regionchange="onRegionChange"
    ></map>
    <!-- 拖地图对准这个十字即可,不依赖点击事件 -->
    <view class="crosshair">
      <view class="cross-v" />
      <view class="cross-h" />
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { LngLat } from '../lib/geo'
import type { MapMarker } from '../lib/mapRender'

/**
 * 小程序原生地图选点。
 *
 * 只监听 @tap 曾导致"点了没反应":地图上到处是地名,点中兴趣点时微信触发的是
 * @poitap,普通 @tap 根本不发；旧版基础库的 @tap 还不返回坐标。所以主交互改成
 * 拖动地图对准中心十字,点击只当快捷方式——哪种情况都插得下旗。
 */
const props = withDefaults(
  defineProps<{
    height?: number
    markers?: MapMarker[]
  }>(),
  { height: 420, markers: () => [] },
)

const emit = defineEmits<{ pick: [p: LngLat] }>()

const mapId = 'pick-map'
const center = ref<LngLat>({ lat: 35, lng: 105 })
const scale = ref(4)

const markerList = computed(() =>
  props.markers.map((m, i) => ({
    id: i,
    latitude: m.lat,
    longitude: m.lng,
    iconPath: '/static/marker-pick.png',
    width: 26,
    height: 26,
    anchor: { x: 0.5, y: 1 },
  })),
)

function round(v: number): number {
  return Math.round(v * 1e4) / 1e4
}

function onTap(e: any) {
  const { latitude, longitude } = e?.detail ?? {}
  if (typeof latitude === 'number' && typeof longitude === 'number') {
    emit('pick', { lat: round(latitude), lng: round(longitude) })
  }
}

function onRegionChange(e: any) {
  if (e?.type !== 'end' && e?.detail?.type !== 'end') return
  // 拖完地图,中心点就是他要插的地方
  uni
    .createMapContext(mapId)
    .getCenterLocation({
      success: (res: any) => emit('pick', { lat: round(res.latitude), lng: round(res.longitude) }),
      fail: () => {},
    })
}
</script>

<style scoped>
.picker-wrap {
  position: relative;
  width: 100%;
}
.native-map {
  width: 100%;
  border-radius: 12px;
  overflow: hidden;
}
.crosshair {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 60rpx;
  height: 60rpx;
  margin-left: -30rpx;
  margin-top: -30rpx;
  pointer-events: none;
}
.cross-v {
  position: absolute;
  left: 29rpx;
  top: 0;
  width: 2rpx;
  height: 60rpx;
  background: var(--accent);
}
.cross-h {
  position: absolute;
  top: 29rpx;
  left: 0;
  height: 2rpx;
  width: 60rpx;
  background: var(--accent);
}
</style>
