/**
 * 朋友圈入口默认不在分享菜单里,光注册 onShareTimeline 不够,
 * 还要显式把 shareTimeline 加进菜单,右上角"..."里那一格才会亮。
 *
 * withTimeline 传 false 用于那些发朋友圈没意义的页面(别人点开是单页模式,
 * 看到的就是这一页)——只留转发给好友。
 */
export function enableShareMenu(withTimeline = true): void {
  // #ifdef MP-WEIXIN
  uni.showShareMenu({
    menus: withTimeline ? ['shareAppMessage', 'shareTimeline'] : ['shareAppMessage'],
  })
  // #endif
}
