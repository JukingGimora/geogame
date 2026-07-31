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
  </view>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
// #ifdef MP-WEIXIN
import { onShareAppMessage, onShareTimeline } from '@dcloudio/uni-app'
// #endif
import { t, tList } from '../../locale'
import { enableShareMenu } from '../../lib/share'

const lines = tList('opening.lines')
const shown = ref(-1)
const topOffset = ref(0)
const muted = ref(false)
let timer: ReturnType<typeof setInterval> | null = null
let audio: UniApp.InnerAudioContext | null = null

onMounted(() => {
  topOffset.value = (uni.getWindowInfo().statusBarHeight || 0) + 12
  enableShareMenu()
  const seen = uni.getStorageSync('geogame_seen_opening')
  const interval = seen ? 250 : 2000

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

function enter() {
  uni.setStorageSync('geogame_seen_opening', '1')
  audio?.stop()
  uni.reLaunch({ url: '/pages/map/map' })
}
</script>

<style scoped>
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
  color: #93856d;
  border: 1px solid #4b4231;
  padding: 8rpx 24rpx;
  background: rgba(27, 21, 16, 0.85);
  z-index: 2;
}
.mute {
  position: fixed;
  top: 24rpx;
  left: 40rpx;
  font-size: 24rpx;
  color: #93856d;
  border: 1px solid #4b4231;
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
  color: #e9dfc9;
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
  color: #f5a33c;
  letter-spacing: 6rpx;
  font-size: 26rpx;
}
.line.final {
  color: #f9f2df;
  font-size: 36rpx;
}
.tap {
  font-family: 'Fusion Pixel 12px Proportional SC', monospace;
  position: fixed;
  bottom: 100rpx;
  font-size: 24rpx;
  color: #d8c9a8;
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
