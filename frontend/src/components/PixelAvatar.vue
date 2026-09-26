<template>
  <view class="pixel-avatar" :style="boxStyle">
    <text class="px-font initials" :style="textStyle">{{ initials }}</text>
  </view>
</template>

<script setup lang="ts">
import { computed } from 'vue'

/**
 * 昵称的像素化缩写当头像。同一个人永远是同一张。
 *
 * 不让用户传图:头像是公开展示的内容,传上来就得审(黄赌毒、二维码引流),
 * 而头像没有照片那条人工审核链路。画出来就没有这类风险,
 * 而且人人都有——实测 288 个用户里只有 3 个人愿意自己设头像。
 *
 * 配色按 seed 取,所以 279 个都叫"旅行者"的人也能靠颜色区分开。
 */
const props = withDefaults(defineProps<{ seed?: string; size?: number }>(), { seed: '', size: 56 })

// 实色圆底 + 挖空的字:深色背景上最干净。
// 之前是浅底深字,一堆小圆点糊在页面上,像贴纸
const COLORS = [
  '#f5a33c', '#e0785e', '#8fd3a8', '#7bb7e0',
  '#d98cb3', '#c9bd8f', '#9b8cd9', '#6fc7c1',
]


function hash(text: string): number {
  let h = 2166136261
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return h >>> 0
}

// 昵称里可能带 #用户编号 这类后缀,只拿名字部分显示
const name = computed(() => (props.seed || '旅行者').split('#')[0].trim() || '旅')

const initials = computed(() => {
  const n = name.value
  // 中文一个字就够认,拉丁字母太窄,取两个
  return /[一-龥]/.test(n[0]) ? n[0] : n.slice(0, 2).toUpperCase()
})

const color = computed(() => COLORS[hash(props.seed || '旅行者') % COLORS.length])

const boxStyle = computed(() => ({
  width: `${props.size}rpx`,
  height: `${props.size}rpx`,
  background: color.value,
}))

const textStyle = computed(() => ({
  color: '#16110c',
  fontSize: `${Math.round(props.size * (initials.value.length > 1 ? 0.38 : 0.52))}rpx`,
}))
</script>

<style scoped>
.pixel-avatar {
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  box-sizing: border-box;
  flex-shrink: 0;
  overflow: hidden;
}
.initials {
  line-height: 1;
}
</style>
