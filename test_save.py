"""测试信息系统编辑保存功能 -- 直接调后端 API 排除前端干扰。"""
import urllib.request, json, sys

BASE = "http://localhost:8000/api"

def api(method, path, data=None, jwt=None):
    url = f"{BASE}{path}"
    body = json.dumps(data).encode() if data else None
    headers = {"Content-Type": "application/json"}
    if jwt:
        headers["Authorization"] = f"Bearer {jwt}"
    r = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        resp = urllib.request.urlopen(r)
        return json.loads(resp.read().decode()), resp.status
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode()), e.code

# 1. Login
jwt_resp, _ = api("POST", "/auth/login", {"username": "admin", "password": "Admin123!"})
jwt = jwt_resp["access_token"]
print("1. Login OK")

# 2. Get first page
list_resp, _ = api("GET", "/info-systems?size=100&page=1", jwt=jwt)
items = list_resp["items"]
total = list_resp["total"]
print(f"2. Total records: {total}, first page: {len(items)}")

if not items:
    print("FAIL: No records")
    sys.exit(1)

# 3. Pick first record
target = items[0]
sys_id = target["id"]
old_name = target["system_name"]
new_name = old_name + " [SAVE_TEST_2026]"
print(f"3. Target: id={sys_id}")
print(f"   old_name: {old_name}")
print(f"   new_name: {new_name}")

# 4. Send PUT with minimal fields (just the ones that matter)
update_resp, status = api("PUT", f"/info-systems/{sys_id}", {
    "system_name": new_name,
}, jwt)
print(f"4. PUT response: HTTP {status}, message: {update_resp.get('message')}")

# 5. Re-fetch using search to find the updated record
verify_resp, _ = api("GET", f"/info-systems?size=5&page=1", jwt=jwt)
found = None
for item in verify_resp["items"]:
    if item["id"] == sys_id:
        found = item
        break

if found:
    actual = found["system_name"]
    if actual == new_name:
        print(f"PASS: system_name updated correctly!")
    else:
        print(f"FAIL: system_name did NOT update!")
        print(f"   expected: {new_name}")
        print(f"   actual:   {actual}")
else:
    print(f"FAIL: Record id={sys_id} not found in first page")

# 6. Restore
restore_resp, _ = api("PUT", f"/info-systems/{sys_id}", {
    "system_name": old_name,
}, jwt)
print(f"6. Restored: {restore_resp.get('message')}")
