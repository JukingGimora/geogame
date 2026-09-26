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


/**
 * 九个文化圈各有自己的颜色,照那张人文地理的分区图来:
 * 相邻的圈色相要拉开,不然在小屏上分不出边界。
 * 解锁与否只改亮度,不改色相——颜色是"这是哪个圈",亮度是"你走到哪了"。
 */
export const CIRCLE_COLORS: Record<string, string> = {
  西欧: '#1f5fa8',   // 图里的 WESTERN,含北美与澳新
  东欧: '#2196f3',   // ORTHODOX
  伊斯兰: '#ef3e33', // MUSLIM
  东亚: '#f5d020',   // CONFUCIAN
  南亚: '#e2632a',   // HINDU
  非洲: '#f0942f',   // AFRICAN
  拉美: '#5b2c91',   // LATIN AMERICAN
  东南亚: '#3fa34d', // 那张图没有单列,按图一的划分单独成圈,取没被占用的绿
  太平洋: '#17a2a2', // 同上,取青
}

