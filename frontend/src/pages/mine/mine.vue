<template>
  <view class="mine" :style="{ paddingTop: `${topOffset + 48}px` }">
    <view class="header">
      <text class="g-title">{{ t('mine.title') }}</text>
      <text class="g-stamp" v-if="me">{{ t('map.points') }} {{ me.points }}</text>
    </view>
    <view v-if="photos.length === 0" class="empty">{{ t('mine.empty') }}</view>

    <view v-for="p in photos" :key="p.id" class="card">
      <image class="thumb" :src="photoUrl(p.url)" mode="aspectFill" />
      <view class="meta">
        <text class="status" :class="p.status">{{ statusText[p.status] }}</text>
        <text v-if="p.reject_reason" class="reason">{{ p.reject_reason }}</text>
        <text v-if="p.story" class="story">{{ p.story }}</text>
      </view>
    </view>

    <view class="fb g-card">
      <view class="fb-header" @tap="fbExpanded = !fbExpanded">
        <text class="fb-title">核心体验反馈</text>
        <text class="fb-toggle">{{ fbExpanded ? '收起 ▾' : '展开 ▸' }}</text>
      </view>

      <view v-if="fbExpanded">
        <view class="fb-item">
          <text class="fb-label">1. 你觉得好玩吗？</text>
          <view class="fb-options">
            <view class="fb-option" :class="{ active: fbData.fun === 'yes' }" @tap="fbData.fun = 'yes'">好玩</view>
            <view class="fb-option" :class="{ active: fbData.fun === 'no' }" @tap="fbData.fun = 'no'">不好玩</view>
            <view class="fb-option" :class="{ active: fbData.fun === 'so' }" @tap="fbData.fun = 'so'">一般</view>
          </view>
        </view>

        <view class="fb-item">
          <text class="fb-label">2. 你最想玩哪种照片？</text>
          <view class="fb-options">
            <view class="fb-option" :class="{ active: fbData.photoType === '景观' }" @tap="fbData.photoType = '景观'">景观</view>
            <view class="fb-option" :class="{ active: fbData.photoType === '城市' }" @tap="fbData.photoType = '城市'">城市</view>
            <view class="fb-option" :class="{ active: fbData.photoType === '人文' }" @tap="fbData.photoType = '人文'">人文</view>
            <view class="fb-option" :class="{ active: fbData.photoType === '美食' }" @tap="fbData.photoType = '美食'">美食</view>
            <view class="fb-option" :class="{ active: fbData.photoType === '其他' }" @tap="fbData.photoType = '其他'">其他</view>
          </view>
        </view>

        <view class="fb-item">
          <text class="fb-label">3. 你会不会愿意继续玩下去？</text>
          <view class="fb-options">
            <view class="fb-option" :class="{ active: fbData.continuePlay === 'yes' }" @tap="fbData.continuePlay = 'yes'">会</view>
            <view class="fb-option" :class="{ active: fbData.continuePlay === 'no' }" @tap="fbData.continuePlay = 'no'">不会</view>
            <view class="fb-option" :class="{ active: fbData.continuePlay === 'maybe' }" @tap="fbData.continuePlay = 'maybe'">看情况</view>
          </view>
        </view>

        <view class="fb-item">
          <text class="fb-label">4. 你会不会愿意分享给别人？</text>
          <view class="fb-options">
            <view class="fb-option" :class="{ active: fbData.share === 'yes' }" @tap="fbData.share = 'yes'">会</view>
            <view class="fb-option" :class="{ active: fbData.share === 'no' }" @tap="fbData.share = 'no'">不会</view>
            <view class="fb-option" :class="{ active: fbData.share === 'maybe' }" @tap="fbData.share = 'maybe'">看情况</view>
          </view>
        </view>

        <view class="fb-item">
          <text class="fb-label">5. 精神股东共建精神家园，您还有什么个性建议，愿闻其详。</text>
          <textarea class="fb-input" v-model="fbData.reason" placeholder="个人反馈、建议、想法都可以" maxlength="300" />
        </view>

        <button class="g-btn" :disabled="fbSending" @tap="sendFb">提交反馈</button>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, BASE_URL } from '../../api'
