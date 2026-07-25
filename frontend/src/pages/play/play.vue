<template>
  <view class="play" :style="{ paddingTop: `${topOffset + 48}px` }">
    <view v-if="run && current" class="stage">
      <view class="topbar">
        <text class="round-label px-font">{{ t('play.round', { n: current.order + 1 }) }} / {{ run.rounds.length }}</text>
        <text class="g-stamp" v-if="run.total_score">{{ run.total_score }}</text>
      </view>

      <image class="photo" :src="photoUrl(current.photo_url)" mode="widthFix" @tap="previewPhoto" />

      <view v-if="phase !== 'result'" class="hints">
        <view
          v-for="(label, i) in hintLabels"
          :key="i"
          class="hint-chip"
          :class="{ used: unlockedLevels.includes(i + 1) }"
          @tap="unlockHint(i + 1)"
        >
          {{ label }} <text class="cost">{{ hintCosts[i] }}</text>
        </view>
        <view v-for="h in unlockedContents" :key="h.level" class="hint-content">{{ h.content }}</view>
      </view>

      <button v-if="phase === 'view'" class="g-btn primary" @tap="phase = 'pick'">{{ t('play.placeFlag') }}</button>

      <view v-if="phase === 'pick'" class="picker">
        <!-- #ifdef MP-WEIXIN -->
        <NativeMapPicker :height="pickMapHeight" :markers="pickMarkers" @pick="onPick" />
        <!-- #endif -->
        <!-- #ifndef MP-WEIXIN -->
        <ChinaMap :height="pickMapHeight" :interactive="true" :markers="pickMarkers" @pick="onPick" />
        <!-- #endif -->
        <view class="row">
          <button class="g-btn" @tap="phase = 'view'">{{ t('play.cancelFlag') }}</button>
          <button class="g-btn primary" :disabled="!picked" @tap="confirmGuess">{{ t('play.confirmFlag') }}</button>
        </view>
      </view>

      <view v-if="phase === 'result' && result" class="result">
        <ChinaMap :height="260" :markers="resultMarkers" />
        <view class="stats">
          <view class="stat">
            <text class="stat-label">{{ t('play.distance') }}</text>
            <text class="stat-value">{{ result.distance_km }} km</text>
          </view>
          <view class="stat">
            <text class="stat-label">{{ t('play.score') }}</text>
            <text class="stat-value">{{ result.score }}</text>
          </view>
        </view>
        <view v-if="result.ai" class="ai-card">
          <view class="ai-head">
            <text>{{ t('play.aiThinks') }}</text>
            <text class="ai-badge" :class="{ won: result.ai.beaten }">
              {{ result.ai.beaten ? t('play.beatAi') : t('play.lostAi') }} · AI {{ result.ai.score }}
            </text>
          </view>
          <text class="ai-reasoning">{{ result.ai.reasoning }}</text>
        </view>
        <view class="story-card" v-if="result.story">
          <text class="story-from">{{ t('play.storyFrom', { name: result.uploader.nickname }) }}</text>
          <text class="story-text">{{ result.story }}</text>
        </view>
        <!-- #ifdef MP-WEIXIN -->
        <button class="g-btn" open-type="share" @tap="onShareTap">{{ t('play.share') }}</button>
        <!-- #endif -->

        <button class="g-btn primary" @tap="nextRound">
          {{ isLastRound ? t('play.finish') : t('play.next') }}
        </button>
      </view>
    </view>

    <view v-if="finished && run" class="finale">
      <text class="finale-label">{{ t('play.total') }}</text>
      <text class="finale-score">{{ run.total_score }}</text>
      <view v-if="showProfileHint" class="hint-bar" @tap="goProfile">
        <text>{{ t('rank.profileHint') }}</text>
        <text class="hint-arrow">›</text>
      </view>
      <button class="g-btn primary" @tap="backHome">{{ t('play.backHome') }}</button>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onLoad, onShareAppMessage } from '@dcloudio/uni-app'
