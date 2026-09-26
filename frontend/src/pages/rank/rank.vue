<template>
  <view class="rank">
    <text class="g-title">{{ t('rank.title') }}</text>
    <text v-if="pulse" class="pulse">
      {{ t('rank.pulse', { active: pulse.active_today, photos: pulse.photos_live })
         + (pulse.photos_today > 0 ? t('rank.pulseNew', { n: pulse.photos_today }) : '') }}
    </text>
    <text v-if="pulse && pulse.my_seen_today > 0" class="pulse-me">
      {{ t('rank.seenToday', { n: pulse.my_seen_today }) }}
    </text>
    <view v-if="showProfileHint" class="hint-bar" @tap="goProfile">
      <text>{{ t('rank.profileHint') }}</text>
      <text class="hint-arrow">›</text>
    </view>
    <view class="tabs">
      <view class="tab" :class="{ active: board === 'streak' }" @tap="switchBoard('streak')">
        {{ t('rank.streak') }}
      </view>
      <view class="tab" :class="{ active: board === 'points' }" @tap="switchBoard('points')">
        {{ t('rank.points') }}
      </view>
    </view>

    <view v-if="data && data.top.length === 0" class="empty">{{ t('rank.empty') }}</view>
    <view v-for="row in data?.top ?? []" :key="row.rank" class="row" :class="{ me: row.is_me }" @tap="openCard(row.uid)">
      <text class="pos g-stamp">{{ row.rank }}</text>
      <view class="user-cell">
        <PixelAvatar :seed="`${row.nickname}#${row.uid}`" :size="56" />
        <text class="nick">{{ row.nickname }}{{ row.is_me ? t('rank.meSuffix') : '' }}</text>
      </view>
      <text class="val g-stamp">{{ row.value }}{{ board === 'points' ? t('rank.peopleUnit') : t('rank.roundUnit') }}</text>
    </view>

    <view v-if="data && data.me.rank && !inTop" class="row me footer-me">
      <text class="pos g-stamp">{{ data.me.rank }}</text>
      <view class="user-cell">
        <PixelAvatar :seed="meSeed" :size="56" />
        <text class="nick">{{ t('rank.me') }}</text>
      </view>
      <text class="val g-stamp">{{ data.me.value }}{{ board === 'points' ? t('rank.peopleUnit') : t('rank.roundUnit') }}</text>
    </view>
    <view v-if="data && data.me.rank === null" class="empty">{{ t('rank.notRanked') }}</view>

    <button class="g-btn primary play-btn" @tap="startRun()">{{ t('map.start') }}</button>
    <!-- #ifdef MP-WEIXIN -->
    <button class="g-btn share-btn" open-type="share" @tap="onShareTap">{{ t('rank.share') }}</button>
    <!-- #endif -->
    <UserCard :uid="cardUid" @close="cardUid = null" />
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
// #ifdef MP-WEIXIN
import { onShareAppMessage, onShareTimeline } from '@dcloudio/uni-app'
// #endif
import { api } from '../../api'
import { t } from '../../locale'
import { logEvent } from '../../lib/analytics'
import { enableShareMenu } from '../../lib/share'
import { useProfileHint } from '../../lib/profileHint'
import { startRun } from '../../lib/play'
import PixelAvatar from '../../components/PixelAvatar.vue'
import UserCard from '../../components/UserCard.vue'

type Board = 'streak' | 'points'

interface RankRow {
  rank: number
  uid: number
  nickname: string
  value: number
  is_me: boolean
}

const board = ref<Board>('streak')
const data = ref<{ top: RankRow[]; me: { rank: number | null; value: number | null; uid: number; nickname: string } } | null>(null)
const pulse = ref<{ active_today: number; photos_live: number; photos_today: number; my_seen_today: number } | null>(null)
const { show: showProfileHint, check: checkProfile, go: goProfile } = useProfileHint('rank')

const cardUid = ref<number | null>(null)

function openCard(uid: number) {
  cardUid.value = uid
}

const inTop = computed(() => data.value?.top.some((r) => r.is_me) ?? false)
// 榜单外那一行是"我",头像种子要跟榜内的我一致
const meSeed = computed(() => {
  const me = data.value?.me
  return me ? `${me.nickname}#${me.uid}` : ''
})

async function load() {
  try {
    const res = await api.leaderboard(board.value)
    data.value = res
    pulse.value = res?.pulse ?? null
  } catch {
    // 拉不到榜单就维持空态,别把未捕获的 rejection 抛到页面上
  }
}

function switchBoard(b: Board) {
  if (board.value === b) return
  // 大家到底在乎分数还是在乎被看见,只有这个点能回答
  logEvent('board_switch', '', undefined, { board: b })
  board.value = b
  data.value = null
  load()
}

onShow(() => {
  enableShareMenu()
  load()
  checkProfile()
})

// #ifdef MP-WEIXIN
function shareTitle(): string {
  const rank = data.value?.me.rank
  return rank ? t('rank.shareTitleRanked', { rank }) : t('rank.shareTitle')
}

function onShareTap() {
  logEvent('share_click', 'page', undefined, { location: 'rank' })
}

onShareAppMessage(() => ({ title: shareTitle(), path: '/pages/opening/opening?to=rank' }))

onShareTimeline(() => ({ title: shareTitle() }))
// #endif
</script>

<style scoped>
.rank {
  min-height: 100vh;
  background: var(--bg);
  padding: 90rpx 24rpx 40rpx;
  box-sizing: border-box;
}
.pulse {
  display: block;
  color: var(--ink-dim);
  font-size: 23rpx;
  margin-top: 8rpx;
}
.pulse-me {
  display: block;
  color: var(--good);
  font-size: 24rpx;
  margin-top: 8rpx;
}
.hint-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--card-alt);
  border: 1px solid var(--accent);
  border-radius: 8rpx;
  padding: 16rpx 20rpx;
  margin-top: 20rpx;
  color: var(--accent);
  font-size: 24rpx;
}
.hint-arrow {
  font-size: 28rpx;
  margin-left: 12rpx;
}
.tabs {
  display: flex;
  gap: 12rpx;
  margin: 24rpx 0;
}
.tab {
  flex: 1;
  text-align: center;
  padding: 16rpx 0;
  border: 1px solid var(--line-strong);
  border-radius: 8rpx;
  color: var(--ink-dim);
  font-size: 26rpx;
}
.tab.active {
  background: var(--accent);
  border-color: var(--accent);
  color: var(--on-accent);
}
.row {
  display: flex;
  align-items: center;
  gap: 20rpx;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 8rpx;
  padding: 20rpx 24rpx;
  margin-bottom: 12rpx;
}
.row.me {
  border-color: var(--accent);
}
.footer-me {
  margin-top: 28rpx;
}
.pos {
  width: 70rpx;
  font-size: 30rpx;
}
.user-cell {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 12rpx;
  min-width: 0;
}
.nick {
  flex: 1;
  color: var(--ink);
  font-size: 28rpx;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.val {
  font-size: 30rpx;
}
.empty {
  color: var(--ink-dim);
  text-align: center;
  margin-top: 120rpx;
  font-size: 28rpx;
}
.play-btn {
  margin-top: 40rpx;
}
.share-btn {
  margin-top: 16rpx;
}
</style>