import { t, tMap } from '../../locale'

const photos = ref<any[]>([])
const me = ref<{ points: number } | null>(null)
const topOffset = ref(0)
const statusText = tMap('mine.status')

onMounted(async () => {
  topOffset.value = (uni.getSystemInfoSync().statusBarHeight || 0) + 12
  photos.value = await api.myPhotos()
  me.value = await api.me()
})

const fbExpanded = ref(false)
const fbData = ref({
  fun: '',
  photoType: '',
  continuePlay: '',
  share: '',
  reason: ''
})
const fbSending = ref(false)

async function sendFb() {
  if (!fbData.value.fun) {
    uni.showToast({ title: '请完成必填项', icon: 'none' })
    return
  }
  fbSending.value = true
  try {
    const content = JSON.stringify(fbData.value)
    await api.sendFeedback(content)
    fbData.value = {
      fun: '',
      photoType: '',
      continuePlay: '',
      share: '',
      reason: ''
    }
    uni.showToast({ title: '感谢反馈！', icon: 'none', duration: 2500 })
  } finally {
    fbSending.value = false
  }
}

function photoUrl(path: string): string {
  return path.startsWith('http') ? path : BASE_URL + path
}
</script>

<style scoped>
.mine {
  min-height: 100vh;
  background: #16110c;
  padding: 24rpx 24rpx 28rpx;
  box-sizing: border-box;
}
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16rpx;
}
.title {
  color: #e9dfc9;
  font-size: 38rpx;
  display: none;
}
.points {
  color: #f5a33c;
  font-size: 26rpx;
}
.empty {
  color: #a2937b;
  font-size: 28rpx;
  text-align: center;
  margin-top: 200rpx;
}
.fb {
  display: flex;
  flex-direction: column;
  gap: 24rpx;
  margin-bottom: 24rpx;
}
.fb-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.fb-title {
  color: #f5a33c;
  font-size: 30rpx;
  font-weight: bold;
}
.fb-toggle {
  color: #a2937b;
  font-size: 24rpx;
}
.fb-item {
  display: flex;
  flex-direction: column;
  gap: 12rpx;
}
.fb-label {
  color: #e9dfc9;
  font-size: 28rpx;
  line-height: 1.5;
}
.fb-options {
  display: flex;
  flex-wrap: wrap;
  gap: 10rpx;
}
.fb-option {
  background: #211a13;
  border: 1px solid #322818;
  color: #a2937b;
  font-size: 24rpx;
  padding: 10rpx 20rpx;
  border-radius: 6rpx;
  text-align: center;
  flex: 1 1 auto;
}
.fb-option.active {
  background: #f5a33c;
  border-color: #f5a33c;
  color: #16110c;
}
.fb-input {
  width: 100%;
  min-height: 100rpx;
  background: #211a13;
  border: 1px solid #322818;
  border-radius: 8rpx;
  padding: 16rpx;
  box-sizing: border-box;
  color: #e9dfc9;
  font-size: 26rpx;
}
.card {
  display: flex;
  flex-direction: column;
  gap: 12rpx;
  background: #211a13;
  border-radius: 12rpx;
  padding: 14rpx;
  margin-bottom: 14rpx;
}
.thumb {
  width: 100%;
  height: 220rpx;
  border-radius: 8rpx;
  flex-shrink: 0;
}
.meta {
  display: flex;
  flex-direction: column;
  gap: 6rpx;
  overflow: hidden;
}
.status {
  font-size: 24rpx;
  color: #a2937b;
}
.status.live {
  color: #6fe0a8;
}
.status.rejected {
  color: #e08484;
}
.reason {
  color: #e08484;
  font-size: 22rpx;
}
.story {
  color: #c9d4e3;
  font-size: 24rpx;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