import ChinaMap from '../../components/ChinaMap.vue'
// #ifdef MP-WEIXIN
import NativeMapPicker from '../../components/NativeMapPicker.vue'
// #endif
import { api, BASE_URL } from '../../api'
import { t, tList } from '../../locale'
import { addFogPoint } from '../../lib/fogStore'
import { logEvent } from '../../lib/analytics'
import { useProfileHint } from '../../lib/profileHint'
import type { LngLat } from '../../lib/geo'
import type { MapMarker } from '../../lib/mapRender'

const hintLabels = tList('play.hints')
const hintCosts = tList('play.hintCost')

const run = ref<any>(null)
const phase = ref<'view' | 'pick' | 'result'>('view')
const topOffset = ref(0)
const picked = ref<LngLat | null>(null)
const result = ref<any>(null)
const unlockedContents = ref<{ level: number; content: string }[]>([])
const finished = ref(false)
const { show: showProfileHint, check: checkProfile, go: goProfile } = useProfileHint('finale')
const pickMapHeight = Math.round(uni.getSystemInfoSync().windowHeight * 0.35)
let recapRoundId: number | null = null
let recapShownAt = 0

const current = computed(() => run.value?.rounds.find((r: any) => !r.finished))
const isLastRound = computed(() => run.value && run.value.rounds.filter((r: any) => !r.finished).length <= 1)
const unlockedLevels = computed(() => unlockedContents.value.map((h) => h.level))

const pickMarkers = computed<MapMarker[]>(() =>
  picked.value ? [{ ...picked.value, kind: 'pick' }] : [],
)
const resultMarkers = computed<MapMarker[]>(() => {
  if (!result.value || !picked.value) return []
  const m: MapMarker[] = [
    { ...picked.value, kind: 'guess' },
    { lat: result.value.truth.lat, lng: result.value.truth.lng, kind: 'truth' },
  ]
  if (result.value.ai) m.push({ lat: result.value.ai.lat, lng: result.value.ai.lng, kind: 'ai' })
  return m
})

onLoad(async (query) => {
  topOffset.value = (uni.getSystemInfoSync().statusBarHeight || 0) + 12
  const runId = Number(query?.runId)
  run.value = await api.getRun(runId)
})

function photoUrl(path: string): string {
  return path.startsWith('http') ? path : BASE_URL + path
}

function previewPhoto() {
  if (current.value) uni.previewImage({ urls: [photoUrl(current.value.photo_url)] })
}

async function unlockHint(level: number) {
  if (!current.value || unlockedLevels.value.includes(level) || phase.value === 'result') return
  try {
    const h = await api.unlockHint(current.value.round_id, level)
    unlockedContents.value.push({ level, content: h.content })
  } catch {
    uni.showToast({ title: '该提示不可用', icon: 'none' })
  }
}

function onPick(p: LngLat) {
  picked.value = p
}

async function confirmGuess() {
  if (!current.value || !picked.value) return
  recapRoundId = current.value.round_id
  result.value = await api.guess(current.value.round_id, picked.value.lat, picked.value.lng)
  phase.value = 'result'
  recapShownAt = Date.now()
  addFogPoint({
    lat: result.value.truth.lat,
    lng: result.value.truth.lng,
    radiusKm: Math.max(40, 300 - result.value.score / 25),
  })
}

function logRecapDwell() {
  if (!recapRoundId || !recapShownAt) return
  logEvent('round_recap_view', 'round', recapRoundId, { dwell_ms: Date.now() - recapShownAt })
  recapRoundId = null
  recapShownAt = 0
}

async function nextRound() {
  logRecapDwell()
  const runId = run.value.run_id
  run.value = await api.getRun(runId)
  result.value = null
  picked.value = null
  unlockedContents.value = []
  phase.value = 'view'
  if (!current.value) {
    finished.value = true
    logEvent('run_finished', 'run', runId, { total_score: run.value.total_score })
    checkProfile()
  }
}

function backHome() {
  uni.reLaunch({ url: '/pages/map/map' })
}

function onShareTap() {
  logEvent('share_click', 'round', recapRoundId ?? undefined)
}

