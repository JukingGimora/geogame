/**
 * 这次运行用哪种语言。
 *
 * 小程序永远是中文,不给选。网页版中英分站:`/en/` 和 `/zh/` 是同一份产物挂在
 * 两个路径下,语言看路径就知道 —— 链接发出去对方一眼认得出是哪个站,
 * 不像 `?lang=zh` 那样像"改过设置的英文站"。
 *
 * 路径之外还认 `?lang=`(旧链接、二维码里可能带着),并把结果记下来:
 * 万一落到一个没有语言段的路径上,至少还是他上次选的那种。
 */
export type Lang = 'zh' | 'en'

const KEY = 'geogame_lang'

function valid(v: string | null): Lang | null {
  return v === 'zh' || v === 'en' ? v : null
}

function resolve(): Lang {
  // #ifdef H5
  try {
    // 路径优先:/zh/ 就是中文站,哪怕浏览器里存的是英文
    const fromPath = valid(location.pathname.split('/').filter(Boolean)[0] ?? null)
    const fromQuery = valid(new URLSearchParams(location.search).get('lang'))
    const picked = fromPath ?? fromQuery
    if (picked) {
      localStorage.setItem(KEY, picked)
      return picked
    }
    const saved = valid(localStorage.getItem(KEY))
    if (saved) return saved
  } catch {
    // 隐私模式下 localStorage 会抛,照默认走
  }
  return 'en'
  // #endif
  // #ifndef H5
  return 'zh'
  // #endif
}

export const currentLang: Lang = resolve()

/** 切到另一种语言的地址。整页跳过去,不在运行时换文案:
 *  已经渲染出来的页面到处都缓存了字符串,热切换只会切一半。 */
export function otherLangUrl(): string {
  // #ifdef H5
  const other: Lang = currentLang === 'en' ? 'zh' : 'en'
  return `/${other}/${location.hash || ''}`
  // #endif
  // #ifndef H5
  return ''
  // #endif
}

export const otherLangLabel = currentLang === 'en' ? '中文' : 'EN'
