/**
 * 朋友圈入口默认不在分享菜单里,光注册 onShareTimeline 不够,
 * 还要显式把 shareTimeline 加进菜单,右上角"..."里那一格才会亮。
 */
export function enableShareMenu(): void {
  // #ifdef MP-WEIXIN
  uni.showShareMenu({ menus: ['shareAppMessage', 'shareTimeline'] })
  // #endif
}
