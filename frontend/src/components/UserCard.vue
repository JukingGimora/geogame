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

      <!-- 被看过 vs 被认出来:前者是有人翻到了你的照片,后者是他真的猜到了地方。
           这句话是这张卡片上唯一说得出"你分享的东西起了什么作用"的地方 -->
      <text v-if="data && data.seen > 0" class="reach">
        {{ t('card.reach', { seen: data.seen, understood: data.understood }) }}
      </text>

      <view v-if="data && data.circles.length" class="lit">
        <text class="lit-title">{{ t('card.litTitle') }}</text>
        <text v-for="c in data.circles" :key="c" class="lit-chip">{{ c }}</text>
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
  countries: { name: string; flag: string }[]
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

const trail = computed(() => {
  const list = data.value?.countries ?? []
  if (!list.length) return ''
  // 国旗 + 国名:一排国旗比一排国名好认。认不出代码的就只显示名字
  const show = list.map((c) => (c.flag ? `${c.flag} ${c.name}` : c.name))
  // 国家多了就只列前六个,剩下的说个数
  const head = show.slice(0, 6).join('  ')
  return show.length > 6
    ? t('card.trailMore', { list: head, n: show.length - 6 })
    : t('card.trail', { list: head })
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
.reach {
  display: block;
  color: var(--ink-dim);
  font-size: 23rpx;
  line-height: 1.7;
  margin-top: 24rpx;
}
.lit {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10rpx;
  margin-top: 24rpx;
}
.lit-title {
  color: var(--ink-dim);
  font-size: 21rpx;
  margin-right: 4rpx;
}
.lit-chip {
  background: var(--card-alt);
  border: 1px solid var(--line);
  border-radius: 999rpx;
  color: var(--ink);
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
