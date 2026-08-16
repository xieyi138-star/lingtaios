# -*- coding: utf-8 -*-
"""项目管理多维度压测。
不只测「能不能用」，而是把真实用户会撞上的每个角落都打一遍：
安全 / 幂等 / 三种来源 / 撤销 / 边界 / 并发 / 持久化 / 恶意输入。
"""
import io, json, os, shutil, socket, subprocess, sys, tempfile, threading, time
import urllib.error
import urllib.request

BC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY, DN = sys.executable, subprocess.DEVNULL
ok_all = True
dims = {}


def rec(dim, n, ok, d=""):
    global ok_all
    ok_all = ok_all and ok
    dims.setdefault(dim, [0, 0])
    dims[dim][0] += 1
    if ok:
        dims[dim][1] += 1
    print("[%s] %-8s %-40s %s" % ("PASS" if ok else "FAIL", dim, n, d))


def sh(c):
    r = subprocess.run(c, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return (r.stdout or b"").decode("mbcs", errors="replace")


def kill():
    for ln in sh("netstat -ano -p TCP").splitlines():
        p = ln.split()
        if len(p) >= 5 and p[0] == "TCP" and p[3] == "LISTENING" and p[1].endswith(":8765"):
            sh("taskkill /F /PID %s /T" % p[4])
    sh('wmic process where "name=\'python.exe\' and commandline like \'%%dashboard.py%%\'" delete')
    time.sleep(1.5)


def post(p, payload, t=60):
    req = urllib.request.Request("http://127.0.0.1:8765/" + p,
                                 data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=t) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8", "replace"))
        except Exception:
            return e.code, {}
    except Exception as e:
        return "ERR", {"error": "%s: %s" % (type(e).__name__, e)}


def projects():
    d = json.loads(urllib.request.urlopen("http://127.0.0.1:8765/data.json",
                                          timeout=20).read().decode("utf-8"))
    return d, sorted(p["name"] for p in d["projects"])


def mkproj(base, name, organs=False, files=3):
    p = os.path.join(base, name)
    os.makedirs(p, exist_ok=True)
    for i in range(files):
        io.open(os.path.join(p, "f%d.md" % i), "w", encoding="utf-8").write("# %d\n" % i)
    if organs:
        os.makedirs(os.path.join(p, "brain"), exist_ok=True)
        io.open(os.path.join(p, "brain", "00_宪法.md"), "w", encoding="utf-8").write("# c\n")
    return p


kill()
sand = tempfile.mkdtemp(prefix="mgmt_")
ws = os.path.join(sand, "工作区 A")            # 故意带空格和中文
os.makedirs(ws)
p_ws1 = mkproj(ws, "在工作区里的甲", organs=True)
p_ws2 = mkproj(ws, "在工作区里的乙")
p_solo = mkproj(sand, "单独加的项目")
p_long = mkproj(sand, "深" * 40)               # 超长中文名
home = tempfile.mkdtemp(prefix="mh_")
rf = os.path.join(sand, "roots.json")
json.dump({"machine_id": "T", "roots": {"NEXUS": None, "D": None, "HOME": home},
           "workspaces": [ws], "projects": [p_solo], "excluded": [], "setup_done": True},
          io.open(rf, "w", encoding="utf-8"), ensure_ascii=False)

subprocess.Popen([PY, "-X", "utf8", "dashboard.py", "--no-browser", "--roots-file", rf],
                 cwd=BC, stdout=DN, stderr=DN)
up = False
for _ in range(80):
    s = socket.socket(); s.settimeout(0.4)
    up = s.connect_ex(("127.0.0.1", 8765)) == 0; s.close()
    if up: break
    time.sleep(0.4)
rec("基础", "服务起来", up)
d, names = projects()
rec("基础", "初始项目齐", "在工作区里的甲" in names and "单独加的项目" in names, str(names))

# ── 安全：移除绝不碰文件 ──
before_files = sorted(os.listdir(p_ws1))
before_brain = os.path.isdir(os.path.join(p_ws1, "brain"))
st, r = post("api/project_remove", {"path": p_ws1})
rec("安全", "移除返回成功", st == 200 and r.get("ok"), "how=%s" % r.get("how"))
rec("安全", "文件夹还在磁盘上", os.path.isdir(p_ws1))
rec("安全", "里面的文件一个没少", sorted(os.listdir(p_ws1)) == before_files,
    "%s" % sorted(os.listdir(p_ws1)))
rec("安全", "brain/ 没被卸掉", os.path.isdir(os.path.join(p_ws1, "brain")) == before_brain)
rec("安全", "接口自报 files_untouched", r.get("files_untouched") is True)
d, names = projects()
rec("功能", "已从列表消失", "在工作区里的甲" not in names, str(names))
rec("功能", "同工作区的兄弟不受连累", "在工作区里的乙" in names)

# ── 撤销 ──
st, r = post("api/project_restore", {"path": p_ws1})
d, names = projects()
rec("撤销", "恢复后回到列表", st == 200 and "在工作区里的甲" in names, str(names))

# ── 三种来源都能移 ──
st, r = post("api/project_remove", {"path": p_solo})
d, names = projects()
rec("来源", "单独加的能移", "单独加的项目" not in names, "how=%s" % r.get("how"))
st, r = post("api/project_restore", {"path": p_solo})
d, names = projects()
rec("来源", "单独加的能恢复", "单独加的项目" in names)
st, r = post("api/project_remove", {"path": ws})
d, names = projects()
rec("来源", "整个工作区能移（连里面的一起）",
    "在工作区里的甲" not in names and "在工作区里的乙" not in names, str(names))
conf = json.load(io.open(rf, encoding="utf-8"))
rec("来源", "工作区从配置里摘掉", conf.get("workspaces") == [])
post("api/project_add", {"path": ws, "whole": True})
d, names = projects()
rec("来源", "整个工作区能加回来",
    "在工作区里的甲" in names and "在工作区里的乙" in names, str(names))

# ── 幂等：重复操作不炸、不产生重复 ──
post("api/project_remove", {"path": p_ws2})
st2, r2 = post("api/project_remove", {"path": p_ws2})
conf = json.load(io.open(rf, encoding="utf-8"))
rec("幂等", "重复移除不报错", st2 == 200 and r2.get("ok"))
rec("幂等", "排除单不重复", len(conf["excluded"]) == len(set(conf["excluded"])),
    str([os.path.basename(x) for x in conf["excluded"]]))
post("api/project_restore", {"path": p_ws2})
st3, r3 = post("api/project_restore", {"path": p_ws2})
rec("幂等", "重复恢复不报错", st3 == 200 and r3.get("ok"))
st4, r4 = post("api/project_add", {"path": p_solo})
rec("幂等", "重复添加被识别为 dup", r4.get("dup") is True, r4.get("reason"))
conf = json.load(io.open(rf, encoding="utf-8"))
rec("幂等", "projects 无重复", len(conf["projects"]) == len(set(conf["projects"])))

# ── 移除后重新添加（用户改主意） ──
post("api/project_remove", {"path": p_solo})
st, r = post("api/project_add", {"path": p_solo})
d, names = projects()
rec("回流", "移除后重新添加能回来", "单独加的项目" in names, str(r)[:60])

# ── 边界 ──
st, r = post("api/project_add", {"path": p_long})
d, names = projects()
rec("边界", "超长中文名项目能加", any(n.startswith("深深") for n in names))
st, r = post("api/project_remove", {"path": ""})
rec("边界", "空路径被拒", st == 400)
st, r = post("api/project_add", {"path": "Z:\\根本不存在"})
rec("边界", "不存在的路径被拒", st == 400, str(r.get("error"))[:40])
st, r = post("api/project_add", {"path": os.path.join(sand, "工作区 A")})
rec("边界", "带空格中文路径正常", st == 200)
st, r = post("api/project_remove", {"path": p_ws1 + "\\"})
rec("边界", "结尾多个反斜杠也认得", st == 200 and r.get("ok"))
post("api/project_restore", {"path": p_ws1})
st, r = post("api/project_remove", {"path": p_ws1.upper()})
d, names = projects()
rec("边界", "大小写不同也能移", "在工作区里的甲" not in names)
post("api/project_restore", {"path": p_ws1})

# ── 恶意输入 ──
for bad, label in ((".." + os.sep + "..", "相对路径穿越"),
                   ("C:\\Windows\\System32", "系统目录"),
                   ("\\\\?\\C:\\", "UNC 前缀")):
    st, r = post("api/project_add", {"path": bad})
    rec("输入", "%s 不崩溃" % label, st in (200, 400, 500), "HTTP %s" % st)
st, r = post("api/project_remove", {"path": 12345})
rec("输入", "非字符串路径不崩溃", st in (200, 400))

# ── 并发：同时移 3 个 ──
targets = [mkproj(ws, "并发%d" % i) for i in range(3)]
post("api/refresh", {})
outs = {}
ths = [threading.Thread(target=lambda i=i: outs.__setitem__(i, post("api/project_remove", {"path": targets[i]})))
       for i in range(3)]
[t.start() for t in ths]
[t.join(timeout=60) for t in ths]
d, names = projects()
rec("并发", "3 个并发移除都成功", all(outs.get(i, (0, {}))[0] == 200 for i in range(3)),
    str([outs.get(i, ("?",))[0] for i in range(3)]))
rec("并发", "3 个都从列表消失", not any(("并发%d" % i) in names for i in range(3)), str(names))
conf = json.load(io.open(rf, encoding="utf-8"))
rec("并发", "配置没被写坏（能解析且无重复）",
    len(conf["excluded"]) == len(set(conf["excluded"])), "%d 条" % len(conf["excluded"]))

# ── 持久化：重启后仍生效 ──
kill()
subprocess.Popen([PY, "-X", "utf8", "dashboard.py", "--no-browser", "--roots-file", rf],
                 cwd=BC, stdout=DN, stderr=DN)
for _ in range(80):
    s = socket.socket(); s.settimeout(0.4)
    up = s.connect_ex(("127.0.0.1", 8765)) == 0; s.close()
    if up: break
    time.sleep(0.4)
d, names = projects()
rec("持久", "重启后移除仍生效", not any(("并发%d" % i) in names for i in range(3)), str(names))
rec("持久", "重启后恢复的仍在", "在工作区里的甲" in names)
rec("持久", "excluded 暴露给前端以便撤销", len(d.get("excluded_projects", [])) > 0,
    "%d 条" % len(d.get("excluded_projects", [])))

# ── 移除后文件夹被真删：不能崩，要标出来 ──
ghost = mkproj(sand, "待会儿删掉的")
post("api/project_add", {"path": ghost})
post("api/project_remove", {"path": ghost})
shutil.rmtree(ghost, ignore_errors=True)
post("api/refresh", {})
d, names = projects()
ex = [e for e in d.get("excluded_projects", []) if os.path.normcase(e["path"]) == os.path.normcase(ghost)]
rec("鲁棒", "已移出且磁盘已删的会标 exists=false", ex and ex[0]["exists"] is False, str(ex)[:70])

# ── 真源保护 ──
real = json.load(io.open(os.path.join(BC, "roots.json"), encoding="utf-8"))
rec("隔离", "真 roots.json 未被污染", real.get("workspaces") is None and real.get("projects") == [])
realdata = json.load(io.open(os.path.join(BC, "site", "data.json"), encoding="utf-8"))
rec("隔离", "真 data.json 未被污染", len(realdata["projects"]) == 22,
    "%d 个项目" % len(realdata["projects"]))

kill()
for p in (sand, home):
    shutil.rmtree(p, ignore_errors=True)
print("\n" + "=" * 72)
for k, (tot, ok) in sorted(dims.items()):
    print("  %-6s %d/%d" % (k, ok, tot))
print("=" * 72)
print("ALL PASSED" if ok_all else "SOME FAILED")
