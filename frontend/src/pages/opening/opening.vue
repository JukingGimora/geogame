<template>
  <view class="opening" :style="{ paddingTop: `${topOffset + 84}px` }" @tap="next">
    <view class="skip" :style="{ top: `${topOffset + 32}px` }" @tap.stop="enter">{{ t('opening.skip') }} »</view>
    <view class="mute" :style="{ top: `${topOffset + 32}px` }" @tap.stop="toggleMute">
      {{ muted ? t('opening.soundOff') : t('opening.soundOn') }}
    </view>
    <view class="lines">
      <text
        v-for="(line, i) in lines"
        :key="i"
        class="line"
        :class="{ visible: i <= shown, date: i === 0, final: i >= lines.length - 2 }"
      >
        {{ line }}
      </text>
    </view>
    <view class="tap" :class="{ visible: shown >= lines.length - 1 }">▸ {{ t('opening.tap') }}</view>
    <text class="build">build {{ BUILD }}</text>
  </view>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
// #ifdef MP-WEIXIN
import { onShareAppMessage, onShareTimeline } from '@dcloudio/uni-app'
// #endif
import { t, tList } from '../../locale'
import { enableShareMenu } from '../../lib/share'
import { api } from '../../api'
import { logEvent } from '../../lib/analytics'
import { BUILD } from '../../lib/version'
import { startRun } from '../../lib/play'

const lines = tList('opening.lines')
const shown = ref(-1)
const topOffset = ref(0)
const muted = ref(false)
// 「叫朋友猜这张」带来的照片 id,原样传给地图页去开局
let wantedPhoto = ''
// 分享来源想让人落在哪一页(比如排行榜分享,看完开场应该看到榜单本身)
let target = ''

onLoad((q) => {
  wantedPhoto = String(q?.photo ?? '')
  target = String(q?.to ?? '')
})
let timer: ReturnType<typeof setInterval> | null = null
let audio: UniApp.InnerAudioContext | null = null

onMounted(() => {
  topOffset.value = (uni.getWindowInfo().statusBarHeight || 0) + 12
  enableShareMenu()
  const seen = uni.getStorageSync('geogame_seen_opening')
  const interval = seen ? 250 : 2000
  logEvent('opening_view', '', undefined, { first_time: !seen })

  audio = uni.createInnerAudioContext()
  audio.src = seen ? '/static/audio/opening-short.mp3' : '/static/audio/opening-full.mp3'
  audio.volume = 0.6
  audio.play()

  timer = setInterval(() => {
    shown.value += 1
    if (shown.value >= lines.length - 1 && timer) clearInterval(timer)
  }, interval)
})

onUnmounted(() => {
  audio?.destroy()
})

function toggleMute() {
  muted.value = !muted.value
  if (!audio) return
  if (muted.value) audio.pause()
  else audio.play()
}

function next() {
  if (shown.value < lines.length - 1) {
    shown.value = lines.length - 1
    if (timer) clearInterval(timer)
  } else {
    enter()
  }
}

// 所有分享都落在这一页,它自己必须也能被转发,否则传播在第一跳就断了
// #ifdef MP-WEIXIN
onShareAppMessage(() => ({ title: t('map.shareTitle'), path: '/pages/opening/opening' }))
onShareTimeline(() => ({ title: t('map.shareTitle') }))
// #endif

async function enterByHistory() {
  try {
    const me = await api.me()
    if ((me.rounds_played ?? 0) > 0) {
      uni.reLaunch({ url: '/pages/map/map' })
      return
    }
  } catch {
    // 拿不到就按新人处理:让他先玩一局,总比丢到空地图强
  }
  startRun(undefined, undefined, { homeOnError: true, mode: 'roam' })
}

function enter() {
  const done = shown.value >= lines.length - 1
  logEvent('opening_leave', '', undefined, { skipped: !done })
  uni.setStorageSync('geogame_seen_opening', '1')
  audio?.stop()
  if (wantedPhoto) {
    uni.reLaunch({ url: `/pages/map/map?photo=${wantedPhoto}` })
  } else if (target === 'rank') {
    uni.reLaunch({ url: '/pages/rank/rank' })
  } else {
    // 没玩过的人直接丢进漫游第一关:先玩,玩完三关再把世界地图交给他;
    // 玩过的人落到地图,那里才是他要的枢纽
    enterByHistory()
  }
}
</script>

<style scoped>
.build {
  position: absolute;
  right: 24rpx;
  bottom: 20rpx;
  color: var(--accent);
  font-size: 26rpx;
  letter-spacing: 2rpx;
}

.opening {
  min-height: 100vh;
  background: #1b1510;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 0 60rpx;
}
.skip {
  position: fixed;
  top: 24rpx;
  right: 40rpx;
  font-size: 24rpx;
  color: var(--ink-dim);
  border: 1px solid var(--line-strong);
  padding: 8rpx 24rpx;
  background: rgba(27, 21, 16, 0.85);
  z-index: 2;
}
.mute {
  position: fixed;
  top: 24rpx;
  left: 40rpx;
  font-size: 24rpx;
  color: var(--ink-dim);
  border: 1px solid var(--line-strong);
  padding: 8rpx 20rpx;
  background: rgba(27, 21, 16, 0.85);
  z-index: 2;
}
.lines {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 18rpx;
}
.line {
  font-family: 'Fusion Pixel 12px Proportional SC', monospace;
  color: var(--ink);
  font-size: 30rpx;
  line-height: 1.9;
  opacity: 0;
  transform: translateY(10px);
  transition: opacity 1.2s ease, transform 1.2s ease;
  text-align: center;
}
.line.visible {
  opacity: 1;
  transform: none;
}
.line.date {
  color: var(--accent);
  letter-spacing: 6rpx;
  font-size: 26rpx;
}
.line.final {
  color: var(--ink);
  font-size: 36rpx;
}
.tap {
  font-family: 'Fusion Pixel 12px Proportional SC', monospace;
  position: fixed;
  bottom: 100rpx;
  font-size: 24rpx;
  color: var(--ink-dim);
  letter-spacing: 8rpx;
  opacity: 0;
  transition: opacity 1s ease;
}
.tap.visible {
  opacity: 0.85;
  animation: pulse 2.6s ease-in-out infinite;
}
@keyframes pulse {
  50% {
    opacity: 0.3;
  }
}
</style>
