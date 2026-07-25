<template>
  <view class="login" :style="{ paddingTop: `${topOffset + 48}px` }">
    <view class="header">
      <text class="g-title">{{ t('login.title') }}</text>
    </view>

    <view class="g-card">
      <button
        class="avatar-btn"
        open-type="chooseAvatar"
        @chooseavatar="onChooseAvatar"
      >
        <image v-if="avatar" class="avatar" :src="avatar" mode="aspectFill" />
        <view v-else class="avatar-placeholder">
          <text class="px-font avatar-icon">▦</text>
        </view>
      </button>

      <text class="hint">{{ t('login.tapAvatar') }}</text>

      <input
        class="nick-input"
        type="nickname"
        v-model="nickname"
        :placeholder="t('login.nickPlaceholder')"
        maxlength="12"
      />

      <view class="agree" @tap="agreed = !agreed">
        <view class="check" :class="{ checked: agreed }">
          <text v-if="agreed" class="px-font">✓</text>
        </view>
        <text class="agree-text">{{ t('login.agree') }}</text>
      </view>

      <button
        class="g-btn primary"
        :disabled="!canLogin"
        @tap="doLogin"
      >
        {{ t('login.enter') }}
      </button>

      <!-- #ifdef MP-WEIXIN -->
      <button class="g-btn" @tap="doWechatLogin">
        {{ t('login.wechatLogin') }}
      </button>
      <!-- #endif -->

      <button class="g-btn" @tap="skipLogin">
        {{ t('login.skip') }}
      </button>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { t } from '../../locale'
import { api } from '../../api'

const topOffset = ref(0)
const avatar = ref('')
const nickname = ref('')
const agreed = ref(true)

const canLogin = computed(() => {
  return nickname.value.trim() && agreed.value
})

onMounted(() => {
  topOffset.value = (uni.getWindowInfo().statusBarHeight || 0) + 12
  const savedNick = uni.getStorageSync('geogame_nickname')
  const savedAvatar = uni.getStorageSync('geogame_avatar')
  if (savedNick) nickname.value = savedNick
  if (savedAvatar) avatar.value = savedAvatar
})

function onChooseAvatar(e: any) {
  const tempFilePath = e.detail.avatarUrl
  avatar.value = tempFilePath
}

async function doLogin() {
  if (!canLogin.value) return
  const nick = nickname.value.trim()
  try {
    await api.updateProfile(nick, avatar.value || undefined)
    uni.setStorageSync('geogame_nickname', nick)
    if (avatar.value) uni.setStorageSync('geogame_avatar', avatar.value)
    uni.setStorageSync('geogame_logged_in', '1')
    leave()
  } catch {
    uni.showToast({ title: '登录失败', icon: 'none' })
  }
}

async function doWechatLogin() {
  try {
    const loginRes: any = await new Promise((resolve, reject) => {
      uni.login({ provider: 'weixin', success: resolve, fail: reject })
    })
    let res = await api.wechatLogin(loginRes.code)
    const nick = nickname.value.trim()
    if (nick || avatar.value) {
      res = { ...res, user: await api.updateProfile(nick || undefined, avatar.value || undefined) }
    }
    uni.setStorageSync('geogame_logged_in', '1')
    if (res.user?.nickname) uni.setStorageSync('geogame_nickname', res.user.nickname)
    if (res.user?.avatar_url) uni.setStorageSync('geogame_avatar', res.user.avatar_url)
    leave()
  } catch {
    uni.showToast({ title: t('login.wechatFailed'), icon: 'none' })
  }
}

function skipLogin() {
  leave()
}

function leave() {
  const pages = getCurrentPages()
  if (pages.length > 1) uni.navigateBack()
  else uni.reLaunch({ url: '/pages/map/map' })
}
</script>

<style scoped>
.login {
  min-height: 100vh;
  background: #16110c;
  padding: 24rpx 24rpx 28rpx;
  box-sizing: border-box;
}

.header {
  text-align: center;
  margin-bottom: 40rpx;
}

.avatar-btn {
  padding: 0;
  margin: 0;
  background: transparent;
  border: none;
  width: 100%;
  display: flex;
  justify-content: center;
}

.avatar {
  width: 160rpx;
  height: 160rpx;
  border-radius: 50%;
  border: 1px solid #322818;
  background: #0f0c08;
}

.avatar-placeholder {
  width: 160rpx;
  height: 160rpx;
  border-radius: 50%;
  border: 1px dashed #4b4231;
  background: #0f0c08;
  display: flex;
  align-items: center;
  justify-content: center;
}

.avatar-icon {
  color: #4b4231;
  font-size: 60rpx;
}

.hint {
  display: block;
  text-align: center;
  color: #a2937b;
  font-size: 22rpx;
  margin-top: 12rpx;
  margin-bottom: 24rpx;
}

.nick-input {
  width: 100%;
  height: 88rpx;
  background: #0f0c08;
  border: 1px solid #322818;
  border-radius: 8rpx;
  padding: 0 20rpx;
  box-sizing: border-box;
  color: #e9dfc9;
  font-size: 28rpx;
  text-align: center;
  margin-bottom: 20rpx;
}

.agree {
  display: flex;
  align-items: center;
  gap: 12rpx;
  margin-bottom: 24rpx;
}

.check {
  width: 32rpx;
  height: 32rpx;
  border: 1px solid #4b4231;
  border-radius: 6rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20rpx;
  color: #f5a33c;
}

.check.checked {
  background: #f5a33c;
  border-color: #f5a33c;
  color: #16110c;
}

.agree-text {
  color: #a2937b;
  font-size: 22rpx;
}
</style>