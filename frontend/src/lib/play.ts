import { api } from '../api'
import { errorMessage } from './errors'

/**
 * 开一局并进入关卡。地图页和排行榜都要用,放在一处免得两边的错误处理慢慢分叉。
 *
 * photoId 来自「叫朋友猜这张」的分享;后端拿不到那张时会自动降级成普通一局,
 * 所以这里不需要区分处理。
 */
export async function startRun(photoId?: number): Promise<void> {
  // 模板里若写成 @tap="startRun",Vue 会把事件对象塞进来,这里挡一道
  const pid = typeof photoId === 'number' && photoId > 0 ? photoId : undefined
  try {
    const run = await api.createRun(undefined, pid)
    uni.navigateTo({ url: `/pages/play/play?runId=${run.run_id}` })
  } catch (e: unknown) {
    uni.showToast({ title: errorMessage(e), icon: 'none' })
  }
}
