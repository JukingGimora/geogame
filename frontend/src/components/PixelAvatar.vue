<template>
  <view class="pixel-avatar" :style="boxStyle">
    <view v-for="(cell, i) in cells" :key="i" class="cell" :style="cell" />
    <text class="px-font initials" :style="textStyle">{{ initials }}</text>
  </view>
</template>

<script setup lang="ts">
import { computed } from 'vue'

/**
 * 昵称的缩写压在马赛克底上。同一个人永远是同一张。
 *
 * 不让用户传图:头像是公开展示的内容,传上来就得审(黄赌毒、二维码引流),
 * 而头像没有照片那条人工审核链路。画出来就没有这类风险,而且人人都有——
 * 实测 288 个用户里只有 3 个人愿意自己设头像。
 *
 * 底色原来是一块纯色,一列排下来像色卡。现在是同色深浅两档拼的 6×6 马赛克,
 * 格子按昵称哈希,左右对称,所以每个人的纹理不同,而字仍然居中、仍然一眼能认。
 */
const props = withDefaults(defineProps<{ seed?: string; size?: number }>(), { seed: '', size: 56 })

const GRID = 6
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

/** 同色深浅两档。差得太多字就压不住了,所以两档都偏亮 */
function shade(hex: string, t: number): string {
  const c = (i: number) => parseInt(hex.slice(1 + i * 2, 3 + i * 2), 16)
  const v = (i: number) => Math.round(c(i) * t + 0x16 * (1 - t))
  return `rgb(${v(0)},${v(1)},${v(2)})`
}

// 昵称里可能带 #用户编号 这类后缀,只拿名字部分显示
const name = computed(() => (props.seed || '旅行者').split('#')[0].trim() || '旅')
const initials = computed(() => {
  const n = name.value
  // 中文一个字就够认,拉丁字母太窄,取两个
  return /[一-龥]/.test(n[0]) ? n[0] : n.slice(0, 2).toUpperCase()
})

const base = computed(() => COLORS[hash(props.seed || '旅行者') % COLORS.length])

const cells = computed(() => {
  const step = 100 / GRID
  const half = GRID / 2
  const out: Record<string, string>[] = []
  for (let y = 0; y < GRID; y++) {
    for (let x = 0; x < GRID; x++) {
      // 左半边算一次,右半边照镜子——对称的纹理更像一张"脸",也更好记
      const bit = hash(`${props.seed}:${x < half ? x : GRID - 1 - x}:${y}`)
      out.push({
        left: `${x * step}%`,
        top: `${y * step}%`,
        width: `${step}%`,
        height: `${step}%`,
        background: shade(base.value, bit % 3 === 0 ? 0.74 : 1),
      })
    }
  }
  return out
})

const boxStyle = computed(() => ({ width: `${props.size}rpx`, height: `${props.size}rpx` }))
const textStyle = computed(() => ({
  fontSize: `${Math.round(props.size * (initials.value.length > 1 ? 0.38 : 0.52))}rpx`,
}))
</script>

<style scoped>
.pixel-avatar {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  box-sizing: border-box;
  flex-shrink: 0;
  overflow: hidden;
}
.cell {
  position: absolute;
}
.initials {
  position: relative;
  line-height: 1;
  color: #16110c;
}
</style>
