<template>
  <view class="home" :style="{ paddingTop: `${topOffset + 48}px` }">
    <view class="header">
      <text class="g-title">{{ t('map.title') }}</text>
      <text class="g-stamp points" v-if="me">{{ t('map.points') }} {{ me.points }}</text>
    </view>
    <view class="map-frame"><ChinaMap :height="mapHeight" :fog-points="fogPoints" :show-labels="true" /></view>
    <view class="actions">
      <button class="g-btn primary" @tap="startRun">{{ t('map.start') }}</button>
      <view class="row">
        <button class="g-btn" @tap="go('/pages/upload/upload')">{{ t('map.upload') }}</button>
        <button class="g-btn" @tap="go('/pages/rank/rank')">{{ t('map.rank') }}</button>
        <button class="g-btn" @tap="go('/pages/mine/mine')">{{ t('map.mine') }}</button>
      </view>
      <!-- #ifdef MP-WEIXIN -->
      <button class="g-btn" open-type="share" @tap="onShareTap">{{ t('map.share') }}</button>
      <!-- #endif -->
    </view>
  </view>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
// #ifdef MP-WEIXIN
import { onShareAppMessage, onShareTimeline } from '@dcloudio/uni-app'
// #endif
import ChinaMap from '../../components/ChinaMap.vue'
import { api } from '../../api'
import { t } from '../../locale'
import { loadFogPoints } from '../../lib/fogStore'
import { logEvent } from '../../lib/analytics'
import type { FogPoint } from '../../lib/mapRender'

const me = ref<{ nickname: string; points: number; avatar_url?: string } | null>(null)
const fogPoints = ref<FogPoint[]>([])
const topOffset = ref(0)
const mapHeight = Math.round(uni.getWindowInfo().windowHeight * 0.62)

onMounted(async () => {
  topOffset.value = (uni.getWindowInfo().statusBarHeight || 0) + 12
  fogPoints.value = loadFogPoints()
  try {
    me.value = await api.me()
  } catch {
    me.value = null
  }
})

async function startRun() {
  try {
    const run = await api.createRun()
    uni.navigateTo({ url: `/pages/play/play?runId=${run.run_id}` })
  } catch (e: any) {
    if (e?.status === 409 && e?.data?.detail === 'all_photos_played') {
      uni.showToast({ title: t('map.allPlayed'), icon: 'none' })
    } else if (e?.status === 409) {
      uni.showToast({ title: t('map.noPhotos'), icon: 'none' })
    } else {
      uni.showToast({ title: '网络异常', icon: 'none' })
    }
  }
}

function go(url: string) {
  uni.navigateTo({ url })
}

// #ifdef MP-WEIXIN
function onShareTap() {
  logEvent('share_click', 'page', undefined, { location: 'map' })
}

onShareAppMessage(() => ({
  title: t('map.shareTitle'),
  path: '/pages/map/map',
}))

onShareTimeline(() => ({
  title: t('map.shareTitle'),
}))
// #endif
</script>

<style scoped>
.home {
  min-height: 100vh;
  background: #16110c;
  padding: 24rpx 24rpx 28rpx;
  box-sizing: border-box;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12rpx;
}

.points {
  font-size: 24rpx;
}

.map-frame {
  border: 1px solid #322818;
  border-radius: 12rpx;
  padding: 6rpx;
  background: #0f0c08;
}

.actions {
  margin-top: 20rpx;
  display: flex;
  flex-direction: column;
  gap: 10rpx;
}

.row {
  display: flex;
  gap: 10rpx;
  flex-wrap: wrap;
}

.row .g-btn {
  flex: 1 1 calc(33% - 10rpx);
  min-width: 0;
}
</style>