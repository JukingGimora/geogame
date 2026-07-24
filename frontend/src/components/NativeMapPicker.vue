<template>
  <map
    class="native-map"
    :style="{ height: height + 'px' }"
    :latitude="center.lat"
    :longitude="center.lng"
    :scale="scale"
    :markers="markerList"
    @tap="onTap"
  ></map>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { LngLat } from '../lib/geo'
import type { MapMarker } from '../lib/mapRender'

const props = withDefaults(
  defineProps<{
    height?: number
    markers?: MapMarker[]
  }>(),
  { height: 420, markers: () => [] },
)

const emit = defineEmits<{ pick: [p: LngLat] }>()

const center = ref<LngLat>({ lat: 35, lng: 105 })
const scale = ref(4)

const markerList = computed(() =>
  props.markers.map((m, i) => ({
    id: i,
    latitude: m.lat,
    longitude: m.lng,
    iconPath: '/static/marker-pick.png',
    width: 38,
    height: 38,
    anchor: { x: 0.5, y: 1 },
  })),
)

function onTap(e: any) {
  const { latitude, longitude } = e.detail
  if (typeof latitude === 'number' && typeof longitude === 'number') {
    emit('pick', { lat: Math.round(latitude * 1e4) / 1e4, lng: Math.round(longitude * 1e4) / 1e4 })
  }
}
</script>

<style scoped>
.native-map {
  width: 100%;
  border-radius: 12px;
  overflow: hidden;
}
</style>
