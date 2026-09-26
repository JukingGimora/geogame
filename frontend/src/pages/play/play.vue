<template>
  <view class="play" :style="{ paddingTop: `${topOffset + 48}px` }">
    <view v-if="run && current" class="stage">
      <view class="topbar">
        <view v-if="isRoam" class="dots">
          <view v-for="i in totalRounds" :key="i" class="dot" :class="{ on: i <= streak }" />
        </view>
        <view v-else class="lives" :class="{ hurt: hurting }">
          <text class="heart full">{{ heartsFull }}</text><text class="heart empty">{{ heartsEmpty }}</text>
          <text v-if="hurting" class="lost">−1</text>
        </view>
        <text class="mute" @tap="toggleMute">{{ muted ? '🔇' : '🔊' }}</text>
        <text class="streak g-stamp">
          {{ isRoam ? t('play.roamProgress', { n: Math.min(streak + 1, totalRounds), total: totalRounds }) : t('play.streak', { n: streak }) }}
        </text>
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

      <view v-if="phase === 'guess'" class="picker">
        <text class="pick-tip">{{ picked ? t('play.pickedTip') : t('play.pickTip') }}</text>
        <!-- #ifdef MP-WEIXIN -->
        <NativeMapPicker :height="pickMapHeight" :markers="pickMarkers" @pick="onPick" />
        <!-- #endif -->
        <!-- #ifndef MP-WEIXIN -->
        <WorldPicker :height="pickMapHeight" :interactive="true" :markers="pickMarkers" @pick="onPick" />
        <!-- #endif -->
        <button class="g-btn primary" :disabled="!picked || submitting" @tap="confirmGuess">
          {{ t('play.confirmFlag') }}
        </button>
      </view>

      <view v-if="phase === 'result' && result" class="result">
        <WorldPicker :height="260" :markers="resultMarkers" />
        <text v-if="result.place" class="place">{{ t('play.placeLabel', { place: result.place }) }}</text>
        <view class="earned">
          <text v-if="result.circle_lit" class="tag lit">{{ t('play.circleLit', { name: result.circle }) }}</text>
          <text v-else-if="result.country_match" class="tag ok">{{ t('play.countryMatch', { name: result.country }) }}</text>
        </view>
        <view class="stats">
          <view class="stat">
            <text class="stat-label">{{ t('play.distance') }}</text>
            <text class="stat-value">{{ result.distance_km }} km</text>
          </view>
          <view class="stat" v-if="!isRoam">
            <text class="stat-label">{{ t('play.livesLabel') }}</text>
            <text class="stat-value"><text class="heart full">{{ heartsFull }}</text><text class="heart empty">{{ heartsEmpty }}</text></text>
          </view>
          <view class="stat" v-else>
            <text class="stat-label">{{ t('play.score') }}</text>
            <text class="stat-value">{{ result.score }}</text>
          </view>
        </view>
        <view v-if="result.ai" class="ai-card">
          <view class="ai-head">
            <text class="ai-dist">{{ t('play.aiDistance', { n: Math.round(result.ai.distance_km) }) }}</text>
            <!-- 赢了才说一句,输了不提;AI 跑偏了要标出来,那是这局最有意思的地方 -->
            <text v-if="result.ai.beaten" class="ai-badge won">{{ t('play.beatAi') }}</text>
            <text v-else-if="result.ai.distance_km > 1000" class="ai-badge off">{{ t('play.aiWayOff') }}</text>
          </view>
          <text class="ai-reasoning">{{ result.ai.reasoning }}</text>
        </view>
        <view class="story-card" v-if="result.story">
          <text class="story-from">{{ t('play.storyFrom', { name: result.uploader.nickname }) }}</text>
          <text class="story-text">{{ result.story }}</text>
        </view>
        <view class="invite" @tap="goUpload">
          <text>{{ t('play.uploadInvite') }}</text>
          <text class="invite-arrow">›</text>
        </view>
        <!-- #ifdef MP-WEIXIN -->
        <button class="g-btn" open-type="share" @tap="onShareTap">{{ t('play.share') }}</button>
        <!-- #endif -->

        <button class="g-btn primary" @tap="nextRound">
          {{ result.ended ? t('play.finish') : t('play.next') }}
        </button>
      </view>
    </view>

    <view v-if="finished && run" class="finale">
      <template v-if="isRoam">
        <text class="finale-label">{{ t('play.endRoam') }}</text>
        <text class="finale-score">{{ t('play.roamAvg', { n: roamAvg }) }}</text>
        <text class="finale-sub">{{ t('play.roamBest', { n: roamBest }) }}</text>
      </template>
      <template v-else>
        <text class="finale-label">{{ endedReason === 'pool_empty' ? t('play.endPool') : t('play.endLives') }}</text>
        <text class="finale-score">{{ t('play.streak', { n: streak }) }}</text>
        <text class="finale-sub">{{ run.rank ? t('play.rank', { n: run.rank }) : t('play.totalScore', { n: run.total_score }) }}</text>
      </template>
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
import { onLoad, onShareAppMessage, onShareTimeline } from '@dcloudio/uni-app'
import WorldPicker from '../../components/WorldPicker.vue'
// #ifdef MP-WEIXIN
import NativeMapPicker from '../../components/NativeMapPicker.vue'
// #endif
import { api, BASE_URL } from '../../api'
import { t, tList } from '../../locale'
import { addFogPoint } from '../../lib/fogStore'
import { logEvent } from '../../lib/analytics'
import { errorMessage } from '../../lib/errors'
import { enableShareMenu } from '../../lib/share'
import { useProfileHint } from '../../lib/profileHint'
import type { LngLat } from '../../lib/geo'
import type { MapMarker } from '../../lib/mapRender'

