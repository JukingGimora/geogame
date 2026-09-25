<template>
  <view class="upload">
    <text class="g-title">{{ t('upload.title') }}</text>

    <view class="photo-box" :style="{ height: boxHeight + 'rpx' }" @tap="choose">
      <image v-if="filePath && previewable" class="preview" :src="filePath" mode="aspectFit" />
      <text v-else-if="filePath" class="placeholder">{{ t('upload.noPreview', { name: fileName }) }}</text>
      <text v-else class="placeholder">{{ t('upload.choose') }}</text>
    </view>

    <text class="hint-line">{{ t('upload.imageOnly') }}</text>

    <text class="section">{{ t('upload.pickLocation') }}</text>
    <!-- #ifdef MP-WEIXIN -->
    <NativeMapPicker :height="480" :markers="markers" @pick="onPick" />
    <!-- #endif -->
    <!-- #ifndef MP-WEIXIN -->
    <ChinaMap :height="480" :interactive="true" :markers="markers" @pick="onPick" />
    <!-- #endif -->

    <textarea class="story" v-model="story" :placeholder="t('upload.story')" maxlength="2000" />

    <button class="g-btn primary" :disabled="submitting" @tap="submit">
      {{ submitting ? t('upload.submitting') : t('upload.submit') }}
    </button>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import ChinaMap from '../../components/ChinaMap.vue'
// #ifdef MP-WEIXIN
import NativeMapPicker from '../../components/NativeMapPicker.vue'
// #endif
import { api } from '../../api'
import { t } from '../../locale'
import { errorMessage } from '../../lib/errors'
import { logEvent } from '../../lib/analytics'
import type { LngLat } from '../../lib/geo'
import type { MapMarker } from '../../lib/mapRender'

const filePath = ref('')
const fileName = ref('')
const story = ref('')
const location = ref<LngLat | null>(null)
const submitting = ref(false)
const boxHeight = ref(600)

const markers = computed<MapMarker[]>(() => (location.value ? [{ ...location.value, kind: 'pick' }] : []))
const previewable = computed(() => !/\.(heic|heif|tif|tiff)$/i.test(fileName.value))

const BOX_CONTENT_WIDTH_RPX = 702
const BOX_MIN_HEIGHT_RPX = 300

function choose() {
  logEvent('upload_choose_click')
  // #ifdef MP-WEIXIN
  // 旧的 chooseImage 已不推荐,而且我们之前还传了它不认的 extension 参数,
  // 调用直接失败又没有 fail 回调——学生反馈的"选视频没结果"就是这么来的。
  uni.chooseMedia({
    count: 1,
    mediaType: ['image'],
    sizeType: ['compressed'],
    success: (res: any) => useFile(res.tempFiles?.[0]?.tempFilePath, res.tempFiles?.[0]?.name),
    fail: (err: any) => onChooseFail(err),
  })
  // #endif
  // #ifndef MP-WEIXIN
  uni.chooseImage({
    count: 1,
    sizeType: ['compressed'],
    success: (res: any) => useFile(res.tempFilePaths?.[0], res.tempFiles?.[0]?.name),
    fail: (err: any) => onChooseFail(err),
  })
  // #endif
}

function onChooseFail(err: any) {
  const msg = String(err?.errMsg ?? '')
  if (msg.includes('cancel')) return // 用户自己取消的,不用打扰他
  logEvent('upload_choose_fail', '', undefined, { err: msg.slice(0, 60) })
  uni.showToast({ title: t('upload.chooseFailed'), icon: 'none', duration: 2500 })
}

function useFile(path?: string, name?: string) {
  if (!path) {
    onChooseFail({ errMsg: 'empty path' })
    return
  }
  filePath.value = path
  fileName.value = name || ''
  logEvent('upload_photo_chosen')
  uni.getImageInfo({
    src: path,
    success: (info) => {
      const ratio = info.width / info.height
      boxHeight.value = Math.max(BOX_MIN_HEIGHT_RPX, Math.round(BOX_CONTENT_WIDTH_RPX / ratio))
    },
    fail: () => {
      boxHeight.value = 600
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
  logEvent('upload_submit')
  try {
    await api.uploadPhoto(filePath.value, location.value.lat, location.value.lng, story.value)
    logEvent('upload_success')
    uni.showToast({ title: t('upload.submitted'), icon: 'none', duration: 2500 })
    setTimeout(() => uni.navigateBack(), 1500)
  } catch (e: unknown) {
    logEvent('upload_fail', '', undefined, { msg: errorMessage(e).slice(0, 40) })
    uni.showToast({ title: errorMessage(e), icon: 'none', duration: 2500 })
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.upload {
  min-height: 100vh;
  background: #efe3c8;
  padding: 90rpx 24rpx 40rpx;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: 20rpx;
}
.hint-line {
  color: #9a8a6b;
  font-size: 22rpx;
}
.title {
  color: #3b2f1c;
  font-size: 38rpx;
  display: none;
}
.photo-box {
  background: #fbf5e6;
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
  color: #7a6a4d;
  font-size: 28rpx;
}
.section {
  color: #7a6a4d;
  font-size: 26rpx;
}
.story {
  width: 100%;
  min-height: 160rpx;
  background: #fbf5e6;
  border-radius: 12rpx;
  padding: 20rpx;
  box-sizing: border-box;
  color: #3b2f1c;
  font-size: 28rpx;
}
.btn {
  background: #232d3e;
  color: #6b5a3c;
  border: none;
  font-size: 30rpx;
  border-radius: 12rpx;
  line-height: 2.6;
  width: 100%;
}
.btn.primary {
  background: #b8531a;
  color: #fff6e6;
}
</style>
