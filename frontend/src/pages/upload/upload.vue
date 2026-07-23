<template>
  <view class="upload">
    <text class="g-title">{{ t('upload.title') }}</text>

    <view class="photo-box" @tap="choose">
      <image v-if="filePath && previewable" class="preview" :src="filePath" mode="aspectFill" />
      <text v-else-if="filePath" class="placeholder">{{ t('upload.noPreview', { name: fileName }) }}</text>
      <text v-else class="placeholder">{{ t('upload.choose') }}</text>
    </view>

    <text class="section">{{ t('upload.pickLocation') }}</text>
    <ChinaMap :height="300" :interactive="true" :markers="markers" @pick="onPick" />

    <textarea class="story" v-model="story" :placeholder="t('upload.story')" maxlength="2000" />

    <button class="g-btn primary" :disabled="submitting" @tap="submit">{{ t('upload.submit') }}</button>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import ChinaMap from '../../components/ChinaMap.vue'
import { api } from '../../api'
import { t } from '../../locale'
import type { LngLat } from '../../lib/geo'
import type { MapMarker } from '../../lib/mapRender'

const filePath = ref('')
const fileName = ref('')
const story = ref('')
const location = ref<LngLat | null>(null)
const submitting = ref(false)

const markers = computed<MapMarker[]>(() => (location.value ? [{ ...location.value, kind: 'pick' }] : []))
const previewable = computed(() => !/\.(heic|heif|tif|tiff)$/i.test(fileName.value))

function choose() {
  uni.chooseImage({
    count: 1,
    extension: ['jpg', 'jpeg', 'png', 'webp', 'gif', 'bmp', 'tif', 'tiff', 'heic', 'heif', 'avif'],
    success: (res) => {
      filePath.value = res.tempFilePaths[0]
      const file = (res.tempFiles as Array<{ name?: string }>)?.[0]
      fileName.value = file?.name || ''
    },
  })
}

function onPick(p: LngLat) {
  location.value = p
}

async function submit() {
  if (!filePath.value || !location.value) {
    uni.showToast({ title: t('upload.needAll'), icon: 'none' })
    return
  }
  submitting.value = true
  try {
    await api.uploadPhoto(filePath.value, location.value.lat, location.value.lng, story.value)
    uni.showToast({ title: t('upload.submitted'), icon: 'none', duration: 2500 })
    setTimeout(() => uni.navigateBack(), 1500)
  } catch (e: unknown) {
    const status = (e as { status?: number })?.status
    uni.showToast({ title: t('upload.failed', { status: status ? String(status) : '网络' }), icon: 'none' })
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.upload {
  min-height: 100vh;
  background: #16110c;
  padding: 90rpx 24rpx 40rpx;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: 20rpx;
}
.title {
  color: #e9dfc9;
  font-size: 38rpx;
  display: none;
}
.photo-box {
  height: 320rpx;
  background: #211a13;
  border-radius: 12rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}
.preview {
  width: 100%;
  height: 100%;
}
.placeholder {
  color: #a2937b;
  font-size: 28rpx;
}
.section {
  color: #a2937b;
  font-size: 26rpx;
}
.story {
  width: 100%;
  min-height: 160rpx;
  background: #211a13;
  border-radius: 12rpx;
  padding: 20rpx;
  box-sizing: border-box;
  color: #e9dfc9;
  font-size: 28rpx;
}
.btn {
  background: #232d3e;
  color: #c9d4e3;
  border: none;
  font-size: 30rpx;
  border-radius: 12rpx;
  line-height: 2.6;
  width: 100%;
}
.btn.primary {
  background: #f5a33c;
  color: #2a1c05;
}
</style>
