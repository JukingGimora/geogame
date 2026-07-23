import zhCN from './zh-CN'

const messages = zhCN

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
