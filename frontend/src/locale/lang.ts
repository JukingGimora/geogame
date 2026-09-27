/**
 * 这次运行用哪种语言。
 *
 * 小程序永远是中文,不给选。H5 默认英文(它是给外语用户看的),
 * 但中文版必须还在:`?lang=zh` 就切回去,选择记在 localStorage 里,
 * 之后再进不用再带参数。
 *
 * 一个包装两种语言,而不是发两份 H5:两份要各自构建、各自部署,
 * 改一个字要记得改两遍,迟早漏。
 */
export type Lang = 'zh' | 'en'

function resolve(): Lang {
  // #ifdef H5
  try {
    const q = new URLSearchParams(location.search).get('lang')
    if (q === 'zh' || q === 'en') {
      localStorage.setItem('geogame_lang', q)
      return q
    }
    const saved = localStorage.getItem('geogame_lang')
    if (saved === 'zh' || saved === 'en') return saved
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
