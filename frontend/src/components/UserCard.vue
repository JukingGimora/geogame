<template>
  <view v-if="open" class="mask" @tap="close">
    <view class="card" @tap.stop>
      <view class="head">
        <PixelAvatar :seed="seed" :size="96" />
        <view class="who">
          <text class="nick">{{ data?.nickname || '…' }}</text>
          <text class="since">{{ data ? t('card.since', { n: data.joined_days }) : '' }}</text>
        </view>
      </view>

      <view v-if="data" class="nums">
        <view v-for="n in nums" :key="n.label" class="num">
          <text class="num-value g-stamp">{{ n.value }}</text>
          <text class="num-label">{{ n.label }}</text>
        </view>
      </view>

      <view v-if="badges.length" class="badges">
        <text v-for="b in badges" :key="b" class="badge">{{ b }}</text>
      </view>

      <text v-if="data && trail" class="trail">{{ trail }}</text>
      <text v-if="failed" class="failed">{{ t('card.failed') }}</text>

      <text class="close" @tap="close">{{ t('card.close') }}</text>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api } from '../api'
import { t } from '../locale'
import { logEvent } from '../lib/analytics'
import PixelAvatar from './PixelAvatar.vue'

interface Profile {
  id: number
  nickname: string
  joined_days: number
  photos: number
  seen: number
  understood: number
  rounds_played: number
  best_streak: number
  circles: string[]
  countries: string[]
}

const props = defineProps<{ uid: number | null }>()

const open = computed(() => props.uid !== null)
const data = ref<Profile | null>(null)
const failed = ref(false)
const emit = defineEmits<{ (e: 'close'): void }>()

const seed = computed(() => (data.value ? `${data.value.nickname}#${data.value.id}` : ''))

// 四个数字:传了多少、被多少人看过、认出来过几个国家、最长连关。
// 「被看过」是这个游戏里唯一别人给你的东西,放在最显眼的第二格
const nums = computed(() => {
  const d = data.value
  if (!d) return []
  return [
    { value: d.photos, label: t('card.photos') },
    { value: d.seen, label: t('card.seen') },
    { value: d.countries.length, label: t('card.countries') },
    { value: d.best_streak, label: t('card.streak') },
  ]
})

// 成就不写成一串 if:每个指标一串台阶,只显示已经踩到的最高那级。
// 想加一条就在这张表上加个数字
const LADDERS: { metric: keyof Profile; steps: number[] }[] = [
  { metric: 'photos', steps: [1, 10, 50] },
  { metric: 'seen', steps: [10, 50, 200] },
  { metric: 'best_streak', steps: [10, 20, 30] },
  { metric: 'circles', steps: [3, 6, 9] },
]

const badges = computed(() => {
  const d = data.value
  if (!d) return []
  const out: string[] = []
  for (const { metric, steps } of LADDERS) {
    const raw = d[metric]
    const value = Array.isArray(raw) ? raw.length : Number(raw)
    const reached = steps.filter((s) => value >= s).pop()
    if (reached) out.push(t(`card.badge.${metric}`, { n: reached }))
  }
  return out
})

const trail = computed(() => {
  const list = data.value?.countries ?? []
  if (!list.length) return ''
  // 国家多了就只列前六个,剩下的说个数
  const head = list.slice(0, 6).join('、')
  return list.length > 6 ? t('card.trailMore', { list: head, n: list.length - 6 }) : t('card.trail', { list: head })
})

watch(
  () => props.uid,
  async (uid) => {
    data.value = null
    failed.value = false
    if (uid === null) return
    logEvent('profile_open', 'user', uid)
    try {
      data.value = await api.userProfile(uid)
    } catch {
      failed.value = true
    }
  },
  { immediate: true },
)

function close() {
  emit('close')
}
</script>

<style scoped>
.mask {
  position: fixed;
  left: 0;
  top: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.66);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 60;
  padding: 0 48rpx;
}
.card {
  width: 100%;
  background: var(--card);
  border: 1px solid var(--line-strong);
  border-radius: 12rpx;
  padding: 36rpx 32rpx 24rpx;
  box-sizing: border-box;
}
.head {
  display: flex;
  align-items: center;
  gap: 20rpx;
}
.who {
  flex: 1;
  min-width: 0;
}
.nick {
  display: block;
  color: var(--ink);
  font-size: 34rpx;
}
.since {
  display: block;
  color: var(--ink-dim);
  font-size: 22rpx;
  margin-top: 6rpx;
}
.nums {
  display: flex;
  margin-top: 32rpx;
}
.num {
  flex: 1;
  text-align: center;
}
.num-value {
  display: block;
  font-size: 38rpx;
}
.num-label {
  display: block;
  color: var(--ink-dim);
  font-size: 21rpx;
  margin-top: 6rpx;
}
.badges {
  display: flex;
  flex-wrap: wrap;
  gap: 10rpx;
  margin-top: 28rpx;
}
.badge {
  border: 1px solid var(--accent);
  border-radius: 999rpx;
  color: var(--accent);
  font-size: 21rpx;
  padding: 6rpx 16rpx;
}
.trail {
  display: block;
  color: var(--ink-dim);
  font-size: 23rpx;
  line-height: 1.7;
  margin-top: 24rpx;
}
.failed {
  display: block;
  color: var(--ink-dim);
  font-size: 24rpx;
  margin-top: 24rpx;
}
.close {
  display: block;
  text-align: center;
  color: var(--ink-dim);
  font-size: 25rpx;
  margin-top: 28rpx;
  padding: 12rpx 0;
}
</style>
