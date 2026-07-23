# geogame（暂用名）

UGC 照片猜地点游戏。每一个孤独的旅行者，都需要被理解。

- 立项与设计：`docs/立项报告.md`
- 技术方案：`docs/架构设计.md`

## 目录
- `backend/` — FastAPI 后端（游客认证、上传审核、区域树、闯关判分、AI对手桩）
- `frontend/` — uni-app 前端（待建：H5 → 微信小程序 → App）

## 后端启动
```sh
sh backend/run.sh        # 端口 8020,自动建 venv、建表、播种 34 省级区域
```
- API 文档：http://localhost:8020/docs
- 测试：`cd backend && .venv/bin/python -m pytest`
- 管理接口鉴权：请求头 `X-Admin-Token`（环境变量 `GEOGAME_ADMIN_TOKEN`,开发默认 `dev-admin`）

## 环境变量（前缀 GEOGAME_）
| 变量 | 默认 | 说明 |
|---|---|---|
| DB_URL | sqlite 本地文件 | 生产换 postgres+asyncpg |
| JWT_SECRET | dev 值 | 生产必换(≥32字节) |
| ADMIN_TOKEN | dev-admin | 审核后台口令 |
| UPLOAD_DIR | ./uploads | 未配置OSS时的本地存储目录 |
| FAKE_AI | true | 关闭后由真实 vLLM worker 写入 ai_guesses |
| OSS_ACCESS_KEY_ID | 无 | 配置后自动切换为阿里云OSS存储(storage.py) |
| OSS_ACCESS_KEY_SECRET | 无 | 建议用只有该bucket权限的RAM子账号,不要用主账号 |
| OSS_BUCKET | 无 | 例如 geogame |
| OSS_ENDPOINT | 无 | 例如 https://oss-cn-beijing.aliyuncs.com |

以上四个OSS变量写在 `backend/.env`(已被 .gitignore 排除),`run.sh` 启动时会自动加载。

## 设计铁律(改代码前必读)
1. 坐标一律 WGS-84;GCJ-02 转换只在前端地图适配层。
2. 判分/提示③④/事实复盘不经 AI 模型(幻觉隔离,见 scoring.py 头注)。
3. 面向用户的文案不写在后端,后端只返回错误码。
4. 积分只走 points_ledger 追加,不做余额字段。
