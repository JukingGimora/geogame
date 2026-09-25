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
:root {
  /* 值在 lib/theme.ts 里,两处要一起改 */
  --bg: #121417;
  --bg-sunken: #0d0f11;
  --card: #1a1d21;
  --card-alt: #20242a;
  --line: #262b31;
  --line-strong: #39414a;
  --ink: #e8e6e3;
  --ink-dim: #9aa0a8;
  --ink-faint: #6a7079;
  --accent: #f5a33c;
  --on-accent: #221703;
  --good: #6fc7a1;
  --warn: #ff6b5e;
}

body {
  background: var(--bg);
  color: var(--ink);
  font-family: -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

.px-font {
  font-family: 'Fusion Pixel 12px Proportional SC', monospace;
  letter-spacing: 2rpx;
}

.g-title {
  font-family: 'Fusion Pixel 12px Proportional SC', monospace;
  color: var(--ink);
  font-size: 36rpx;
  letter-spacing: 4rpx;
}

.g-stamp {
  font-family: 'Fusion Pixel 12px Proportional SC', monospace;
  color: var(--accent);
  letter-spacing: 3rpx;
}

.g-card {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 8rpx;
  padding: 24rpx;
}

.g-btn {
  background: transparent;
  color: var(--ink-dim);
  border: 1px solid var(--line-strong);
  border-radius: 8rpx;
  font-size: 28rpx;
  line-height: 2.6;
  letter-spacing: 4rpx;
}

.g-btn::after {
  border: none;
}

.g-btn.primary {
  background: var(--accent);
  color: var(--on-accent);
  border-color: var(--accent);
  font-family: 'Fusion Pixel 12px Proportional SC', monospace;
  font-size: 30rpx;
}

.g-btn[disabled] {
  opacity: 0.4;
  background: transparent;
  color: var(--ink-dim);
}

.g-btn.primary[disabled] {
  background: var(--accent);
  color: var(--on-accent);
}
</style>
