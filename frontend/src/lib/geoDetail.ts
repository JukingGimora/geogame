import { BASE_URL } from '../api'

export interface GeoFeature {
  type: string
  properties: { adcode: number; name: string; center?: [number, number]; centroid?: [number, number] }
  geometry: { type: 'Polygon' | 'MultiPolygon'; coordinates: number[][][] | number[][][][] }
}

export interface GeoCollection {
  features: GeoFeature[]
}

export const PROVINCE_ADCODE: Record<string, number> = {
  北京: 110000, 天津: 120000, 河北: 130000, 山西: 140000, 内蒙古: 150000,
  辽宁: 210000, 吉林: 220000, 黑龙江: 230000, 上海: 310000, 江苏: 320000,
  浙江: 330000, 安徽: 340000, 福建: 350000, 江西: 360000, 山东: 370000,
  河南: 410000, 湖北: 420000, 湖南: 430000, 广东: 440000, 广西: 450000,
  海南: 460000, 重庆: 500000, 四川: 510000, 贵州: 520000, 云南: 530000,
  西藏: 540000, 陕西: 610000, 甘肃: 620000, 青海: 630000, 宁夏: 640000,
  新疆: 650000, 台湾: 710000, 香港: 810000, 澳门: 820000,
}

const cache = new Map<number, GeoCollection>()
const loading = new Set<number>()
const failed = new Set<number>()

export function getBoundary(adcode: number): GeoCollection | undefined {
  return cache.get(adcode)
}

export function ensureBoundary(adcode: number, onLoaded: () => void): void {
  if (cache.has(adcode) || loading.has(adcode) || failed.has(adcode)) return
  loading.add(adcode)
  uni.request({
    url: `${BASE_URL}/api/v1/geo/${adcode}`,
    success: (res) => {
      if (res.statusCode === 200 && res.data && (res.data as GeoCollection).features) {
        cache.set(adcode, res.data as GeoCollection)
        onLoaded()
      } else {
        failed.add(adcode)
      }
    },
    fail: () => failed.add(adcode),
    complete: () => loading.delete(adcode),
  })
}
