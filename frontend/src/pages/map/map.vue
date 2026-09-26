<template>
  <view class="home" :style="{ paddingTop: `${topOffset + 48}px` }">
    <view class="header">
      <text class="g-title">{{ t('map.title') }}</text>
      <text class="sub">{{ subtitle }}</text>
    </view>

    <view class="map-bleed">
      <WorldMap :height="mapHeight" :circles="circles" :selected="activeName" @pick="onPick" />
    </view>

    <view class="legend">
      <view
        v-for="c in circles"
        :key="c.name"
        class="chip"
        :class="{ on: activeName === c.name, dim: c.photos === 0 }"
        @tap="onPick(c.name)"
      >
        <view class="dot" :style="{ background: colorOf(c.name), opacity: c.lit ? 1 : 0.45 }" />
        <text class="chip-name">{{ c.name }}</text>
        <text class="chip-count">{{ c.photos }}</text>
      </view>
    </view>

    <view class="picked" v-if="active">
      <view class="picked-head">
        <text class="picked-name px-font">{{ active.name }}</text>
        <text class="picked-count">
          {{ active.photos > 0 ? t('map.circlePhotos', { n: active.photos }) : t('map.circleEmpty') }}
        </text>
      </view>
      <text class="picked-desc">{{ active.desc }}</text>
    </view>
    <text v-else class="picked-hint">{{ t('map.mapHint') }}</text>

    <button class="g-btn primary start" @tap="onStart">
      {{ active && active.photos > 0 ? t('map.startCircle', { name: active.name }) : t('map.roam') }}
    </button>
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
import WorldMap from '../../components/WorldMap.vue'
import { api } from '../../api'
import { t } from '../../locale'
import { enableShareMenu } from '../../lib/share'
import { startRun } from '../../lib/play'
import { logEvent } from '../../lib/analytics'
import { CIRCLE_COLORS } from '../../lib/theme'

interface Circle {
  name: string
  desc: string
  photos: number
  played: number
  lit: boolean
  lit_count?: number
}

const circles = ref<Circle[]>([])
const activeName = ref('')
const topOffset = ref(0)
// 世界地图的宽高比约 2.5:高度按宽度算,画面才不会上下留一大片空
const windowWidth = uni.getWindowInfo().windowWidth
// 通栏:地图本来就是宽扁的,左右再留白只会更窄
const mapHeight = Math.round(windowWidth / 2.0)

function colorOf(name: string): string {
  return CIRCLE_COLORS[name] ?? '#888'
}

const active = computed(() => circles.value.find((c) => c.name === activeName.value) || null)

// 点亮了几个圈,是玩家在这游戏里唯一一直累积的东西
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
    // 拉不到就让地图空着,至少"开始一轮"还能点
  }
}

function onPick(name: string) {
  activeName.value = name
  const c = circles.value.find((x) => x.name === name)
  logEvent('circle_click', 'circle', undefined, { name, photos: c?.photos ?? 0, lit: c?.lit ?? false })
}

function onStart() {
  const c = active.value
  if (c && c.photos === 0) {
    uni.showToast({ title: t('map.circleEmptyHint'), icon: 'none', duration: 2200 })
    return
  }
  logEvent('start_click', 'page', undefined, { from: 'home', circle: c?.name ?? '' })
  // 选了圈就是认真打(三条命);没选就是随便走走(三关,不会死)
  startRun(undefined, c?.name, { mode: c ? 'serious' : 'roam' })
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
  padding: 0 28rpx 32rpx;
  box-sizing: border-box;
}

.header {
  margin-bottom: 20rpx;
}

.map-bleed {
  margin: 0 -28rpx;
}

.legend {
  display: flex;
  flex-wrap: wrap;
  gap: 12rpx;
  margin-top: 22rpx;
}

.chip {
  display: flex;
  align-items: center;
  gap: 10rpx;
  background: var(--card);
  border-radius: 999rpx;
  padding: 12rpx 20rpx;
}

.chip.on {
  background: var(--card-alt);
}

.chip.dim {
  opacity: 0.45;
}

.dot {
  width: 16rpx;
  height: 16rpx;
  border-radius: 50%;
}

.chip-name {
  color: var(--ink-dim);
  font-size: 24rpx;
}

.chip.on .chip-name {
  color: var(--ink);
}

.chip-count {
  color: var(--ink-faint);
  font-size: 22rpx;
}

.sub {
  display: block;
  color: var(--ink-faint);
  font-size: 23rpx;
  margin-top: 10rpx;
}

.picked {
  min-height: 108rpx;
  margin-top: 24rpx;
}

.picked-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
}

.picked-name {
  color: var(--accent);
  font-size: 32rpx;
}

.picked-count {
  color: var(--ink-faint);
  font-size: 22rpx;
}

.picked-desc {
  display: block;
  color: var(--ink-dim);
  font-size: 24rpx;
  line-height: 1.7;
  margin-top: 8rpx;
}

.picked-hint {
  display: block;
  min-height: 108rpx;
  margin-top: 24rpx;
  color: var(--ink-faint);
  font-size: 23rpx;
}

.start {
  width: 100%;
  margin-top: 8rpx;
}

.row {
  display: flex;
  gap: 14rpx;
  margin-top: 16rpx;
}

.row .g-btn {
  flex: 1;
  min-width: 0;
}
</style>
