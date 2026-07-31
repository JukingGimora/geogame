export const BASE_URL = import.meta.env.VITE_API_BASE ?? 'http://localhost:8020'

const TOKEN_KEY = 'geogame_token'
const DEVICE_KEY = 'geogame_device'
const NICKNAME_KEY = 'geogame_nickname'
const AVATAR_KEY = 'geogame_avatar'
const LOGGED_IN_KEY = 'geogame_logged_in'

function deviceKey(): string {
  let key = uni.getStorageSync(DEVICE_KEY)
  if (!key) {
    key = 'dev-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 12)
    uni.setStorageSync(DEVICE_KEY, key)
  }
  return key
}

let token: string = uni.getStorageSync(TOKEN_KEY) || ''

async function guestLogin(): Promise<void> {
  const nickname = (uni.getStorageSync(NICKNAME_KEY) as string | '') || undefined
  const avatarUrl = (uni.getStorageSync(AVATAR_KEY) as string | '') || undefined
  const res = await rawRequest('POST', '/api/v1/auth/guest', { device_key: deviceKey(), nickname, avatar_url: avatarUrl })
  token = res.token
  uni.setStorageSync(TOKEN_KEY, token)
  await restoreByWechat()
}

/**
 * 游客身份只锚在本地存储的 device_key 上,而小程序的开发版/体验版/正式版存储互相隔离、
 * 微信也会在空间紧张时清理它——存储一没,老用户就变成了全新游客,上传和积分全部失联。
 * openid 不会丢,所以每次登录后立刻静默绑一次:后端认得这个 openid 的话,会把原来的
 * 账号换回来。绑不上不影响继续玩,顶多是这次仍以游客身份进行。
 */
async function restoreByWechat(): Promise<void> {
  // #ifdef MP-WEIXIN
  try {
    const code = await new Promise<string>((resolve, reject) => {
      uni.login({ provider: 'weixin', success: (r: any) => resolve(r.code), fail: reject })
    })
    const res = await rawRequest('POST', '/api/v1/auth/wechat', { code })
    if (res?.token) {
      token = res.token
      uni.setStorageSync(TOKEN_KEY, token)
    }
  } catch {
    /* 静默失败:没绑上不该挡着人玩 */
  }
  // #endif
}

function rawRequest(method: 'GET' | 'POST' | 'DELETE', path: string, data?: any): Promise<any> {
  return new Promise((resolve, reject) => {
    uni.request({
      url: BASE_URL + path,
      method,
      data,
      header: token ? { Authorization: `Bearer ${token}` } : {},
      success: (res) => {
        if (res.statusCode && res.statusCode < 400) resolve(res.data)
        else reject({ status: res.statusCode, data: res.data })
      },
      fail: reject,
    })
  })
}

async function request(method: 'GET' | 'POST' | 'DELETE', path: string, data?: any): Promise<any> {
  if (!token) await guestLogin()
  try {
    return await rawRequest(method, path, data)
  } catch (e: any) {
    if (e?.status === 401) {
      await guestLogin()
      return rawRequest(method, path, data)
    }
    throw e
  }
}

export const api = {
  me: () => request('GET', '/api/v1/auth/me'),
  updateProfile: (nickname?: string, avatarUrl?: string) =>
    request('POST', '/api/v1/auth/profile', { nickname, avatar_url: avatarUrl }),
  wechatLogin: async (code: string): Promise<any> => {
    if (!token) await guestLogin()
    const res = await rawRequest('POST', '/api/v1/auth/wechat', { code })
    token = res.token
    uni.setStorageSync(TOKEN_KEY, token)
    return res
  },
  regions: () => request('GET', '/api/v1/regions'),
  createRun: (regionId?: number) => request('POST', '/api/v1/runs', { region_id: regionId ?? null }),
  getRun: (runId: number) => request('GET', `/api/v1/runs/${runId}`),
  unlockHint: (roundId: number, level: number) => request('POST', `/api/v1/rounds/${roundId}/hints`, { level }),
  guess: (roundId: number, lat: number, lng: number) =>
    request('POST', `/api/v1/rounds/${roundId}/guess`, { lat, lng }),
  myPhotos: () => request('GET', '/api/v1/photos/mine'),
  deletePhoto: (photoId: number) => request('DELETE', `/api/v1/photos/${photoId}`),
  leaderboard: (board: 'best_run' | 'points') => request('GET', `/api/v1/leaderboard?board=${board}`),
  sendFeedback: (content: string, contact?: string) =>
    request('POST', '/api/v1/feedback', { content, contact: contact || null }),
  logEvent: (eventType: string, refType = '', refId?: number, meta = '') =>
    request('POST', '/api/v1/events', { event_type: eventType, ref_type: refType, ref_id: refId ?? null, meta }),

  async uploadAvatar(filePath: string): Promise<{ url: string }> {
    if (!token) await guestLogin()
    return new Promise((resolve, reject) => {
      uni.uploadFile({
        url: BASE_URL + '/api/v1/auth/avatar',
        filePath,
        name: 'file',
        header: { Authorization: `Bearer ${token}` },
        success: (res) => {
          if (res.statusCode < 400) resolve(JSON.parse(res.data))
          else reject({ status: res.statusCode, data: res.data })
        },
        fail: reject,
      })
    })
  },

  async uploadPhoto(filePath: string, lat: number, lng: number, story: string): Promise<any> {
    if (!token) await guestLogin()
    return new Promise((resolve, reject) => {
      uni.uploadFile({
        url: BASE_URL + '/api/v1/photos',
        filePath,
        name: 'file',
        formData: { lat: String(lat), lng: String(lng), story },
        header: { Authorization: `Bearer ${token}` },
        success: (res) => {
          if (res.statusCode < 400) resolve(JSON.parse(res.data))
          else reject({ status: res.statusCode, data: res.data })
        },
        fail: reject,
      })
    })
  },
}

export function hasLoggedIn(): boolean {
  return uni.getStorageSync(LOGGED_IN_KEY) === '1'
}

export function setLoggedIn(): void {
  uni.setStorageSync(LOGGED_IN_KEY, '1')
}

export function setUserProfile(nickname: string, avatar?: string): void {
  uni.setStorageSync(NICKNAME_KEY, nickname)
  if (avatar) uni.setStorageSync(AVATAR_KEY, avatar)
}