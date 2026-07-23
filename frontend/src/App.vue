<script setup lang="ts">
import { onLaunch } from '@dcloudio/uni-app'
import { logEvent } from './lib/analytics'

onLaunch(() => {
  logEvent('session_start')
})
</script>

<style>
page,
body {
  background: #16110c;
  color: #e9dfc9;
  font-family: -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

.px-font {
  font-family: 'Fusion Pixel 12px Proportional SC', monospace;
  letter-spacing: 2rpx;
}

.g-title {
  font-family: 'Fusion Pixel 12px Proportional SC', monospace;
  color: #e9dfc9;
  font-size: 36rpx;
  letter-spacing: 4rpx;
}

.g-stamp {
  font-family: 'Fusion Pixel 12px Proportional SC', monospace;
  color: #f5a33c;
  letter-spacing: 3rpx;
}

.g-card {
  background: #211a13;
  border: 1px solid #322818;
  border-radius: 8rpx;
  padding: 24rpx;
}

.g-btn {
  background: transparent;
  color: #d8c9a8;
  border: 1px solid #4b4231;
  border-radius: 8rpx;
  font-size: 28rpx;
  line-height: 2.6;
  letter-spacing: 4rpx;
}

.g-btn::after {
  border: none;
}

.g-btn.primary {
  background: #f5a33c;
  color: #2a1c05;
  border-color: #f5a33c;
  font-family: 'Fusion Pixel 12px Proportional SC', monospace;
  font-size: 30rpx;
}

.g-btn[disabled] {
  opacity: 0.4;
  background: transparent;
  color: #d8c9a8;
}

.g-btn.primary[disabled] {
  background: #f5a33c;
  color: #2a1c05;
}
</style>
