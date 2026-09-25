/**
 * 全站配色的唯一出处。
 *
 * 以前颜色硬写在十几个文件里,换一次肤要全局替换,每次都漏(地图的迷雾、
 * 像素头像的配色都漏过)。现在样式里一律用 CSS 变量,canvas 和组件用这里的常量,
 * 换肤只改这一个文件。
 *
 * 配色回到最初那套暖褐夜色。中间试过羊皮纸和中性深灰,都更"干净",
 * 但也都把这个游戏的神秘感洗掉了——作者的原话是"压抑就压抑吧"。
 * 深色本来也更合理:照片和地图是主角,背景不该跟它们抢。
 */
export const THEME = {
  bg: '#16110c',        // 页面底
  bgSunken: '#0f0c08',  // 地图框、输入框这类凹下去的面
  card: '#211a13',      // 卡片
  cardAlt: '#2a2110',   // 次级卡片、提示条
  line: '#322818',      // 细分隔线
  lineStrong: '#4b4231', // 需要看得见的边框
  ink: '#e9dfc9',       // 主文字
  inkDim: '#a2937b',    // 次要文字
  inkFaint: '#6b5f4a',  // 最弱的文字
  accent: '#f5a33c',    // 强调:主按钮、选中态、插旗
  onAccent: '#2a1c05',  // 压在强调色上的字
  good: '#8fd3a8',      // 猜中、读懂
  warn: '#e0785e',      // 掉命、AI、危险操作
} as const

/** 地图 canvas 用的颜色。地图是偏蓝的夜色,和页面的暖褐拉开,才像一张摊在桌上的图 */
export const MAP_THEME = {
  bg: '#171e29',
  land: '#223046',
  landAlt: '#26364e',
  border: '#3b4c63',
  label: '#8fa3bd',
  fog: 'rgba(10,12,16,0.78)',
  pick: THEME.accent,
  truth: '#6fe0a8',
  ai: THEME.warn,
  line: THEME.ink,
}
