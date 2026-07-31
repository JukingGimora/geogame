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
      <view class="tab" :class="{ active: board === 'best_run' }" @tap="switchBoard('best_run')">
        {{ t('rank.bestRun') }}
      </view>
      <view class="tab" :class="{ active: board === 'points' }" @tap="switchBoard('points')">
        {{ t('rank.points') }}
      </view>
    </view>

    <view v-if="data && data.top.length === 0" class="empty">{{ t('rank.empty') }}</view>
    <view v-for="row in data?.top ?? []" :key="row.rank" class="row" :class="{ me: row.is_me }">
      <text class="pos g-stamp">{{ row.rank }}</text>
      <view class="user-cell">
        <image v-if="row.avatar_url" class="avatar" :src="row.avatar_url" mode="aspectFill" />
        <view v-else class="avatar placeholder" />
        <text class="nick">{{ row.nickname }}{{ row.is_me ? t('rank.meSuffix') : '' }}</text>
      </view>
      <text class="val g-stamp">{{ row.value }}{{ board === 'points' ? t('rank.peopleUnit') : '' }}</text>
    </view>

    <view v-if="data && data.me.rank && !inTop" class="row me footer-me">
      <text class="pos g-stamp">{{ data.me.rank }}</text>
      <view class="user-cell">
        <image v-if="data.me.avatar_url" class="avatar" :src="data.me.avatar_url" mode="aspectFill" />
        <view v-else class="avatar placeholder" />
        <text class="nick">{{ t('rank.me') }}</text>
      </view>
      <text class="val g-stamp">{{ data.me.value }}{{ board === 'points' ? t('rank.peopleUnit') : '' }}</text>
    </view>
    <view v-if="data && data.me.rank === null" class="empty">{{ t('rank.notRanked') }}</view>

    <!-- #ifdef MP-WEIXIN -->
    <button class="g-btn share-btn" open-type="share" @tap="onShareTap">{{ t('rank.share') }}</button>
    <!-- #endif -->
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

type Board = 'best_run' | 'points'

interface RankRow {
  rank: number
  nickname: string
  avatar_url?: string
  value: number
  is_me: boolean
}

const board = ref<Board>('best_run')
const data = ref<{ top: RankRow[]; me: { rank: number | null; value: number | null; avatar_url?: string } } | null>(null)
const pulse = ref<{ active_today: number; photos_live: number; photos_today: number; my_seen_today: number } | null>(null)
const { show: showProfileHint, check: checkProfile, go: goProfile } = useProfileHint('rank')

const inTop = computed(() => data.value?.top.some((r) => r.is_me) ?? false)

async function load() {
  const res = await api.leaderboard(board.value)
  data.value = res
  pulse.value = res.pulse
}

function switchBoard(b: Board) {
  if (board.value === b) return
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

onShareAppMessage(() => ({ title: shareTitle(), path: '/pages/opening/opening' }))

onShareTimeline(() => ({ title: shareTitle() }))
// #endif
</script>

<style scoped>
.rank {
  min-height: 100vh;
  background: #16110c;
  padding: 90rpx 24rpx 40rpx;
  box-sizing: border-box;
}
.pulse {
  display: block;
  color: #a2937b;
  font-size: 23rpx;
  margin-top: 8rpx;
}
.pulse-me {
  display: block;
  color: #8fd3a8;
  font-size: 24rpx;
  margin-top: 8rpx;
}
.hint-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #2a2110;
  border: 1px solid #f5a33c;
  border-radius: 8rpx;
  padding: 16rpx 20rpx;
  margin-top: 20rpx;
  color: #f5a33c;
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
  border: 1px solid #4b4231;
  border-radius: 8rpx;
  color: #a2937b;
  font-size: 26rpx;
}
.tab.active {
  background: #f5a33c;
  border-color: #f5a33c;
  color: #2a1c05;
}
.row {
  display: flex;
  align-items: center;
  gap: 20rpx;
  background: #211a13;
  border: 1px solid #322818;
  border-radius: 8rpx;
  padding: 20rpx 24rpx;
  margin-bottom: 12rpx;
}
.row.me {
  border-color: #f5a33c;
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
.avatar {
  width: 56rpx;
  height: 56rpx;
  border-radius: 50%;
  background: #16110c;
  border: 1px solid #4b4231;
  flex-shrink: 0;
}
.avatar.placeholder {
  background: linear-gradient(135deg, #4b4231, #16110c);
}
.nick {
  flex: 1;
  color: #e9dfc9;
  font-size: 28rpx;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.val {
  font-size: 30rpx;
}
.empty {
  color: #a2937b;
  text-align: center;
  margin-top: 120rpx;
  font-size: 28rpx;
}
.share-btn {
  margin-top: 40rpx;
}
</style>
