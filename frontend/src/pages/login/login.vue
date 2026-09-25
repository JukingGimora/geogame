<template>
  <view class="login" :style="{ paddingTop: `${topOffset + 48}px` }">
    <view class="header">
      <text class="g-title">{{ t('login.title') }}</text>
    </view>

    <view class="g-card">
      <view class="avatar-wrap"><PixelAvatar :seed="nickname" :size="160" /></view>

      <text class="hint">{{ t('login.avatarHint') }}</text>

      <input
        class="nick-input"
        v-model="nickname"
        :placeholder="t('login.nickPlaceholder')"
        maxlength="12"
      />

      <button
        class="g-btn primary"
        :disabled="!canLogin"
        @tap="doLogin"
      >
        {{ t('login.enter') }}
      </button>

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
import { errorMessage } from '../../lib/errors'
import PixelAvatar from '../../components/PixelAvatar.vue'

const topOffset = ref(0)
const nickname = ref('')

const canLogin = computed(() => nickname.value.trim().length > 0)

onMounted(() => {
  topOffset.value = (uni.getWindowInfo().statusBarHeight || 0) + 12
  const savedNick = uni.getStorageSync('geogame_nickname')
  if (savedNick) nickname.value = savedNick
})

async function linkWechatSilently() {
  // #ifdef MP-WEIXIN
  try {
    const loginRes: any = await new Promise((resolve, reject) => {
      uni.login({ provider: 'weixin', success: resolve, fail: reject })
    })
    await api.wechatLogin(loginRes.code)
  } catch {
    // 静默绑定失败不影响头像昵称保存,换设备找回账号这个附加能力就是少一次而已
  }
  // #endif
}

async function doLogin() {
  if (!canLogin.value) return
  const nick = nickname.value.trim()
  try {
    await linkWechatSilently()
    const profile = await api.updateProfile(nick)
    uni.setStorageSync('geogame_nickname', profile.nickname)
    uni.setStorageSync('geogame_logged_in', '1')
    leave()
  } catch (e: unknown) {
    uni.showToast({ title: errorMessage(e), icon: 'none' })
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

.avatar-wrap {
  display: flex;
  justify-content: center;
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

</style>