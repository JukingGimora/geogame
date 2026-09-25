<script setup lang="ts">
import { onLaunch } from '@dcloudio/uni-app'
import { logEvent } from './lib/analytics'
import { ensureWechatBinding } from './api'

onLaunch(() => {
  logEvent('session_start')
  // 趁账号还在,把 openid 绑上;将来存储被清才找得回来
  ensureWechatBinding()
})
</script>

<style>
page,
body {
  background: #efe3c8;
  color: #3b2f1c;
  font-family: -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

.px-font {
  font-family: 'Fusion Pixel 12px Proportional SC', monospace;
  letter-spacing: 2rpx;
}

.g-title {
  font-family: 'Fusion Pixel 12px Proportional SC', monospace;
  color: #3b2f1c;
  font-size: 36rpx;
  letter-spacing: 4rpx;
}

.g-stamp {
  font-family: 'Fusion Pixel 12px Proportional SC', monospace;
  color: #b8531a;
  letter-spacing: 3rpx;
}

.g-card {
  background: #fbf5e6;
  border: 1px solid #ddcca6;
  border-radius: 8rpx;
  padding: 24rpx;
}

.g-btn {
  background: transparent;
  color: #5d4e33;
  border: 1px solid #c8b58a;
  border-radius: 8rpx;
  font-size: 28rpx;
  line-height: 2.6;
  letter-spacing: 4rpx;
}

.g-btn::after {
  border: none;
}

.g-btn.primary {
  background: #b8531a;
  color: #fff6e6;
  border-color: #b8531a;
  font-family: 'Fusion Pixel 12px Proportional SC', monospace;
  font-size: 30rpx;
}

.g-btn[disabled] {
  opacity: 0.4;
  background: transparent;
  color: #5d4e33;
}

.g-btn.primary[disabled] {
  background: #b8531a;
  color: #fff6e6;
}
</style>
