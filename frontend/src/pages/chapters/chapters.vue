<template>
  <view class="chapters" :style="{ paddingTop: `${topOffset + 48}px` }">
    <view class="header">
      <text class="g-title">{{ t('chapters.title') }}</text>
      <text class="g-stamp seen" v-if="me">{{ t('map.points') }} {{ me.points }}</text>
    </view>

    <view v-for="c in ordered" :key="c.key" class="card" @tap="open(c.key)">
      <view class="card-main">
        <text class="card-title px-font">{{ t(`chapters.${c.key}`) }}</text>
        <text class="card-desc">{{ t(`chapters.${c.key}Desc`) }}</text>
      </view>
      <text class="card-arrow g-stamp">›</text>
    </view>

    <view class="row">
      <button class="g-btn" @tap="go('/pages/upload/upload')">{{ t('map.upload') }}</button>
      <button class="g-btn" @tap="go('/pages/rank/rank')">{{ t('map.rank') }}</button>
      <button class="g-btn" @tap="go('/pages/mine/mine')">{{ t('map.mine') }}</button>
    </view>
  </view>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
// #ifdef MP-WEIXIN
import { onShareAppMessage, onShareTimeline } from '@dcloudio/uni-app'
// #endif
import { api } from '../../api'
import { t } from '../../locale'
import { enableShareMenu } from '../../lib/share'
import { startRun } from '../../lib/play'

const me = ref<{ nickname: string; points: number } | null>(null)
const topOffset = ref(0)

// 小程序这边先看中国,H5 那边先看世界——两个入口进来的是两拨人,
// 但打的是同一个库、排的是同一个榜,他们会在排行榜上撞见对方。
const CHAPTERS = [{ key: 'china' }, { key: 'world' }]
let worldFirst = false
// #ifdef H5
worldFirst = true
// #endif
const ordered = worldFirst ? [...CHAPTERS].reverse() : CHAPTERS

onMounted(async () => {
  topOffset.value = (uni.getWindowInfo().statusBarHeight || 0) + 12
  enableShareMenu()
  try {
    me.value = await api.me()
  } catch {
    me.value = null
  }
})

function open(key: string) {
  // 中国这一章有迷雾地图可看,先进地图页;世界还没有地图,直接开局
  if (key === 'china') uni.navigateTo({ url: '/pages/map/map' })
  else startRun(undefined, 'world')
}

function go(url: string) {
  uni.navigateTo({ url })
}

// #ifdef MP-WEIXIN
onShareAppMessage(() => ({ title: t('map.shareTitle'), path: '/pages/opening/opening' }))
onShareTimeline(() => ({ title: t('map.shareTitle') }))
// #endif
</script>

<style scoped>
.chapters {
  min-height: 100vh;
  background: #efe3c8;
  padding: 24rpx 24rpx 28rpx;
  box-sizing: border-box;
}
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 28rpx;
}
.seen {
  font-size: 24rpx;
}
.card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fbf5e6;
  border: 1px solid #c8b58a;
  border-radius: 12rpx;
  padding: 36rpx 28rpx;
  margin-bottom: 20rpx;
}
.card-main {
  flex: 1;
  min-width: 0;
}
.card-title {
  display: block;
  color: #b8531a;
  font-size: 34rpx;
}
.card-desc {
  display: block;
  color: #7a6a4d;
  font-size: 24rpx;
  margin-top: 10rpx;
}
.card-arrow {
  font-size: 40rpx;
  margin-left: 16rpx;
}
.row {
  display: flex;
  gap: 10rpx;
  margin-top: 40rpx;
}
.row .g-btn {
  flex: 1 1 calc(33% - 10rpx);
  min-width: 0;
}
</style>
