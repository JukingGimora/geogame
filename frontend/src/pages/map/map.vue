<template>
  <view class="home" :style="{ paddingTop: `${topOffset + 56}px` }">
    <text class="g-title title">{{ t('map.title') }}</text>
    <text class="sub">{{ subtitle }}</text>

    <view class="circles">
      <view
        v-for="c in circles"
        :key="c.name"
        class="circle"
        :class="{ lit: c.lit, empty: c.photos === 0 }"
        @tap="enter(c)"
      >
        <view class="circle-head">
          <text class="circle-name px-font">{{ c.name }}</text>
          <text class="circle-count">{{ c.photos > 0 ? t('map.circlePhotos', { n: c.photos }) : t('map.circleEmpty') }}</text>
        </view>
        <text class="circle-desc">{{ c.desc }}</text>
      </view>
    </view>

    <button class="g-btn primary start" @tap="onStart">{{ t('map.start') }}</button>
    <view class="row">
      <button class="g-btn" @tap="go('/pages/upload/upload')">{{ t('map.upload') }}</button>
      <button class="g-btn" @tap="go('/pages/rank/rank')">{{ t('map.rank') }}</button>
      <button class="g-btn" @tap="go('/pages/mine/mine')">{{ t('map.mine') }}</button>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { onLoad, onShow } from '@dcloudio/uni-app'
// #ifdef MP-WEIXIN
import { onShareAppMessage, onShareTimeline } from '@dcloudio/uni-app'
// #endif
import { api } from '../../api'
import { t } from '../../locale'
import { enableShareMenu } from '../../lib/share'
import { startRun } from '../../lib/play'
import { logEvent } from '../../lib/analytics'

interface Circle {
  name: string
  desc: string
  photos: number
  played: number
  lit: boolean
}

const circles = ref<Circle[]>([])
const topOffset = ref(0)

// 点亮了几个圈,是玩家在这游戏里唯一一直累积的东西,放在最显眼的第二行
const subtitle = computed(() => {
  const lit = circles.value.filter((c) => c.lit).length
  return t('map.progress', { lit, total: circles.value.length || 9 })
})

// 朋友指名的那张:一进来就开局,别让人还得自己找"开始一轮"
onLoad((q) => {
  const id = Number(q?.photo)
  if (id) startRun(id)
})

onMounted(() => {
  topOffset.value = (uni.getWindowInfo().statusBarHeight || 0) + 12
  enableShareMenu()
})

onShow(load)

async function load() {
  try {
    const res = await api.circles()
    circles.value = res.items
  } catch {
    // 拉不到就让页面空着,至少"开始一轮"还能点
  }
}

function enter(c: Circle) {
  logEvent('circle_click', 'circle', undefined, { name: c.name, photos: c.photos, lit: c.lit })
  if (c.photos === 0) {
    uni.showToast({ title: t('map.circleEmptyHint'), icon: 'none', duration: 2200 })
    return
  }
  startRun(undefined, c.name)
}

function onStart() {
  logEvent('start_click', 'page', undefined, { from: 'home' })
  startRun()
}

function go(url: string) {
  logEvent('home_nav', 'page', undefined, { to: url.split('/').pop() })
  uni.navigateTo({ url })
}

// #ifdef MP-WEIXIN
onShareAppMessage(() => ({
  title: t('map.shareTitle'),
  path: '/pages/opening/opening',
}))

onShareTimeline(() => ({
  title: t('map.shareTitle'),
}))
// #endif
</script>

<style scoped>
.home {
  min-height: 100vh;
  background: var(--bg);
  padding: 0 32rpx 40rpx;
  box-sizing: border-box;
}

.title {
  display: block;
  font-size: 44rpx;
}

.sub {
  display: block;
  color: var(--ink-faint);
  font-size: 24rpx;
  margin-top: 14rpx;
}

.circles {
  margin: 44rpx 0 40rpx;
}

/* 没有边框,靠底色深浅分层:框太多是"廉价感"最主要的来源 */
.circle {
  background: var(--card);
  border-radius: 12rpx;
  padding: 26rpx 28rpx;
  margin-bottom: 14rpx;
  opacity: 0.55;
}

.circle.lit {
  opacity: 1;
}

.circle.empty {
  opacity: 0.3;
}

.circle-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
}

.circle-name {
  color: var(--ink);
  font-size: 32rpx;
}

.circle.lit .circle-name {
  color: var(--accent);
}

.circle-count {
  color: var(--ink-faint);
  font-size: 22rpx;
}

.circle-desc {
  display: block;
  color: var(--ink-dim);
  font-size: 24rpx;
  line-height: 1.7;
  margin-top: 10rpx;
}

.start {
  width: 100%;
}

.row {
  display: flex;
  gap: 16rpx;
  margin-top: 20rpx;
}

.row .g-btn {
  flex: 1;
  min-width: 0;
}
</style>
