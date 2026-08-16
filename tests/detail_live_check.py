# -*- coding: utf-8 -*-
"""对着正在跑的 exe，把项目详情逐个打一遍——确认「打不开」纯粹是服务没在跑"""
import json, urllib.request, urllib.error

def post(path, payload, t=90):
    req = urllib.request.Request("http://127.0.0.1:8765/" + path,
                                 data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=t) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8", "replace"))

d = json.loads(urllib.request.urlopen("http://127.0.0.1:8765/data.json", timeout=20).read().decode("utf-8"))
ps = d["projects"]
print("对 %d 个项目逐个打开详情：\n" % len(ps))
bad = []
for p in ps:
    st, r = post("api/project_detail", {"path": p["path"]})
    ok = st == 200 and r.get("ok")
    if not ok:
        bad.append((p["name"], st, str(r.get("error"))[:50]))
    print("  [%s] %-28s HTTP %s" % ("OK " if ok else "!!", p["name"][:28], st))
print()
if bad:
    print("打不开的：")
    for n, st, e in bad:
        print("   %s  HTTP %s  %s" % (n, st, e))
else:
    print(">>> 全部 %d 个详情页都能正常打开，接口没问题" % len(ps))