const hintLabels = tList('play.hints')
const hintCosts = tList('play.hintCost')

const run = ref<any>(null)
const phase = ref<'guess' | 'result'>('guess')
const submitting = ref(false)
const endedReason = ref<string | null>(null)
const topOffset = ref(0)
const picked = ref<LngLat | null>(null)
const result = ref<any>(null)
const unlockedContents = ref<{ level: number; content: string }[]>([])
const finished = ref(false)
const { show: showProfileHint, check: checkProfile, go: goProfile } = useProfileHint('finale')

// 漫游结算报"平均差多少、最准的一关":一局三关,这两个数就够说明今天手感如何
const roamDistances = computed<number[]>(() =>
  (run.value?.rounds ?? [])
    .filter((r: any) => r.finished && typeof r.distance_km === 'number')
    .map((r: any) => r.distance_km),
)
const roamAvg = computed(() =>
  roamDistances.value.length
    ? Math.round(roamDistances.value.reduce((a, b) => a + b, 0) / roamDistances.value.length)
    : 0,
)
const roamBest = computed(() =>
  roamDistances.value.length ? Math.round(Math.min(...roamDistances.value)) : 0,
)
const pickMapHeight = Math.round(uni.getWindowInfo().windowHeight * 0.35)
let recapRoundId: number | null = null
let recapShownAt = 0

const current = computed(() => run.value?.rounds.find((r: any) => !r.finished))
const streak = computed(() => result.value?.streak ?? run.value?.streak ?? 0)
const isRoam = computed(() => (result.value?.mode ?? run.value?.mode) === 'roam')
const totalRounds = computed(() => run.value?.total_rounds ?? 3)
const livesLeft = computed(() => result.value?.lives_left ?? run.value?.lives_left ?? 3)
// ♥♥♡ 一眼就懂,也比"还剩2条命"更有紧张感。分成两段是为了让满的是红的、空的是灰的
const hurting = ref(false)
const muted = ref(!!uni.getStorageSync('geogame_muted'))

function toggleMute() {
  muted.value = !muted.value
  uni.setStorageSync('geogame_muted', muted.value ? '1' : '')
}
let audio: UniApp.InnerAudioContext | null = null

/** 掉血要看得见也听得见:只震动的话,玩家常常没意识到自己少了一条命 */
function playHurt() {
  hurting.value = true
  setTimeout(() => (hurting.value = false), 700)
  uni.vibrateShort({ fail: () => {} })
  if (muted.value) return
  try {
    if (!audio) {
      audio = uni.createInnerAudioContext()
      audio.src = '/static/audio/life-lost.mp3'
      audio.volume = 0.5
    }
    audio.stop()
    audio.play()
  } catch {
    // 有的机型不给放,不值得为它打断一局
  }
}

