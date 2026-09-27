import { tMap } from '../locale'

/**
 * 文化圈名字的显示形式。
 *
 * 圈名在数据里**一直是中文**:它同时是配色表的键、也是开局时回传给后端的 chapter。
 * 所以只在要显示给人看的地方过一遍这个函数,不要图省事把数据里的名字换掉——
 * 换掉的那一刻配色会全丢、开局参数也对不上。
 */
const NAMES = tMap('circles')

export function circleName(zh: string): string {
  return NAMES[zh] || zh
}
