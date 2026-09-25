import { ref } from 'vue'
import { api } from '../api'
import { logEvent } from './analytics'

export function useProfileHint(location: string) {
  const show = ref(false)

  async function check() {
    try {
      const me = await api.me()
      // 后端判定:系统给的默认名算没起过名,自己改过就不再打扰
      show.value = me.default_name === true
      if (show.value) logEvent('profile_hint_view', '', undefined, { location })
    } catch {
      show.value = false
    }
  }

  function go() {
    logEvent('profile_hint_click', '', undefined, { location })
    uni.navigateTo({ url: '/pages/login/login' })
  }

  return { show, check, go }
}