onShareAppMessage(() => ({
  title: result.value?.ai?.beaten
    ? t('play.shareTitleWon', { score: result.value.score })
    : t('play.shareTitleDefault', { score: result.value?.score ?? 0 }),
  path: '/pages/map/map',
}))
</script>

<style scoped>
.play {
  min-height: 100vh;
  background: #16110c;
  padding: 24rpx 24rpx 28rpx;
  box-sizing: border-box;
}
.topbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12rpx;
}
.round-label {
  color: #a2937b;
  font-size: 24rpx;
}
.photo {
  width: 100%;
  border-radius: 8rpx;
  background: #211a13;
  border: 1px solid #322818;
  box-sizing: border-box;
}
.hints {
  display: flex;
  flex-wrap: wrap;
  gap: 8rpx;
  margin: 12rpx 0;
}
.hint-chip {
  background: transparent;
  border: 1px solid #4b4231;
  color: #d8c9a8;
  font-size: 22rpx;
  padding: 8rpx 14rpx;
  border-radius: 6rpx;
}
.hint-chip.used {
  opacity: 0.4;
}
.cost {
  color: #f5a33c;
  font-size: 20rpx;
}
.hint-content {
  width: 100%;
  color: #e9dfc9;
  font-size: 24rpx;
  background: #211a13;
  border-left: 4rpx solid #f5a33c;
  padding: 12rpx 16rpx;
  border-radius: 0;
}
.g-btn {
  width: 100%;
}
.picker {
  margin-top: 16rpx;
  border: 1px solid #322818;
  border-radius: 12rpx;
  padding: 6rpx;
  background: #0f0c08;
}
.row {
  display: flex;
  gap: 16rpx;
  margin-top: 16rpx;
}
.result {
  margin-top: 20rpx;
  display: flex;
  flex-direction: column;
  gap: 20rpx;
}
.stats {
  display: flex;
  gap: 16rpx;
}
.stat {
  flex: 1;
  background: #211a13;
  border: 1px solid #322818;
  border-radius: 8rpx;
  padding: 20rpx;
  display: flex;
  flex-direction: column;
  gap: 8rpx;
}
.stat-label {
  color: #a2937b;
  font-size: 24rpx;
}
.stat-value {
  font-family: 'Fusion Pixel 12px Proportional SC', monospace;
  color: #f5a33c;
  font-size: 48rpx;
}
.ai-card,
.story-card {
  background: #211a13;
  border: 1px solid #322818;
  border-radius: 8rpx;
  padding: 22rpx;
  display: flex;
  flex-direction: column;
  gap: 12rpx;
}
.ai-head {
  display: flex;
  justify-content: space-between;
  color: #a2937b;
  font-size: 26rpx;
}
.ai-badge {
  font-family: 'Fusion Pixel 12px Proportional SC', monospace;
  color: #e08484;
}
.ai-badge.won {
  color: #6fe0a8;
}
.ai-reasoning {
  color: #cabfa8;
  font-size: 26rpx;
  line-height: 1.7;
}
.story-card {
  border-left: 4rpx solid #f5a33c;
  border-radius: 0 8rpx 8rpx 0;
}
.story-from {
  color: #f5a33c;
  font-size: 24rpx;
  font-family: 'Fusion Pixel 12px Proportional SC', monospace;
}
.story-text {
  color: #e9dfc9;
  font-size: 28rpx;
  line-height: 1.9;
  font-family: Georgia, 'Songti SC', 'SimSun', serif;
}
.finale {
  min-height: 70vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 24rpx;
}
.finale-label {
  color: #a2937b;
  font-size: 28rpx;
}
.finale-score {
  font-family: 'Fusion Pixel 12px Proportional SC', monospace;
  color: #f5a33c;
  font-size: 110rpx;
}
.hint-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #2a2110;
  border: 1px solid #f5a33c;
  border-radius: 8rpx;
  padding: 16rpx 20rpx;
  color: #f5a33c;
  font-size: 24rpx;
  width: 100%;
  box-sizing: border-box;
}
.hint-arrow {
  font-size: 28rpx;
  margin-left: 12rpx;
}
</style>
