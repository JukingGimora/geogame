import { t } from '../locale'

/**
 * 后端 detail 到人话的映射。用户不该看到 422、only_own_photos 这种东西。
 * 401 那几个(missing_token/invalid_token/user_not_found)不列:api 层会自动重登重试,正常到不了这里。
 */
const MESSAGES: Record<string, string> = {
  // 上传
  file_too_large: 'errors.fileTooLarge',
  invalid_image: 'errors.invalidImage',
  invalid_coordinates: 'errors.invalidCoordinates',
  // 开局
  no_photos_available: 'errors.noPhotos',
  all_photos_played: 'errors.allPlayed',
  only_own_photos: 'errors.onlyOwnPhotos',
  region_not_found: 'errors.regionNotFound',
  // 关卡
  run_not_found: 'errors.runNotFound',
  round_not_found: 'errors.roundNotFound',
  round_already_finished: 'errors.roundFinished',
  hint_not_available: 'errors.hintNotAvailable',
  invalid_hint_level: 'errors.hintNotAvailable',
  // 登录
  wechat_code_invalid: 'errors.wechatInvalid',
}

export function errorMessage(e: unknown): string {
  const err = e as { status?: number; data?: { detail?: string } } | undefined
  const key = err?.data?.detail ? MESSAGES[err.data.detail] : undefined
  if (key) return t(key)
  if (!err?.status) return t('errors.network')
  return t('errors.unknown')
}
