/**
 * 全站配色的唯一出处。
 *
 * 以前颜色硬写在十几个文件里,换一次肤要全局替换,每次都漏(地图的迷雾、
 * 像素头像的配色都漏过)。现在样式里一律用 CSS 变量,canvas 和组件用这里的常量,
 * 换肤只改这一个文件。
 *
 * 深色的理由很实际:照片和地图是这个游戏的主角,深色背景不跟它们抢。
 * 但要用中性深灰,不用原来那种褐黑——学生说"压抑"说的是那个褐黑,不是暗本身。
 */
export const THEME = {
  bg: '#121417',        // 页面底
  bgSunken: '#0d0f11',  // 地图框、输入框这类凹下去的面
  card: '#1a1d21',      // 卡片
  cardAlt: '#20242a',   // 次级卡片、提示条
  line: '#262b31',      // 细分隔线
  lineStrong: '#39414a', // 需要看得见的边框
  ink: '#e8e6e3',       // 主文字
  inkDim: '#9aa0a8',    // 次要文字
  inkFaint: '#6a7079',  // 最弱的文字
  accent: '#f5a33c',    // 强调:主按钮、选中态、插旗
  onAccent: '#221703',  // 压在强调色上的字
  good: '#6fc7a1',      // 猜中、读懂
  warn: '#ff6b5e',      // 掉命、AI、危险操作
} as const

/** 地图 canvas 用的颜色,跟着主题走 */
export const MAP_THEME = {
  bg: THEME.bgSunken,
  land: '#1e232a',
  landAlt: '#232932',
  border: '#3a434e',
  label: THEME.inkFaint,
  // 迷雾压在地图上:太黑会把整张图糊掉,只要让未探索的地方"看得见轮廓、看不清细节"
  fog: 'rgba(8,10,13,0.62)',
  pick: THEME.accent,
  truth: THEME.good,
  ai: THEME.warn,
  line: THEME.ink,
}
