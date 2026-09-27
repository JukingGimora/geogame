// H5 默认英文、`?lang=zh` 切回中文,所以两份文案都在包里。
// 小程序只有中文,连带 import 一起关掉:小程序包有大小上限,
// 不该为一份用不到的英文文案买单。
// 只有这一处能条件编译——两个分支里各写一遍 import 的话,
// 类型检查看到的是没预处理过的文件,会报重复声明
import zhCN from './zh-CN'

let messages: any = zhCN

// #ifdef H5
import en from './en'
import { currentLang } from './lang'
if (currentLang === 'en') messages = en
// #endif

export function t(path: string, vars: Record<string, string | number> = {}): string {
  const raw = path.split('.').reduce<any>((o, k) => (o ? o[k] : undefined), messages)
  if (typeof raw !== 'string') return path
  return raw.replace(/\{(\w+)\}/g, (_, k) => String(vars[k] ?? ''))
}

export function tList(path: string): string[] {
  const raw = path.split('.').reduce<any>((o, k) => (o ? o[k] : undefined), messages)
  return Array.isArray(raw) ? raw : []
}

export function tMap(path: string): Record<string, string> {
  const raw = path.split('.').reduce<any>((o, k) => (o ? o[k] : undefined), messages)
  return raw && typeof raw === 'object' ? raw : {}
}
