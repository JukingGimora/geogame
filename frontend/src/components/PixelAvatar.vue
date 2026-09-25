<template>
  <view class="pixel-avatar" :style="{ width: sizePx, height: sizePx, background: bg }">
    <view v-for="(on, i) in cells" :key="i" class="cell" :style="cellStyle(i, on)" />
  </view>
</template>

<script setup lang="ts">
import { computed } from 'vue'

/**
 * 昵称算出来的像素头像。同一个昵称永远是同一张脸。
 *
 * 不让用户传图:头像是公开展示的内容,传上来就得审(黄赌毒、二维码引流),
 * 而头像没有照片那条人工审核链路。生成的话这类风险根本不存在,
 * 而且人人都有头像——实测 288 个用户里只有 3 个人愿意自己设。
 */
const props = withDefaults(defineProps<{ seed?: string; size?: number }>(), { seed: '', size: 56 })

// 五列里只画左边三列,右边镜像——对称的图案比随机噪点更像一张脸
const GRID = 5
const HALF = 3

const PALETTES = [
  ['#f5a33c', '#2a1c05'],
  ['#8fd3a8', '#0f2418'],
  ['#7bb7e0', '#0c1d2a'],
  ['#d98cb3', '#2a1220'],
  ['#c7b083', '#241c10'],
  ['#9b8cd9', '#1a1430'],
]

function hash(text: string): number {
  let h = 2166136261
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return h >>> 0
}

const seedHash = computed(() => hash(props.seed || '旅行者'))
const palette = computed(() => PALETTES[seedHash.value % PALETTES.length])
const bg = computed(() => palette.value[1])
const sizePx = computed(() => `${props.size}rpx`)

const cells = computed<boolean[]>(() => {
  const out: boolean[] = []
  let bits = seedHash.value
  for (let row = 0; row < GRID; row++) {
    const left: boolean[] = []
    for (let col = 0; col < HALF; col++) {
      bits = Math.imul(bits, 1103515245) + 12345
      left.push(((bits >>> 16) & 1) === 1)
    }
    out.push(...left, left[1], left[0])
  }
  return out
})

function cellStyle(index: number, on: boolean) {
  const unit = props.size / GRID
  return {
    width: `${unit}rpx`,
    height: `${unit}rpx`,
    left: `${(index % GRID) * unit}rpx`,
    top: `${Math.floor(index / GRID) * unit}rpx`,
    background: on ? palette.value[0] : 'transparent',
  }
}
</script>

<style scoped>
.pixel-avatar {
  position: relative;
  border-radius: 50%;
  overflow: hidden;
  border: 1px solid #4b4231;
  box-sizing: border-box;
  flex-shrink: 0;
}
.cell {
  position: absolute;
}
</style>