const heartsFull = computed(() => '♥'.repeat(livesLeft.value))
const heartsEmpty = computed(() => '♡'.repeat(Math.max(0, 3 - livesLeft.value)))
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
  topOffset.value = (uni.getWindowInfo().statusBarHeight || 0) + 12
  enableShareMenu()
  const runId = Number(query?.runId)
  try {
    run.value = await api.getRun(runId)
    logRoundStart()
  } catch (e: unknown) {
    // 拿不到这一局就没有任何东西可渲染,页面会是全黑的。宁可说清楚再退回地图
    uni.showToast({ title: errorMessage(e), icon: 'none' })
    setTimeout(() => uni.reLaunch({ url: '/pages/map/map' }), 1500)
  }
})

/** 每一关展示时打一次。没有它就只有"开始"和"完成"两头,中间全黑,答不了"卡在第几关"。 */
function logRoundStart() {
  if (current.value) {
    logEvent('round_start', 'round', current.value.round_id, { order: current.value.order + 1 })
  }
}

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
  } catch (e: unknown) {
    uni.showToast({ title: errorMessage(e), icon: 'none' })
  }
}

function onPick(p: LngLat) {
  // 第一次落点单独记一次:开局到插旗之间流失最狠,不打这个点就看不见人死在哪
  if (!picked.value && current.value) logEvent('pick_first', 'round', current.value.round_id)
  picked.value = p
}

async function confirmGuess() {
  if (!current.value || !picked.value || submitting.value) return
  submitting.value = true
  recapRoundId = current.value.round_id
  logEvent('guess_submit', 'round', current.value.round_id)
  try {
    result.value = await api.guess(current.value.round_id, picked.value.lat, picked.value.lng)
  } catch (e: unknown) {
    uni.showToast({ title: errorMessage(e), icon: 'none' })
    submitting.value = false
    return
  }
  submitting.value = false
  const before = run.value?.lives_left ?? 3
  if ((result.value?.lives_left ?? before) < before) playHurt()
  else uni.vibrateShort({ fail: () => {} })
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
  const ended = result.value?.ended ?? null
  run.value = await api.getRun(runId)
  result.value = null
  picked.value = null
  unlockedContents.value = []
  phase.value = 'guess'
  if (ended || run.value.status !== 'playing') {
    endedReason.value = ended
    finished.value = true
    logEvent('run_finished', 'run', runId, { streak: run.value.streak, reason: ended })
    checkProfile()
    return
  }
  logRoundStart()
}

function backHome() {
  uni.reLaunch({ url: '/pages/map/map' })
}

function goUpload() {
  logEvent('upload_invite_click', 'round', recapRoundId ?? undefined)
  uni.navigateTo({ url: '/pages/upload/upload' })
}

function onShareTap() {
  logEvent('share_click', 'round', recapRoundId ?? undefined)
}

function shareTitle(): string {
  return result.value?.ai?.beaten
    ? t('play.shareTitleWon', { score: result.value.score })
    : t('play.shareTitleDefault', { score: result.value?.score ?? 0 })
}

function shareImage(): string | undefined {
  return current.value ? photoUrl(current.value.photo_url) : undefined
}

onShareAppMessage(() => ({
  title: shareTitle(),
  path: '/pages/opening/opening',
  imageUrl: shareImage(),
}))

onShareTimeline(() => ({
  title: shareTitle(),
  imageUrl: shareImage(),
}))
</script>

<style scoped>
.dots {
  display: flex;
  gap: 10rpx;
  align-items: center;
}
.dot {
  width: 16rpx;
  height: 16rpx;
  border-radius: 50%;
  background: var(--line-strong);
}
.dot.on {
  background: var(--accent);
}
.earned {
  display: flex;
  gap: 12rpx;
  margin-top: 12rpx;
}
.tag {
  font-size: 23rpx;
  border-radius: 999rpx;
  padding: 6rpx 16rpx;
}
.tag.lit {
  background: var(--accent);
  color: var(--on-accent);
}
.tag.ok {
  color: var(--good);
  border: 1px solid var(--good);
}

.lives {
  display: flex;
  align-items: center;
  position: relative;
}

.lives.hurt {
  animation: shake 0.45s ease-in-out;
}

.lives.hurt .heart.full {
  animation: dim 0.45s ease-out;
}

.lost {
  position: absolute;
  left: 100%;
  margin-left: 10rpx;
  color: var(--warn);
  font-size: 26rpx;
  animation: rise 0.7s ease-out forwards;
}

