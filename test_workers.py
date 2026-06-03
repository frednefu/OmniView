import urllib.request, json

# 1. 登录
data = json.dumps({"username": "admin", "password": "Admin123!"}).encode()
req = urllib.request.Request(
    "http://localhost:8000/api/auth/login", data=data,
    headers={"Content-Type": "application/json"}, method="POST"
)
resp = urllib.request.urlopen(req)
jwt = json.loads(resp.read().decode())["access_token"]
print("JWT OK")

# 2. Worker 列表
req = urllib.request.Request(
    "http://localhost:8000/api/workers",
    headers={"Authorization": f"Bearer {jwt}"}
)
resp = urllib.request.urlopen(req)
workers = json.loads(resp.read().decode())
print(f"total={workers['total']}, items={len(workers['items'])}")
for w in workers["items"]:
    print(f"  ID={w['id']} name={w['worker_name']} status={w['status']}")
