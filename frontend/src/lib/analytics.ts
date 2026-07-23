import { api } from '../api'

export function logEvent(eventType: string, refType = '', refId?: number, meta?: Record<string, unknown>): void {
  api.logEvent(eventType, refType, refId, meta ? JSON.stringify(meta) : '').catch(() => {})
}
