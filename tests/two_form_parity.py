# -*- coding: utf-8 -*-
"""两态一致性：同一份 roots 配置，源码态和 exe 态跑出来的结果必须一致。

HERE 那个 bug（exe 把自己所在目录当项目）就是两态不一致漏出来的。
这类问题成窝，所以不逐个猜，直接把两边的可观测输出摆到一起比。
预期只有一处合法差异：exe 里「仅源码态」的 L8 条目不登记（59 vs 67）。
"""
import io, json, os, shutil, socket, subprocess, sys, tempfile, time
import urllib.error, urllib.request

BC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# release_pkg 是作者本机的发布目录，别人 clone 下来只有自己打出来的 dist——两个都认，
# 谁在就用谁，否则这行在别人机器上直接 FileNotFoundError。首选保持原样，不改语义。
_CAND = [os.path.join(BC, d, "lingtaios.exe") for d in ("dist", "release_pkg")]
EXE = next((p for p in _CAND if os.path.isfile(p)), _CAND[0])
PY, DN = sys.executable, subprocess.DEVNULL


def sh(c):
    r = subprocess.run(c, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return (r.stdout or b"").decode("mbcs", errors="replace")


def kill():
    for ln in sh("netstat -ano -p TCP").splitlines():
        p = ln.split()
        if len(p) >= 5 and p[0] == "TCP" and p[3] == "LISTENING" and p[1].endswith(":8765"):
            sh("taskkill /F /PID %s /T" % p[4])
    sh("taskkill /F /IM lingtaios.exe /T")
    sh('wmic process where "name=\'python.exe\' and commandline like \'%%dashboard.py%%\'" delete')
    time.sleep(1.6)


def wait_up(secs=70):
    for _ in range(int(secs / 0.4)):
        s = socket.socket()
        s.settimeout(0.4)
        up = s.connect_ex(("127.0.0.1", 8765)) == 0
        s.close()
        if up:
            return True
        time.sleep(0.4)
    return False


def post(path, payload, t=90):
    req = urllib.request.Request("http://127.0.0.1:8765/" + path,
                                 data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=t) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, {}
    except Exception as e:
        return "ERR", {"e": repr(e)}


def collect(rf, proj):
    d = json.loads(urllib.request.urlopen("http://127.0.0.1:8765/data.json",
                                          timeout=25).read().decode("utf-8"))
    h = d["health"]
    st_detail, r_detail = post("api/project_detail", {"path": proj})
    st_tpl, r_tpl = post("api/templates", {})
    st_browse, r_browse = post("api/browse", {"path": os.path.dirname(proj)})
    st_find, r_find = post("api/find_projects", {"locations": [os.path.dirname(proj)], "depth": 2})
    return {
        "项目名集合": sorted(p["name"] for p in d["projects"]),
        "坑库条数": len(d["pitfall"]["rows"]),
        "坑库列数": len(d["pitfall"]["columns"]),
        "方法真源数": len(d.get("methods") or []),
        "健康 ok": h["ok"],
        "健康 applicable": h["applicable"],
        "健康 missing": len(h["missing"]),
        "健康 noroot": h["noroot"],
        "详情页 HTTP": st_detail,
        "详情页 ok": r_detail.get("ok"),
        "详情页器官数": len(r_detail.get("organs") or {}),
        "继续做指令有内容": bool((r_detail.get("resume") or "").strip()),
        "开窗模板 HTTP": st_tpl,
        "开窗模板有内容": bool((r_tpl.get("open") or "").strip()),
        "浏览 HTTP": st_browse,
        "浏览到的子目录数": len(r_browse.get("dirs") or []),
        "扫描 HTTP": st_find,
        "扫描到的候选数": r_find.get("total"),
        "first_run": d.get("first_run"),
        "unreachable 数": len(d.get("unreachable_projects") or []),
        "excluded 数": len(d.get("excluded_projects") or []),
    }


kill()
sand = tempfile.mkdtemp(prefix="parity_")
work = os.path.join(sand, "work")
proj = os.path.join(work, "样本项目")
os.makedirs(os.path.join(proj, "brain"))
for f in ("00_宪法.md", "01_法典.md", "05_交接.md"):
    io.open(os.path.join(proj, "brain", f), "w", encoding="utf-8").write("# %s\n" % f)
io.open(os.path.join(proj, "README.md"), "w", encoding="utf-8").write("# r\n")
os.makedirs(os.path.join(work, "另一个项目"))
io.open(os.path.join(work, "另一个项目", "a.md"), "w", encoding="utf-8").write("# a\n")

home = tempfile.mkdtemp(prefix="ph_")
rf = os.path.join(sand, "roots.json")
json.dump({"machine_id": "PARITY", "roots": {"NEXUS": None, "D": None, "HOME": home},
           "workspaces": [work], "projects": [], "excluded": [], "setup_done": True},
          io.open(rf, "w", encoding="utf-8"), ensure_ascii=False)

# ── 源码态 ──
subprocess.Popen([PY, "-X", "utf8", "dashboard.py", "--no-browser", "--roots-file", rf],
                 cwd=BC, stdout=DN, stderr=DN)
print("源码态起来:", wait_up())
src = collect(rf, proj)
kill()

# ── exe 态（同一份 roots）──
runner = tempfile.mkdtemp(prefix="parityexe_")
shutil.copy2(EXE, os.path.join(runner, "lingtaios.exe"))
subprocess.Popen([os.path.join(runner, "lingtaios.exe"), "--no-browser", "--roots-file", rf],
                 cwd=runner, stdout=DN, stderr=DN)
print("exe 态起来:", wait_up())
exe = collect(rf, proj)
kill()

# 合法差异：exe 不登记「仅源码态」的 L8 条目；源码态会把 brain-console 自己算进去
LEGIT = {"健康 ok", "健康 applicable", "项目名集合"}

print("\n%-20s %-34s %-34s" % ("对比项", "源码态", "exe 态"))
print("-" * 92)
diff, ok = [], 0
for k in src:
    a, b = src[k], exe[k]
    same = (a == b)
    if same:
        ok += 1
    else:
        diff.append(k)
    mark = "  " if same else ("~ " if k in LEGIT else "!!")
    print("%s%-18s %-34s %-34s" % (mark, k, str(a)[:34], str(b)[:34]))

print("\n" + "=" * 92)
bad = [k for k in diff if k not in LEGIT]
print("一致 %d 项 / 共 %d 项" % (ok, len(src)))
print("合法差异（形态本就不同）:", [k for k in diff if k in LEGIT] or "无")
print("**不该有的差异**:", bad or "无")
print("\n%s" % ("两态一致 —— 没有新的形态相关 bug" if not bad else "发现形态不一致，要修"))
for p in (sand, home, runner):
    shutil.rmtree(p, ignore_errors=True)
