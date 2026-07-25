import { ref } from 'vue'
import { api } from '../api'
import { logEvent } from './analytics'

const GUEST_DEFAULT_NICKNAME = '旅行者'

export function useProfileHint(location: string) {
  const show = ref(false)

  async function check() {
    try {
      const me = await api.me()
      show.value = me.nickname === GUEST_DEFAULT_NICKNAME && !me.avatar_url
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
