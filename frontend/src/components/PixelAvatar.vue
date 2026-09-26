<template>
  <view class="pixel-avatar" :style="boxStyle">
    <view v-for="(cell, i) in cells" :key="i" class="cell" :style="cell" />
  </view>
</template>

<script setup lang="ts">
import { computed } from 'vue'

/**
 * 按昵称生成的像素马赛克头像。同一个人永远是同一张。
 *
 * 不让用户传图:头像是公开展示的内容,传上来就得审(黄赌毒、二维码引流),
 * 而头像没有照片那条人工审核链路。画出来就没有这类风险,而且人人都有——
 * 实测 288 个用户里只有 3 个人愿意自己设头像。
 *
 * 原来是「实色圆底 + 一个大字」,一屏排下来像一串色卡,认不出谁是谁。
 * 现在是 5×5 的格子、左右对称(对称的图形人眼更容易记住,也更像一张"脸"),
 * 两种深浅的同色块拼出纹理,不同的人纹理不同。
 */
const props = withDefaults(defineProps<{ seed?: string; size?: number }>(), { seed: '', size: 56 })

const GRID = 5
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

/** 同色深浅两档,比两种颜色拼在一起耐看 */
function shade(hex: string, t: number): string {
  const c = (i: number) => parseInt(hex.slice(1 + i * 2, 3 + i * 2), 16)
  const v = (i: number) => Math.round(c(i) * t + 0x16 * (1 - t))
  return `rgb(${v(0)},${v(1)},${v(2)})`
}

const seed = computed(() => props.seed || '旅行者')
const base = computed(() => COLORS[hash(seed.value) % COLORS.length])

const cells = computed(() => {
  const step = 100 / GRID
  const half = Math.ceil(GRID / 2)
  const out: Record<string, string>[] = []
  for (let y = 0; y < GRID; y++) {
    for (let x = 0; x < GRID; x++) {
      // 只给左半边(含中列)算一次,右半边照镜子——对称才像一张脸
      const mx = x < half ? x : GRID - 1 - x
      const bit = hash(`${seed.value}:${mx}:${y}`)
      if (bit % 100 < 42) continue // 留空,不然满屏一块实色
      out.push({
        left: `${x * step}%`,
        top: `${y * step}%`,
        width: `${step}%`,
        height: `${step}%`,
        background: shade(base.value, bit % 3 === 0 ? 0.62 : 1),
      })
    }
  }
  return out
})

const boxStyle = computed(() => ({
  width: `${props.size}rpx`,
  height: `${props.size}rpx`,
}))
</script>

<style scoped>
.pixel-avatar {
  position: relative;
  border-radius: 8rpx;
  box-sizing: border-box;
  flex-shrink: 0;
  overflow: hidden;
  background: var(--bg-sunken, #0f0c08);
}
.cell {
  position: absolute;
}
</style>
