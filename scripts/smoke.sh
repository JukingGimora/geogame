#!/usr/bin/env bash
# 把每个接口都打一遍。NameError / 少导入 / 删了函数没改调用方这类错误,
# 本地跑一条正常路径是发现不了的,只有真的请求过才会暴露。
#
#   ./scripts/smoke.sh                      # 本地
#   ./scripts/smoke.sh https://线上域名      # 部署后
#
# 有任何一个接口不是预期状态码就退出码非 0。

set -uo pipefail
BASE="${1:-http://localhost:8020}"
ADMIN="${GEOGAME_ADMIN_TOKEN:-$(grep -s GEOGAME_ADMIN_TOKEN "$(dirname "$0")/../backend/.env" | cut -d= -f2)}"
API="$BASE/api/v1"
DEV="smoke-probe-fixed"   # 固定设备号,避免每次跑都新建一个用户
FAIL=0

check() { # 名称 期望码 实际码
  if [ "$2" = "$3" ]; then printf "  \033[32m✓\033[0m %-42s %s\n" "$1" "$3"
  else printf "  \033[31m✗\033[0m %-42s 期望 %s 实际 %s\n" "$1" "$2" "$3"; FAIL=1; fi
}
code() { curl -s -m 25 -o /dev/null -w '%{http_code}' "$@"; }

echo "冒烟测试: $BASE"
check "GET  /health" 200 "$(code "$BASE/health")"

TOKEN=$(curl -s -m 25 -X POST "$API/auth/guest" -H 'Content-Type: application/json' \
  -d "{\"device_key\":\"$DEV\"}" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("token",""))' 2>/dev/null)
[ -n "$TOKEN" ] && check "POST /auth/guest" 200 200 || { check "POST /auth/guest" 200 000; echo "拿不到 token,后面没法测"; exit 1; }
AUTH=(-H "Authorization: Bearer $TOKEN")
JSON=(-H 'Content-Type: application/json')

check "GET  /auth/me" 200 "$(code "$API/auth/me" "${AUTH[@]}")"
check "POST /auth/wechat (无效code应400非500)" 400 "$(code -X POST "$API/auth/wechat" "${AUTH[@]}" "${JSON[@]}" -d '{"code":"smoke-invalid"}')"
check "POST /auth/profile" 200 "$(code -X POST "$API/auth/profile" "${AUTH[@]}" "${JSON[@]}" -d '{"nickname":"冒烟测试"}')"
check "POST /auth/profile (临时路径头像应422)" 422 "$(code -X POST "$API/auth/profile" "${AUTH[@]}" "${JSON[@]}" -d '{"avatar_url":"http://tmp/x.jpg"}')"
check "GET  /regions" 200 "$(code "$API/regions" "${AUTH[@]}")"
check "GET  /leaderboard?board=best_run" 200 "$(code "$API/leaderboard?board=best_run" "${AUTH[@]}")"
check "GET  /leaderboard?board=points" 200 "$(code "$API/leaderboard?board=points" "${AUTH[@]}")"
check "GET  /photos/mine" 200 "$(code "$API/photos/mine" "${AUTH[@]}")"
check "POST /events" 200 "$(code -X POST "$API/events" "${AUTH[@]}" "${JSON[@]}" -d '{"event_type":"session_start"}')"
check "POST /feedback" 200 "$(code -X POST "$API/feedback" "${AUTH[@]}" "${JSON[@]}" -d '{"content":"冒烟测试,可忽略"}')"

# 一局完整流程。题库被这个探针玩空后会返回 409,那是预期的,不算失败。
RUN=$(curl -s -m 25 -X POST "$API/runs" "${AUTH[@]}" "${JSON[@]}" -d '{}')
# 必须取第一个**未完成**的关:固定设备号第二次跑时,/runs 会返回上次没打完的那局,
# 取 rounds[0] 会撞上已经猜过的关,白报 409。
RID=$(echo "$RUN" | python3 -c '
import sys,json
d=json.load(sys.stdin)
r=next((x for x in d["rounds"] if not x["finished"]), None)
print(r["round_id"] if r else "")' 2>/dev/null)
if [ -n "$RID" ]; then
  check "POST /runs" 200 200
  check "GET  /runs/{id}" 200 "$(code "$API/runs/$(echo "$RUN"|python3 -c 'import sys,json;print(json.load(sys.stdin)["run_id"])')" "${AUTH[@]}")"
  check "POST /rounds/{id}/hints" 200 "$(code -X POST "$API/rounds/$RID/hints" "${AUTH[@]}" "${JSON[@]}" -d '{"level":1}')"
  check "POST /rounds/{id}/guess" 200 "$(code -X POST "$API/rounds/$RID/guess" "${AUTH[@]}" "${JSON[@]}" -d '{"lat":30,"lng":104}')"
else
  echo "  · 没有未完成的关(题库对该探针已玩空),跳过关卡接口"
fi

if [ -n "$ADMIN" ]; then
  A=(-H "X-Admin-Token: $ADMIN")
  check "GET  /admin/photos?status=live" 200 "$(code "$API/admin/photos?status=live&limit=1" "${A[@]}")"
  check "GET  /admin/photos?status=pending" 200 "$(code "$API/admin/photos?status=pending&limit=1" "${A[@]}")"
  check "GET  /admin/stats" 200 "$(code "$API/admin/stats" "${A[@]}")"
  check "GET  /admin/feedback" 200 "$(code "$API/admin/feedback" "${A[@]}")"
  check "GET  /admin (审核页)" 200 "$(code "$BASE/admin")"
else
  echo "  · 没有 GEOGAME_ADMIN_TOKEN,跳过后台接口"
fi

echo
[ $FAIL -eq 0 ] && echo "全部通过" || echo "有接口异常,别发布"
exit $FAIL