@keyframes shake {
  0%, 100% { transform: translateX(0); }
  20% { transform: translateX(-6rpx); }
  45% { transform: translateX(5rpx); }
  70% { transform: translateX(-3rpx); }
}

@keyframes dim {
  0% { opacity: 1; transform: scale(1.25); }
  100% { opacity: 1; transform: scale(1); }
}

@keyframes rise {
  0% { opacity: 1; transform: translateY(0); }
  100% { opacity: 0; transform: translateY(-28rpx); }
}
.heart {
  font-size: 32rpx;
  letter-spacing: 4rpx;
}
.heart.full {
  color: var(--warn);
}
.heart.empty {
  color: var(--ink-faint);
}

.place {
  display: block;
  color: var(--ink-dim);
  font-size: 24rpx;
  margin-top: 12rpx;
}

.play {
  min-height: 100vh;
  background: var(--bg);
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
  color: var(--ink-dim);
  font-size: 24rpx;
}
.photo {
  width: 100%;
  border-radius: 8rpx;
  background: var(--card);
  border: 1px solid var(--line);
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
  border: 1px solid var(--line-strong);
  color: var(--ink-dim);
  font-size: 22rpx;
  padding: 8rpx 14rpx;
  border-radius: 6rpx;
}
.hint-chip.used {
  opacity: 0.4;
}
.cost {
  color: var(--accent);
  font-size: 20rpx;
}
.hint-content {
  width: 100%;
  color: var(--ink);
  font-size: 24rpx;
  background: var(--card);
  border-left: 4rpx solid var(--accent);
  padding: 12rpx 16rpx;
  border-radius: 0;
}
.g-btn {
  width: 100%;
}
.picker {
  margin-top: 16rpx;
  border: 1px solid var(--line);
  border-radius: 12rpx;
  padding: 6rpx;
  background: var(--bg-sunken);
}
.row {
  display: flex;
  gap: 16rpx;
  margin-top: 16rpx;
}
.row .g-btn {
  flex: 1;
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
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 8rpx;
  padding: 20rpx;
  display: flex;
  flex-direction: column;
  gap: 8rpx;
}
.stat-label {
  color: var(--ink-dim);
  font-size: 24rpx;
}
.stat-value {
  font-family: 'Fusion Pixel 12px Proportional SC', monospace;
  color: var(--accent);
  font-size: 48rpx;
}
.ai-card,
.story-card {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 8rpx;
  padding: 22rpx;
  display: flex;
  flex-direction: column;
  gap: 12rpx;
}
.ai-head {
  display: flex;
  justify-content: space-between;
  color: var(--ink-dim);
  font-size: 26rpx;
}
.ai-dist {
  color: var(--ink-dim);
  font-size: 24rpx;
}

.ai-badge.off {
  color: var(--warn);
}

.ai-badge {
  font-family: 'Fusion Pixel 12px Proportional SC', monospace;
  color: var(--warn);
}
.ai-badge.won {
  color: var(--good);
}
.ai-reasoning {
  color: #cabfa8;
  font-size: 26rpx;
  line-height: 1.7;
}
.invite {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border: 1px dashed var(--line-strong);
  border-radius: 8rpx;
  padding: 20rpx 24rpx;
  color: var(--ink-dim);
  font-size: 25rpx;
}
.invite-arrow {
  color: var(--accent);
  font-size: 30rpx;
}
.story-card {
  border-left: 4rpx solid var(--accent);
  border-radius: 0 8rpx 8rpx 0;
}
.story-from {
  color: var(--accent);
  font-size: 24rpx;
  font-family: 'Fusion Pixel 12px Proportional SC', monospace;
}
.story-text {
  color: var(--ink);
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
  color: var(--ink-dim);
  font-size: 28rpx;
}
.finale-score {
  font-family: 'Fusion Pixel 12px Proportional SC', monospace;
  color: var(--accent);
  font-size: 110rpx;
}
.hint-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--card-alt);
  border: 1px solid var(--accent);
  border-radius: 8rpx;
  padding: 16rpx 20rpx;
  color: var(--accent);
  font-size: 24rpx;
  width: 100%;
  box-sizing: border-box;
}
.hint-arrow {
  font-size: 28rpx;
  margin-left: 12rpx;
}
</style>
