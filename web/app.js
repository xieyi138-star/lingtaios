/* 大脑驾驶舱 · 前端（零框架）。只渲染 fetch 到的 data.json，本文件不含任何知识。 */
"use strict";

let DATA = null;
const main = document.getElementById("main");

function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/* statusBadge（✓在位 / ✗缺失 / —本机无此根）删了：它唯一的用处是渲染
   「扫描位置」那张别名表，而那张表是内部概念（SKILLS/NEXUS/D/HOME），
   已经从「我的文件」里撤掉——项目没出现时的解法是首页「添加已有项目」，
   不是让用户去读一张根别名表。 */

async function copyText(t) {
  try { await navigator.clipboard.writeText(t); return true; }
  catch (e) {
    const ta = document.createElement("textarea");
    ta.value = t; document.body.appendChild(ta); ta.select();
    const ok = document.execCommand("copy"); ta.remove(); return ok;
  }
}

const PROJ_STATE = {
  generated: ["good", "✓ 状态已生成"],
  not_run: ["warn", "⚠ 未跑生成器"],
  bad_json: ["bad", "✗ 状态文件损坏"],
  null: ["muted", ""],
};
/* ⛔ 「状态已生成」不带时间——一年前生成的和刚生成的长得一模一样。
   实测代价：本项目自己的 02_状态 停在一天前，写着「坑库 38 条 ✅ 无告警」，
   而真源已经 80 条。驾驶舱顶着旧快照报平安，漂了 42 条没有任何东西出声。
   补了「🔄 重算状态」按钮还不够：**没人告诉你该按，按钮就等于不存在**。 */
const STATE_STALE_DAYS = 7;
function stateChip(p) {
  const [cls, label] = PROJ_STATE[p.state] || PROJ_STATE.null;
  if (p.state !== "generated") return [cls, label];
  const d = p.state_age_days;
  if (d === null || d === undefined) return [cls, label];
  if (d >= STATE_STALE_DAYS) return ["warn", "⏳ 状态 " + d + " 天前"];
  return ["good", d <= 0 ? "✓ 状态 今天" : "✓ 状态 " + d + " 天前"];
}
function isActive(p) { return p.state || p.alarms.length || p.handoff_mtime; }
function organN(p) { return Object.values(p.organs).filter(Boolean).length; }

const ORG_DOTS = [["法典", "01_法典.md"], ["状态", "02_状态.md"], ["排产", "03_在建.md"],
  ["监察", "关口清单.md"], ["记忆", "04_待办池.md"], ["进化", "06_提案层.md"]];

function organDots(p) {
  const stale = p.state_at
    ? (Date.now() - new Date(p.state_at.replace(" ", "T")).getTime()) / 86400000 > 7
    : true;
  return '<span class="dots">' + ORG_DOTS.map(([name, file]) => {
    const has = p.organs[file];
    const cls = !has ? "d-none" : (stale ? "d-stale" : "d-ok");
    const tip = name + (has ? (stale ? "（状态超 7 天未更新）" : "（新）") : "（缺失）");
    return '<i class="dot ' + cls + '" title="' + tip + '"></i>';
  }).join("") + "</span>";
}

function slimCard(p) {
  const [scls, sl] = stateChip(p);
  const n = organN(p);
  return '<div class="card slim clickable" data-path="' + esc(p.path) + '"><div class="card-head"><strong>' + esc(p.name) + "</strong>" +
    '<span class="chip ' + scls + '">' + sl + "</span></div>" +
    '<div class="chip-row">' + organDots(p) +
    // ⛔ 卡片上只放用户看得懂、且会据此行动的东西。
    //    「器官 0/9」对没装系统的项目等于常年挂个 0，看着像坏了——直接说「未装系统」。
    //    「⚠ 可升级 N」是通用件同步（体系升级传播），维护体系的人才需要，
    //    用户不改方法论，撤到项目详情页里去。
    (n > 0 ? '<span class="chip good">六器官 ' + n + "/9</span>"
           : '<span class="chip muted">未装系统</span>') +
    (p.alarms.length ? '<span class="chip warn">告警 ' + p.alarms.length + "</span>" : "") +
    (p.handoff_mtime ? '<span class="chip muted">交接 ' + esc(p.handoff_mtime.slice(5, 16)) + "</span>" : "") +
    "</div></div>";
}

function attachCardClicks(scope) {
  (scope || document).querySelectorAll(".card.clickable").forEach(c => {
    c.onclick = () => goProjectDetail(c.dataset.path);
  });
}

/* ---------- 项目详情（点进去：看下一步 + 继续做 + 打开目录） ---------- */
let lastPage = "home";
function goProjectDetail(path) {
  main.innerHTML = '<div class="section"><p class="muted-note">加载中…</p></div>';
  fetch("api/project_detail", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
  }).then(r => r.json()).then(renderProjectDetail)
    .catch(e => main.innerHTML = '<div class="bad-box">✗ ' + esc(String(e)) + "</div>");
}

function renderProjectDetail(d) {
  if (!d.ok) { main.innerHTML = '<div class="bad-box">✗ ' + esc(d.error) + "</div>"; return; }
  const n = Object.values(d.organs).filter(Boolean).length;
  let html = '<div class="section"><div class="filter-row">' +
    '<button class="chip-btn" id="pd-back">← 返回</button>' +
    '<h2 style="border:0;margin:0;flex:1">' + esc(d.name) + "</h2>" +
    (n > 0 ? '<span class="chip good">六器官 ' + n + "/9</span>"
           : '<span class="chip muted">未装系统</span>') + "</div>" +
    '<p class="muted-note"><code>' + esc(d.path) + "</code></p>" +
    '<div class="filter-row">' +
    '<button class="chip-btn primary" id="pd-resume">📋 复制「继续做」指令</button>' +
    '<button class="chip-btn" id="pd-open">📁 打开项目目录</button>' +
    /* 后端 /api/run_generator 一直都在，前端从来没调用过——能力有、够不着。
       对只用 exe 的人这是个断掉的闭环：建项目时状态自动生成，之后再没法重算，
       而文档给的办法是跑 python，他机器上可能根本没有。 */
    (d.has_brain ? '<button class="chip-btn" id="pd-regen">🔄 重算状态</button>' : "") +
    '<button class="chip-btn" id="pd-remove">🗂 移出项目库</button></div>' +
    /* 状态多老要写出来，并且就写在「重算」按钮旁边——把「该按了」和「怎么按」
       放在同一处，否则用户看到按钮也不知道现在该不该按。 */
    (d.state_at
      ? '<p class="muted-note">状态生成于 ' + esc(d.state_at) +
        (d.state_age_days >= 7
          ? ' —— <b>已经 ' + d.state_age_days + ' 天没重算了</b>，上面的数字可能是旧的'
          : "") + "</p>"
      : (d.has_brain
        ? '<p class="muted-note">状态还没生成过 —— 点上面「🔄 重算状态」。</p>' : "")) +
    '<div id="pd-rm-box"></div>';

  if (d.alarms && d.alarms.length) {
    html += '<div class="section"><h3>⚠ 告警（' + d.alarms.length + "）</h3><ul>" +
      d.alarms.map(a => "<li>" + esc(a) + "</li>").join("") + "</ul></div>";
  }
  if (d.outdated && d.outdated.length) {
    html += '<div class="section"><div class="filter-row">' +
      '<button class="chip-btn warn-btn" id="pd-sync">🔄 同步通用件（' + d.outdated.length + " 件落后：体系已升级）</button></div>" +
      '<div id="pd-sync-status"></div></div>';
  }
  if (d.notes && d.notes.length) {
    html += '<div class="section"><h3>📌 进行中（' + d.notes.length + " 注）</h3><ul>" +
      d.notes.map(t => "<li>" + esc(t) + "</li>").join("") + "</ul></div>";
  }
  if (d.handoff_done && !d.handoff_blank) {
    html += '<div class="section"><h3>✅/⏳ 上一窗做完的与没做完的</h3><div class="doc">' + d.handoff_done + "</div></div>";
  } else if (d.handoff_blank) {
    /* 还是出厂模板（一屏 <...> 占位符）。原样渲染出来长得像内容，
       陌生人会以为坏了或自己漏填了。换成一句告诉他下一步。 */
    html += '<div class="section"><h3>✅/⏳ 上一窗做完的与没做完的</h3>' +
      '<p class="muted-note">还没有——这是刚建好的项目。点上面「📋 复制「继续做」指令」' +
      "粘给任何 AI，它做完一段就会把这里填上。</p></div>";
  }
  if (d.traces && d.traces.length) {
    html += '<div class="section"><details><summary>📜 最近轨迹（' + d.traces.length + ' 行 · 自进化的原料）</summary>' +
      '<table style="margin-top:8px"><thead><tr><th>时间</th><th>动作</th><th>证据</th><th>结果</th></tr></thead><tbody>' +
      d.traces.map(t => "<tr><td>" + esc(t.t || t.raw || "") + "</td><td>" + esc(t.act || "") + "</td><td>" + esc(t.ev || "") + "</td><td>" + esc(t.res || "") + "</td></tr>").join("") +
      "</tbody></table></details></div>";
  }
  const docOrder = ["交接", "状态", "在建", "待办", "法典", "宪法", "HANDOFF"];
  const docNames = { "交接": "下一步（05_交接）", "状态": "状态（机器生成）", "在建": "在建（03）",
    "待办": "待办池（04）", "法典": "法典（01）", "宪法": "宪法（00）", "HANDOFF": "HANDOFF 交接文档" };
  let first = true;
  for (const key of docOrder) {
    if (!d.docs[key]) continue;
    const title = docNames[key];
    if (first && (key === "交接" || key === "状态")) {
      html += '<div class="section"><h3>' + title + '</h3><div class="doc">' + d.docs[key] + "</div></div>";
      first = false;
    } else {
      html += '<div class="section"><details><summary>' + title + '</summary><div class="doc" style="margin-top:8px">' +
        d.docs[key] + "</div></details></div>";
    }
  }
  if (!n) {
    html += '<div class="section"><div class="filter-row">' +
      '<button class="chip-btn accent-btn" id="pd-install">⚙️ 一键装系统（只新增 brain\\，不碰项目原文件）</button></div>' +
      '<div id="pd-install-status"></div>' +
      '<p class="muted-note">装完这个项目就有：自动状态、告警、收窗自动更新、进度摘要。原来的文档一个不动。</p></div>';
  }
  if (d.root_md.length) {
    html += '<div class="section"><details><summary>项目根目录文档（' + d.root_md.length + " 个，只列名不渲染内容）</summary>" +
      '<div class="chip-row" style="margin-top:8px">' +
      d.root_md.map(f => '<span class="chip muted">' + esc(f) + "</span>").join("") + "</div></details></div>";
  }
  main.innerHTML = html;
  document.getElementById("pd-back").onclick = () => go(lastPage);
  document.getElementById("pd-open").onclick = () => {
    fetch("api/open_dir", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: d.path }) });
  };
  document.getElementById("pd-resume").onclick = async () => {
    const ok = await copyText(d.resume);
    const b = document.getElementById("pd-resume");
    b.textContent = ok ? "✓ 已复制——粘给任何 AI" : "✗ 复制失败";
  };
  const regenBtn = document.getElementById("pd-regen");
  if (regenBtn) regenBtn.onclick = async () => {
    regenBtn.disabled = true;
    regenBtn.textContent = "重算中…";
    const r = await post("api/run_generator", { path: d.path });
    if (!r.ok) {
      regenBtn.disabled = false;
      regenBtn.textContent = "✗ " + (r.error || "重算失败");
      return;
    }
    // 重进详情页：不刷新的话「最近一次生成」还是旧的，用户会以为没生效
    reloadData(() => goProjectDetail(d.path));
  };
  // 移出项目库：先就地确认，把「文件一个不动」说清楚，别让人以为是删文件
  document.getElementById("pd-remove").onclick = () => {
    const box = document.getElementById("pd-rm-box");
    box.innerHTML = '<div class="bad-box">把 <b>' + esc(d.name) + "</b> 移出项目库？" +
      "<br>只是不再显示在灵台里，<b>" + esc(d.path) + " 里的文件一个都不动</b>，随时能加回来。" +
      '<div class="filter-row" style="margin-top:8px">' +
      '<button class="chip-btn bad-btn" id="pd-rm-yes">确定移出</button>' +
      '<button class="chip-btn" id="pd-rm-no">取消</button></div></div>';
    document.getElementById("pd-rm-no").onclick = () => { box.innerHTML = ""; };
    document.getElementById("pd-rm-yes").onclick = () => {
      box.innerHTML = '<p><span class="spin"></span> 处理中…</p>';
      post("api/project_remove", { path: d.path }).then(r => {
        if (!r.ok) { box.innerHTML = '<div class="bad-box">✗ ' + esc(r.error) + "</div>"; return; }
        reloadData(() => { go("projects"); pjMsg('<div class="ok-box">✓ 已把 <b>' +
          esc(d.name) + "</b> 移出项目库（" + esc(r.how) + "）。文件一个没动。" +
          ' <button class="chip-btn" id="pj-undo2" data-p="' + esc(d.path) + '">撤销</button></div>');
          const u = document.getElementById("pj-undo2");
          if (u) u.onclick = () => post("api/project_restore", { path: u.dataset.p })
            .then(() => reloadData(() => { renderProjects();
              pjMsg('<div class="ok-box">✓ 已撤销</div>'); }));
        });
      });
    };
  };
  const syncBtn = document.getElementById("pd-sync");
  if (syncBtn) {
    syncBtn.onclick = async () => {
      syncBtn.disabled = true;
      document.getElementById("pd-sync-status").innerHTML =
        '<p><span class="spin"></span> 同步中…（专属件永不覆盖）</p>';
      try {
        const r = await fetch("api/sync_project", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ path: d.path }),
        });
        const rj = await r.json();
        if (rj.ok) {
          document.getElementById("pd-sync-status").innerHTML =
            '<div class="ok-box">✓ 已同步 ' + rj.synced + " 件，通用件已是最新。1 秒后刷新…</div>";
          setTimeout(() => goProjectDetail(d.path), 1000);
        } else {
          document.getElementById("pd-sync-status").innerHTML =
            '<div class="bad-box">✗ ' + esc(rj.error) + "</div>";
          syncBtn.disabled = false;
        }
      } catch (e) {
        document.getElementById("pd-sync-status").innerHTML =
          '<div class="bad-box">✗ ' + esc(String(e)) + "</div>";
        syncBtn.disabled = false;
      }
    };
  }
  const installBtn = document.getElementById("pd-install");
  if (installBtn) {
    installBtn.onclick = async () => {
      const box = document.getElementById("pd-install-status");
      installBtn.disabled = true;
      installBtn.style.display = "none";
      const steps = "复制六器官 → 填充宪法/法典 → 生成状态 → 登记装配图 → 重建看板";
      const t0 = Date.now();
      box.innerHTML = '<p><span class="spin"></span> 安装中（已 0 秒）：' + steps + "</p>";
      const timer = setInterval(() => {
        box.innerHTML = '<p><span class="spin"></span> 安装中（已 ' +
          Math.floor((Date.now() - t0) / 1000) + " 秒）：" + steps + "</p>";
      }, 1000);
      try {
        const r = await fetch("api/install_organs", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ path: d.path }),
        });
        const rj = await r.json();
        clearInterval(timer);
        if (rj.ok) {
          const warn = rj.generator && rj.generator.exit !== 0 ? " ⚠ 生成器有告警，看下方状态" : "";
          box.innerHTML = '<div class="ok-box">✓ 装好了：六器官 12 个文件已写入项目的 brain\\ 目录，状态也生成好了' +
            esc(warn) + "。<br>1 秒后自动刷新详情…</div>";
          setTimeout(() => goProjectDetail(d.path), 1000);
        } else {
          installBtn.disabled = false;
          installBtn.style.display = "";
          box.innerHTML = '<div class="bad-box">✗ ' + esc(rj.error) + "</div>";
        }
      } catch (e) {
        clearInterval(timer);
        installBtn.disabled = false;
        installBtn.style.display = "";
        box.innerHTML = '<div class="bad-box">✗ 请求失败：' + esc(String(e)) + "</div>";
      }
    };
  }
}

/* ---------- 首页：仪表（双击后 5 秒内回答"有没有问题 / 怎么开工"） ---------- */
function renderHome() {
  const h = DATA.health;
  const alarmProjects = DATA.projects.filter(p => p.alarms.length);
  const active = DATA.projects.filter(isActive);
  // ⛔ 这个环原来显示「真源在位 59/59」——那是灵台自己的内部一致性检查，
  //    用户根本不知道「真源」是什么，而它占着首页最大最显眼的位置。
  //    换成他真正关心的：手上的项目有几个已经装上系统了。
  //    真源健康度没删，挪到 设置 → 进化审计 里（要维护体系的人才去看）。
  const R = 52, C = 2 * Math.PI * R;
  const pct = DATA.projects.length
    ? Math.round(active.length / DATA.projects.length * 100) : 0;
  const ringColor = alarmProjects.length ? "#fb7185" : "#34d399";
  const ring = '<div class="hero-ring">' +
    '<svg width="128" height="128" viewBox="0 0 128 128"><defs>' +
    '<linearGradient id="ringGrad" x1="0" y1="1" x2="1" y2="0">' +
    '<stop offset="0" stop-color="' + ringColor + '"/><stop offset="1" stop-color="#6ea8fe"/>' +
    "</linearGradient></defs>" +
    '<circle class="ring-bg" cx="64" cy="64" r="' + R + '"/>' +
    '<circle class="ring-val" cx="64" cy="64" r="' + R + '" stroke-dasharray="' + C + '" stroke-dashoffset="' + (C * (1 - pct / 100)).toFixed(1) + '"/>' +
    '</svg><div class="ring-num"><b>' + active.length + "</b><span>/ " + DATA.projects.length +
    " 已装系统</span></div></div>";
  const tiles = [
    ["告警项目", String(alarmProjects.length), alarmProjects.length ? "warn" : "good", ""],
    ["项目总数", String(DATA.projects.length), "good", ""],
    // 「经验库 N」这个数字本身就是坑库的入口：点它进去查坑/记坑。
    // ⛔ 以前数字在这儿、动作在下面一行「🧠 经验库 84 条 · 查坑/记坑 · 设置 · 说一声」，
    //    同一屏把条数说了两遍，而那一行还夹在告警和项目列表中间。
    ["经验库 · 点开查坑/记坑", String(DATA.pitfall.rows.length), "good", "h-tile-pitfall"],
  ];
  let html = '<div class="hero">' + ring + tiles.map(t =>
    '<div class="tile ' + t[2] + (t[3] ? " clickable" : "") + '"' + (t[3] ? ' id="' + t[3] + '"' : "") +
    '><div class="tile-num">' + esc(t[1]) + '</div><div class="tile-label">' + esc(t[0]) + "</div></div>"
  ).join("") + "</div>";

  /* ⛔ 这里不放任何「复制开工指令」的按钮。
       开工必须绑定到**一个具体项目**，而首页不知道用户今天想开哪个——
       原来那个「📋 复制开窗三句话」就是这么坏的：它复制出「读本项目
       brain\01_法典.md」，「本项目」是哪个没说，是个没有根的相对路径，
       粘给 AI 只能反问或瞎猜。改成「猜最近动过的那个」仍然是猜。
       正确的入口本来就在：点项目卡 → 详情页「复制『继续做』指令」，
       那份带这台机器上的真实绝对路径。首页只负责告诉他去哪点。 */
  // ⛔ 标题原来是「今日开工」——它承诺了一个**时间**，而这张卡跟今天没关系，
  //    它就是入口；返回的用户也不是「今天才开工」。改成卡里内容真正在回答的那个问题。
  html += '<div class="section card start-card"><h2>项目开工说明</h2>' +
    // 「红绿灯全绿 / 收窗 / 分段落盘」都是自家说法，第一次来的人看不懂。
    // 句子按「删掉它对方的判断会变吗」删过一轮：去掉「下面任意」「详情页」
    // 「指令」「直接开工」「每做完一段」——删了都不改变他下一步怎么做。
    '<p class="muted-note">' + (active.length
      ? "点项目卡 → 复制「继续做」→ 粘给任何 AI。进度它自己写回文件，不用你收尾。"
      : "还没有项目。先建一个，或者把电脑上已经在做的加进来。") + "</p>" +
    '<div class="filter-row">' +
    '<button class="chip-btn accent-btn" id="h-newproj">＋ 新项目</button>' +
    // 「新项目」是从零建一个；「添加已有」是把电脑上已经存在的项目收进来。
    // 两回事，用户想收录已有项目时不该只能去项目页找
    '<button class="chip-btn" id="h-addproj">📂 添加已有项目</button>' +
    // 「深查（重算全部真源）」——用户不知道什么叫真源，他只想让页面反映硬盘上的实况
    '<button class="chip-btn" id="h-refresh">🔄 重新扫描</button></div>' +
    '<p class="muted-note">数据更新于 ' + esc(DATA.generated_at) + "</p></div>";

  const ev = DATA.evolution || {};
  const staleN = (ev.stale_handoffs || []).length;
  // 够不着的项目要出声：外接硬盘拔了/网络盘断了，项目从列表消失而不吭一声，
  // 人只会以为东西丢了
  const gone = DATA.unreachable_projects || [];
  // ⛔ 首页只放**用户要处理的事**。
  //    「断头 / 同名双份」是装配图指针的一致性问题，属于体系自检，挪去 设置 → 进化审计；
  //    留在这儿的是他真的要动手的两件：项目够不着了、交接太久没更新。
  if (staleN || gone.length) {
    html += '<div class="section"><h2>🔴 先看这里</h2><ul>' +
      gone.map(p => "<li>📴 够不着：<code>" + esc(p) +
        "</code>——外接硬盘没插？网络盘断了？目录挪走了？（它还记在你的项目清单里）</li>").join("") +
      // 提到哪儿就得能点过去。⛔ 这条以前指向「设置→进化审计」，那页已经没了——
      //    而且要动手的地方本来就在项目库：去那个项目里接着做，交接自然就更新了。
      (staleN ? "<li>🟡 有 " + staleN + " 个项目的交接超 7 天没更新——" +
        '<a href="#" class="h-goto-projects">去项目库看 →</a></li>' : "") +
      "</ul></div>";
  }
  if (alarmProjects.length) {
    html += '<div class="section"><h2>⚠ 有告警的项目</h2><div class="cards">' +
      alarmProjects.map(slimCard).join("") + "</div></div>";
  }
  /* ⛔ 这里原来有一行「🧠 经验库 84 条 · 查坑/记坑 · 设置 · 说一声 →」，
     夹在告警和项目列表中间。三样东西各自都放错了地方：
       · 条数——顶部大格子里已经有一个「经验库 84」，同一屏说了两遍；
       · 查坑/记坑、设置——它们是**导航**，被塞进正文只因为侧栏里没有它们的入口；
       · 说一声——反馈链接，不该打断「告警 → 我的项目」这条视线。
     现在：数字和动作合并进那个大格子（点它进坑库）、设置进侧栏、反馈去侧栏底部。 */
  const rest = DATA.projects.length - active.length;
  html += '<div class="section"><h2>进行中的项目（' + active.length + '）</h2><div class="cards">' +
    active.slice(0, 6).map(slimCard).join("") + "</div>" +
    (active.length > 6 ? '<p class="muted-note">更多见 <a href="#" class="h-goto-projects">项目库 →</a></p>' : "") +
    /* 空状态得给条路。首跑向导有引导，点了「跳过」落到这儿反而只剩一个 0——
       陌生人第一次打开卡在这一屏，前面所有功夫都白做。 */
    (DATA.projects.length === 0
      ? '<p class="muted-note">还一个都没有。点上面「＋ 新项目」建第一个，' +
        '或者「添加已有项目」把手上正在做的加进来。</p>'
      : "") +
    /* ⛔ rest 为 0 时别再写「其余 0 个…去项目库看」——那是让人点过去看一片空白。 */
    (rest > 0
      ? '<p class="muted-note">其余 ' + rest +
        ' 个未装系统的项目（可能没完工）→ <a href="#" class="h-goto-projects">去项目库看，全部可点开续做 →</a></p>'
      : "") + "</div>";

  main.innerHTML = html;
  attachCardClicks();
  document.getElementById("h-newproj").onclick = () => go("newproj");
  const hAdd = document.getElementById("h-addproj");
  if (hAdd) hAdd.onclick = () => { go("projects"); addProjectHere(); };
  const tp = document.getElementById("h-tile-pitfall");
  if (tp) tp.onclick = () => go("pitfall");
  main.querySelectorAll(".h-goto-projects").forEach(a => {
    a.onclick = e => { e.preventDefault(); go("projects"); };
  });
  document.getElementById("h-refresh").onclick = async () => {
    const b = document.getElementById("h-refresh");
    b.disabled = true; b.textContent = "🔄 扫描中…";
    try {
      const r = await fetch("api/refresh", { method: "POST" });
      const d = await r.json();
      if (d.generated_at) { DATA = d; renderHome(); }
      else { b.disabled = false; b.textContent = "✗ " + (d.error || "扫描失败"); }
    } catch (e) {
      b.disabled = false; b.textContent = "✗ 扫描失败";
    }
  };
}

/* ---------- 项目页：全部可点；装系统的在前，未装的折叠区同样可点 ---------- */
let PJ_QUERY = "";

function pjMatch(p) {
  const q = PJ_QUERY.trim().toLowerCase();
  if (!q) return true;
  return (p.name || "").toLowerCase().includes(q) ||
         (p.path || "").toLowerCase().includes(q);
}

function renderProjects() {
  const hits = DATA.projects.filter(pjMatch);
  const active = hits.filter(isActive)
    .sort((a, b) => (organN(b) - organN(a)) || (b.alarms.length - a.alarms.length));
  const rest = hits.filter(p => !isActive(p));
  const gone = DATA.excluded_projects || [];

  let html = '<div class="section"><div class="filter-row">' +
    '<h2 style="border:0;margin:0;flex:1">项目库（' + DATA.projects.length + "）</h2>" +
    '<button class="chip-btn primary" id="pj-add">📂 添加项目…</button>' +
    '<button class="chip-btn" id="pj-manage">🗂 管理</button></div>' +
    // 项目一多就只能靠眼睛扫——坑库有搜索，项目库也该有
    (DATA.projects.length > 6
      ? '<div class="filter-row" style="margin-top:8px">' +
        '<input id="pj-q" type="search" placeholder="搜项目名或路径" value="' + esc(PJ_QUERY) + '">' +
        (PJ_QUERY ? '<span class="muted-note">找到 ' + hits.length + " 个</span>" : "") +
        "</div>"
      : "") +
    '<div id="pj-msg"></div></div>';

  if (PJ_QUERY && !hits.length) {
    html += '<div class="section"><p class="muted-note">没有匹配「' + esc(PJ_QUERY) +
      "」的项目。换个词，或者清空搜索框看全部。</p></div>";
  } else if (!DATA.projects.length) {
    // 空状态：别只显示两个空列表，要告诉人下一步干什么
    html += '<div class="section"><div class="ok-box">项目库还是空的。' +
      "<br>点上面的「📂 添加项目」把你已有的项目收进来（选中文件夹即可，" +
      "灵台只读不写，不会动你的文件）；" +
      "不记得放哪了就用「🔍 帮我找找」扫一遍。" +
      (gone.length ? "<br>另外你有 " + gone.length + " 个移出过的项目，展开下面就能拿回来。" : "") +
      "</div></div>";
  } else {
    html += '<div class="section"><h3>装系统的项目（' + active.length + "）</h3>" +
      (active.length ? '<div class="cards">' + active.map(slimCard).join("") + "</div>"
                     : '<p class="muted-note">还没有装过六器官的项目——点开任一项目可以一键装。</p>') +
      "</div>";
    if (rest.length) {
      html += '<div class="section"><details open><summary>未装系统的项目（' + rest.length +
        " · 没完工也能点开续做——点进去看它的交接/施工图）</summary>" +
        '<div class="cards" style="margin-top:10px">' +
        rest.map(slimCard).join("") + "</div></details></div>";
    }
  }

  if (gone.length) {
    html += '<div class="section"><details><summary>已移出项目库的（' + gone.length +
      " · 文件都还在，随时能拿回来)</summary><div style='margin-top:8px'>" +
      gone.map(g =>
        '<div class="q-label inline"><code>' + esc(g.path) + "</code>" +
        (g.exists ? "" : ' <span class="chip muted">文件夹已不在磁盘上</span>') +
        (g.exists ? ' <button class="chip-btn pj-restore" data-p="' + esc(g.path) +
          '">恢复显示</button>' : "") + "</div>").join("") +
      "</div></details></div>";
  }

  main.innerHTML = html;
  attachCardClicks();
  bindProjectManage();
  const q = document.getElementById("pj-q");
  if (q) {
    // 边打边筛。重渲染会让输入框失焦，所以打完立刻把光标和插入点还回去
    q.oninput = () => {
      PJ_QUERY = q.value;
      const pos = q.selectionStart;
      keepScroll(renderProjects);
      const q2 = document.getElementById("pj-q");
      if (q2) { q2.focus(); try { q2.setSelectionRange(pos, pos); } catch (e) {} }
    };
  }
}

/* 管理模式：卡片上出现「移出」，点了先就地确认，不用 window.confirm（会卡住页面） */
let PJ_MANAGE = false;
function bindProjectManage() {
  const add = document.getElementById("pj-add");
  if (add) add.onclick = () => addProjectHere();
  const mg = document.getElementById("pj-manage");
  if (mg) {
    mg.textContent = PJ_MANAGE ? "✓ 完成管理" : "🗂 管理";
    mg.onclick = () => { PJ_MANAGE = !PJ_MANAGE; keepScroll(renderProjects); };
  }
  main.querySelectorAll(".pj-restore").forEach(b => {
    b.onclick = ev => {
      ev.stopPropagation();
      post("api/project_restore", { path: b.dataset.p }).then(r => {
        if (!r.ok) { pjMsg('<div class="bad-box">✗ ' + esc(r.error) + "</div>"); return; }
        reloadData(() => {
          keepScroll(renderProjects);
          pjMsg('<div class="ok-box">✓ 已恢复显示：<code>' + esc(b.dataset.p) + "</code></div>");
        });
      });
    };
  });
  if (PJ_MANAGE) {
    main.querySelectorAll(".card.clickable").forEach(c => {
      const p = c.dataset.path;
      const bar = document.createElement("div");
      bar.className = "chip-row";
      bar.style.marginTop = "6px";
      bar.innerHTML = '<button class="chip-btn bad-btn pj-rm" data-p="' + esc(p) + '">移出项目库</button>';
      c.appendChild(bar);
      c.onclick = null;   // 管理模式下不跳详情，免得误触
    });
    main.querySelectorAll(".pj-rm").forEach(b => {
      b.onclick = ev => {
        ev.stopPropagation();
        const p = b.dataset.p;
        const box = b.parentElement;
        box.innerHTML = '<span class="muted-note">移出后只是不再显示，<b>' + esc(p) +
          " 里的文件一个都不动</b>。</span>" +
          '<button class="chip-btn bad-btn pj-rm-yes" data-p="' + esc(p) + '">确定移出</button>' +
          '<button class="chip-btn pj-rm-no">取消</button>';
        box.querySelector(".pj-rm-no").onclick = e2 => { e2.stopPropagation(); keepScroll(renderProjects); };
        box.querySelector(".pj-rm-yes").onclick = e2 => {
          e2.stopPropagation();
          post("api/project_remove", { path: p }).then(r => {
            if (!r.ok) { pjMsg('<div class="bad-box">✗ ' + esc(r.error) + "</div>"); return; }
            reloadData(() => {
              keepScroll(renderProjects);
              pjMsg('<div class="ok-box">✓ 已移出项目库（' + esc(r.how) + "）。" +
                (r.files_untouched ? "文件夹和里面的文件一个没动。" : "") +
                ' <button class="chip-btn" id="pj-undo" data-p="' + esc(p) + '">撤销</button></div>');
              const u = document.getElementById("pj-undo");
              if (u) u.onclick = () => {
                post("api/project_restore", { path: u.dataset.p }).then(() =>
                  reloadData(() => { renderProjects(); pjMsg('<div class="ok-box">✓ 已撤销</div>'); }));
              };
            });
          });
        };
      };
    });
  }
}

function pjMsg(h) {
  const b = document.getElementById("pj-msg");
  if (b) b.innerHTML = h;
}
function post(path, payload) {
  return fetch(path, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
  }).then(r => r.json()).catch(e => ({ ok: false, error: String(e) }));
}
function reloadData(cb) {
  fetch("data.json").then(r => r.json()).then(d => { DATA = d; if (cb) cb(); });
}

/* 驾驶舱里随时加项目：同样是系统对话框 */
function addProjectHere() {
  pjMsg('<p class="muted-note"><span class="spin"></span> 已弹出「浏览文件夹」窗口，' +
    "选好项目所在的文件夹点确定。（没看见就看看任务栏）</p>");
  post("api/pick_folder", { title: "选择要添加的项目文件夹" }).then(r => {
    if (!r.ok) { pjMsg('<div class="bad-box">✗ ' + esc(r.error) + "</div>"); return; }
    if (r.cancelled) { pjMsg(""); return; }
    const finish = (whole) => post("api/project_add", { path: r.path, whole: whole }).then(a => {
      if (!a.ok) { pjMsg('<div class="bad-box">✗ ' + esc(a.error) + "</div>"); return; }
      reloadData(() => {
        keepScroll(renderProjects);
        pjMsg(a.dup
          ? '<div class="ok-box">' + esc(a.reason || "已经加过了") + "</div>"
          : '<div class="ok-box">✓ 已添加 <code>' + esc(r.path) + "</code>，现在共 " +
            a.projects_now + " 个项目</div>");
      });
    });
    if (r.child_candidates >= 2) {
      pjMsg('<div class="ok-box">选中了 <code>' + esc(r.path) + "</code>——" +
        "它里面还有 " + r.child_candidates + " 个子文件夹。" +
        '<div class="filter-row" style="margin-top:8px">' +
        '<button class="chip-btn primary" id="pa-one">就加这一个</button>' +
        '<button class="chip-btn" id="pa-all">把里面的都加进来</button></div></div>');
      document.getElementById("pa-one").onclick = () => finish(false);
      document.getElementById("pa-all").onclick = () => finish(true);
    } else {
      finish(false);
    }
  });
}

/* ---------- 坑库回流：把一条通用坑送回主库 ----------
   ⛔ 不发任何网络请求，不上传任何数据——只是拼一个 GitHub「新建 Issue」的链接，
      内容预填好，发不发由用户在 GitHub 上自己按。零遥测这条承诺不能因为
      「想收集贡献」就打折。 */
const REPO_URL = "https://github.com/xieyi138-star/lingtaios";
function sharePitfall(p, code) {
  const title = "[坑] " + String(p.pit || "").slice(0, 60);
  const body = [
    "> 判据：换一个项目、换一套技术栈，这条还成立吗？成立才该进主库。",
    "",
    "**分区**：" + (p.section || ""),
    "",
    "## 一句话坑",
    p.pit || "",
    "",
    "## 防法（照做即可）",
    p.fix || "",
    "",
    "## 失效判据（防的事被结构性消除即删）",
    p.invalid_when || "",
    "",
    "## 出处",
    p.source || "（未填）",
    "",
    "## 署名（会写进主库的「贡献者」列，留空则匿名收录）",
    "",
    "",
    "---",
    "由灵台从本地坑库导出" + (code ? "（本地编号 " + code + "）" : "") + "。",
    "我确认这条**不含**任何涉密信息（IP / 密钥 / 客户数据）。",
  ].join("\n");
  const url = REPO_URL + "/issues/new?labels=" + encodeURIComponent("坑库贡献") +
    "&title=" + encodeURIComponent(title) + "&body=" + encodeURIComponent(body);
  window.open(url, "_blank", "noopener");
}

/* ---------- 导出「我的踩坑档案」 ----------
   用户不会为了帮你而公开，会为了**自己**而公开——他记的坑是踩过的实战证据，
   是能拿出去的专业履历。所以给他一份能直接发出去的东西，他图专业形象，
   顺带把方法库带出去。（Obsidian Publish 就是这个逻辑：用户想要的是发布本身。）
   ⚠️ 局限：现在识别不出「内置的」和「他自己记的」，所以导出的是整个库并如实标注。
      要精确区分，得在首跑时把内置编号集合存下来——等有人真的在用了再做。 */
function exportPitfallArchive() {
  const rows = (DATA.pitfall && DATA.pitfall.rows) || [];
  const secs = (DATA.pitfall && DATA.pitfall.sections) || [];
  const nProj = (DATA.projects || []).length;
  const L = [];
  L.push("# 我的踩坑档案");
  L.push("");
  L.push("> 用灵台管着 " + nProj + " 个项目，经验库 " + rows.length + " 条。");
  L.push("> 每条都带**防法**和**失效判据**——防的事被结构性解决了就退休，");
  L.push("> 不是一个只增不减、最后没人看的清单。");
  L.push("");
  for (const s of secs) {
    const inSec = rows.filter(r => r.__section === s.name);
    if (!inSec.length) continue;
    L.push("## " + s.name + "（" + inSec.length + " 条）");
    L.push("");
    for (const r of inSec) {
      L.push("**" + (r["编号"] || "") + "　" + (r["一句话坑"] || "") + "**");
      L.push("");
      L.push("- 防法：" + (r["防法（照做即可）"] || ""));
      L.push("- 失效判据：" + (r["失效判据"] || ""));
      if (String(r["贡献者"] || "").trim()) L.push("- 贡献者：" + r["贡献者"]);
      L.push("");
    }
  }
  L.push("---");
  L.push("");
  L.push("方法库来自 [灵台 LingTai OS](" + REPO_URL + ")：让任何 AI 按验证过的方法做事，");
  L.push("而不是按它猜的。本档案含灵台内置的方法论坑库与我自己补充的条目。");
  const blob = new Blob([L.join("\n")], { type: "text/markdown;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "我的踩坑档案.md";
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
}

/* ---------- 坑库：搜索 + 分区 + 分页 ---------- */
let PIT_ROWS = [];
const PIT_PAGE = 20;
function renderPitfall() {
  PIT_ROWS = DATA.pitfall.rows;
  // `__` 开头 = 后端内部字段（如 __section 是给分区筛选用的），不该出现在表格里
  const cols = (DATA.pitfall.columns || []).filter(c => !String(c).startsWith("__"));
  const sections = DATA.pitfall.sections;
  let html = '<div class="section"><h2>坑库（' + PIT_ROWS.length + " 条 · 踩坑前查一眼）</h2>" +
    '<p class="muted-note">点任意一行，展开它的出处和失效判据。</p>' +
    '<div class="filter-row"><input id="pit-q" type="search" placeholder="搜索坑或防法">' +
    '<select id="pit-sec"><option value="">全部分区</option>' +
    sections.map(s => '<option value="' + esc(s.name) + '">' + esc(s.name) + "（" + s.count + "）</option>").join("") +
    '</select><button class="chip-btn accent-btn" id="pit-add">＋ 记一条坑</button>' +
    '<button class="chip-btn" id="pit-export" title="导出成一份可以直接发出去的 markdown">📤 导出档案</button></div>' +
    '<div id="pit-form-wrap" style="display:none"><div class="form-grid">' +
    '<label>分区<select id="pf-section">' +
    sections.map(s => '<option>' + esc(s.name) + "</option>").join("") + "</select></label>" +
    '<label>一句话坑<input id="pf-pit" placeholder="踩的是什么坑"></label>' +
    '<label>防法（照做即可）<input id="pf-fix" placeholder="下次怎么做就不踩"></label>' +
    '<label>出处<input id="pf-src" placeholder="哪个项目/窗口"></label>' +
    '<label>失效判据（必填）<input id="pf-inv" placeholder="防的事被结构性消除即删，如：XX工具修复后"></label>' +
    '</div><div class="filter-row"><button class="chip-btn primary" id="pf-go">入库</button>' +
    '<span class="muted-note">防法/失效判据缺一不放行——涨有门槛</span></div><div id="pf-result"></div></div>' +
    '<table id="pit-table"><thead><tr>' + PIT_MAIN.map(c => "<th>" + esc(c) + "</th>").join("") + "</tr></thead><tbody></tbody></table>" +
    '<div class="filter-row"><button class="chip-btn" id="pit-more">显示更多</button>' +
    '<span class="muted-note" id="pit-count"></span></div></div>';
  main.innerHTML = html;
  document.getElementById("pit-q").oninput = drawPitRows;
  document.getElementById("pit-sec").onchange = drawPitRows;
  document.getElementById("pit-more").onclick = drawPitRows;
  document.getElementById("pit-add").onclick = () => {
    const w = document.getElementById("pit-form-wrap");
    w.style.display = w.style.display === "none" ? "" : "none";
  };
  document.getElementById("pit-export").onclick = exportPitfallArchive;
  document.getElementById("pf-go").onclick = async () => {
    const payload = {
      section: document.getElementById("pf-section").value,
      pit: document.getElementById("pf-pit").value.trim(),
      fix: document.getElementById("pf-fix").value.trim(),
      source: document.getElementById("pf-src").value.trim(),
      invalid_when: document.getElementById("pf-inv").value.trim(),
    };
    const r = await fetch("api/add_pitfall", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const rj = await r.json();
    const out = document.getElementById("pf-result");
    if (rj.ok) {
      // 记完这一刻是问「要不要贡献」的最佳时机——他刚踩完，最清楚这坑通不通用。
      // 「用的人越多方法越准」这句话，只有把坑收得回来才不是空话。
      out.innerHTML = '<div class="ok-box">✓ 已入库（编号 ' + esc(rj.code) + "）</div>" +
        '<div class="section" style="margin-top:10px"><b>🌱 这条是跨项目通用的吗？</b>' +
        '<p class="muted-note">判断只有一句：<b>换个项目、换套技术栈，这条还成立吗？</b>' +
        "成立就贡献回主库，下一版所有人的 AI 都按更准的方法做事。<br>" +
        "只在你这个项目成立的，留在自己库里同样有用，不用贡献。</p>" +
        '<div class="filter-row"><button class="chip-btn accent-btn" id="pf-share">🌱 贡献回主库</button>' +
        '<span class="muted-note">只会替你把内容填进 GitHub 表单，发不发你自己按——不上传任何东西</span></div></div>';
      const sh = document.getElementById("pf-share");
      if (sh) sh.onclick = () => sharePitfall(payload, rj.code);
      fetch("data.json").then(r2 => r2.json()).then(dd => { DATA = dd; });
    } else {
      out.innerHTML = '<div class="bad-box">✗ ' + esc(rj.error) + "</div>";
    }
  };
  drawPitRows();
}
let pitLimit = PIT_PAGE;
// 查坑的人只要两件事：这是什么坑、怎么防。其余四列是**元数据**：
// 「出处」写的是记录者自己项目的代号（Savant / stock-agent / NEXUS …），别人看不懂；
// 「触发」是内部计数；「失效判据」只在决定要不要删这条坑时才用；「入库」是日期。
// 七列全平铺出来，表格宽到要横向滚，真正有用的那两列反而被挤没了。
// 所以主表只留三列，元数据点开那一行才显示——搜索仍然搜全部列，不影响找得到。
const PIT_MAIN = ["编号", "一句话坑", "防法（照做即可）"];
function drawPitRows() {
  const q = (document.getElementById("pit-q").value || "").toLowerCase();
  const sec = document.getElementById("pit-sec").value;
  // `__` 开头 = 后端内部字段（如 __section 是给分区筛选用的），不该出现在表格里
  const cols = (DATA.pitfall.columns || []).filter(c => !String(c).startsWith("__"));
  const meta = cols.filter(c => PIT_MAIN.indexOf(c) < 0);
  const rows = PIT_ROWS.filter(r =>
    (!sec || r.__section === sec) &&
    (!q || cols.some(c => String(r[c] || "").toLowerCase().includes(q))));
  const shown = rows.slice(0, pitLimit);
  document.querySelector("#pit-table tbody").innerHTML = shown.map((r, i) =>
    '<tr class="pit-row" data-i="' + i + '" style="cursor:pointer">' +
    PIT_MAIN.map(c => "<td>" + esc(r[c]) + "</td>").join("") + "</tr>" +
    '<tr class="pit-meta" data-i="' + i + '" style="display:none"><td colspan="' +
    PIT_MAIN.length + '"><span class="muted-note">' +
    meta.filter(c => String(r[c] || "").trim()).map(c => esc(c) + "：" + esc(r[c])).join("　·　") +
    '</span>　<button class="chip-btn pit-share" data-i="' + i +
    '" title="换个项目、换套技术栈还成立的，才该进主库">🌱 贡献回主库</button>' +
    /* 退休一条坑，该发生在**你正看着它**的时候，而不是在另一个页面上勾一张清单。
       ⛔ 措辞不用「删除」：用户看到「删除」第一反应是「我的文件会不会没了」。
          说清楚只动这一行、别的什么都不碰。 */
    '　<button class="chip-btn pit-retire" data-i="' + i +
    '" title="它防的事已经不可能发生了，就让它退休">这条不用了</button>' +
    '<span class="pit-retire-box" data-i="' + i + '"></span></td></tr>').join("");
  document.querySelectorAll("#pit-table .pit-row").forEach(tr => {
    tr.onclick = () => {
      const m = document.querySelector('#pit-table .pit-meta[data-i="' + tr.dataset.i + '"]');
      if (m) m.style.display = m.style.display === "none" ? "" : "none";
    };
  });
  document.querySelectorAll("#pit-table .pit-share").forEach(b => {
    b.onclick = e => {
      e.stopPropagation();          // 别把展开/收起也一起触发了
      const r = shown[+b.dataset.i];
      sharePitfall({
        section: r.__section, pit: r["一句话坑"], fix: r["防法（照做即可）"],
        source: r["出处"], invalid_when: r["失效判据"],
      }, r["编号"]);
    };
  });
  document.querySelectorAll("#pit-table .pit-retire").forEach(b => {
    b.onclick = e => {
      e.stopPropagation();
      const r = shown[+b.dataset.i];
      const box = document.querySelector('#pit-table .pit-retire-box[data-i="' + b.dataset.i + '"]');
      box.innerHTML = "　让 <b>" + esc(r["编号"]) + "</b> 退休？" +
        '<span class="muted-note">只去掉经验库里这一行，你的项目和文件一个都不动。</span>' +
        ' <button class="chip-btn bad-btn pit-retire-yes">确定</button>' +
        ' <button class="chip-btn pit-retire-no">取消</button>';
      box.querySelector(".pit-retire-no").onclick = ev => { ev.stopPropagation(); box.innerHTML = ""; };
      box.querySelector(".pit-retire-yes").onclick = async ev => {
        ev.stopPropagation();
        box.textContent = "　处理中…";
        const res = await post("api/audit_delete", { kind: "pitfall", ids: [r["编号"]] });
        if (!res.ok) { box.innerHTML = '　<span class="muted-note">✗ ' + esc(res.error) + "</span>"; return; }
        reloadData(() => renderPitfall());
      };
    };
  });
  document.getElementById("pit-count").textContent = "显示 " + shown.length + " / " + rows.length;
  document.getElementById("pit-more").style.display = rows.length > shown.length ? "" : "none";
  if (document.getElementById("pit-more").style.display === "none") pitLimit = PIT_PAGE;
  else if (pitLimit < rows.length) pitLimit += PIT_PAGE;
}

/* renderEvolutionInto()（候选删除 / C 类到期 / 判据强度 / 待补判据 / 断头双份 /
   通用件落后 + 一个「🗑 删除所选」批量按钮）整个删了。三条理由：
     · 它们既不是用户能判的，也不是他想判的——那是维护这套体系的人的活；
     · 「通用件落后」现在系统自己同步掉了（sync_probe），根本不该问；
     · 一个摆着「删除」按钮的清单，用户第一反应是「我的文件会不会没了」。
   真正需要保留的能力只有一个：让某一条坑退休。它现在长在坑库那一行上——
   你正看着那条坑的时候点「这条不用了」，比在另一个页面勾清单诚实得多。 */

/* ---------- 我的文件 ---------- */
function renderSystem() {
  /* ⛔ 这一页原来叫「设置」，两个 tab：整理 / 换机。逐项问「用户会据此做什么」之后
     发现**大部分根本不是设置，是维护者的工作台**：
       · 「每周看一次，勾选 → 点删除」——要求用户定期做维护，他不会；
       · 「交接超 7 天没更新」——首页「先看这里」已经有同一条，重复；
       · 候选删除 / C 类到期 / 判据强度 / 待补判据 / 真源在位 / 断头双份
         ——全是维护坑库和体系的人才看的；
       · 「🔧 体系自检」的标签自己写着**「一般不用管」**——那它凭什么占一屏。
     用户真要的只有两件：**我的东西在哪**（「记忆归你」的兑现处）、**换机怎么办**。
     整页就只剩这两件。 */
  main.innerHTML = '<div class="section"><h2>我的文件</h2><div id="sys-box"></div></div>';
  renderSysTab();
}

function renderSysTab() {
  const box = document.getElementById("sys-box");
  {
    // ⛔ 这页原来只写「clone skills 仓库 → python install.py → python dashboard.py」——
    //    对下载 exe 用的人**直接是错的**：他手上根本没有源码，也没装 Python。
    //    绝大多数用户走的是 exe 那条路，所以先写它。
    const roots = DATA.root_status;
    // 「方法」页去掉了：那四篇是**给 AI 读的文件**，不是给人在网页里翻的——
    // 用户的路径是「复制继续做指令 → 粘给 AI」，AI 自己去读那些 md。
    // 但不能就此藏起来：「记忆归你」是产品第一承诺，得让人知道东西在哪、能自己改。
    const skills = (roots.find(r => r.alias === "SKILLS") || {}).path || "";
    /* ⛔ 这一页按「一个完全不懂技术的人」重写过。原来的毛病逐条：
         · 「纯文本文件」「方法论」「六器官」「brain\」「方法体系」——他一个都不懂；
         · 列了四个内部文件名（常驻薄核/道法术/项目交付法/核心大脑）——书名一样，看不懂；
         · 甩一长串 C:\Users\...\dist\project-delivery 让他自己看——他要的是「打开」；
         · **整整一段「用源码的：clone 仓库 / python install.py」**——他根本不需要，
           摆在那儿只会让他以为自己少做了一步、是不是还得装 Python。开发者看 README。
       重写的判据：说他**会失去什么**，不说文件叫什么；能给按钮就不给路径；
       想看细节的自己点开。 */
    box.innerHTML =
      '<p>你的东西全在这台电脑上，灵台<b>不往外传</b>。用记事本就能打开、自己改。</p>' +
      (skills ? '<div class="filter-row"><button class="chip-btn primary" id="sys-open-method">📂 打开我的文件夹</button></div>' : "") +
      "<h3 style=\"margin-top:20px\">换新电脑</h3>" +
      "<p>把 <code>lingtaios.exe</code> <b>所在的整个文件夹</b>拷过去，双击接着用。</p>" +
      '<p class="muted-note">⛔ 只拷 <code>lingtaios.exe</code> 这一个文件 = 你记的东西全没了<br>' +
      "你的项目文件不用搬，还在原来的地方。</p>" +
      /* ⛔ 这里删掉的东西，删的理由都是同一条：**展示出来对用户是负担**。
           · 文件清单（规矩/坑/项目资料）——他点了「打开我的文件夹」自己就看见了，
             写成清单是盘点，不是他要做的事；
           · 一长串路径——有按钮就不需要路径；
           · 「扫描位置」表——项目没出现时的解法是首页「添加已有项目」，不是让他读这张表；
           · 「复制一段话让 AI 学方法」——傻瓜路径上没人会用它，连后端接口一起删了，
             否则又是一处没人调用的死代码。 */
      "";
    const om = document.getElementById("sys-open-method");
    if (om) {
      om.onclick = () => fetch("api/open_dir", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: skills + "\\project-delivery" }),
      });
    }
  }
}

/* ---------- 新项目（向导 B · 填表即装） ---------- */
function renderNewProject() {
  // ⛔ 落点选项必须按这台机器的实况生成。
  // 原来是写死的三条，头一条还印着「Nexus 根（C:\nexus_local 下）」——
  // 别人的电脑上根本没这个目录，选了直接报「所选根未配置」，
  // 等于把作者的机器路径当成了所有人的默认值。
  const rs = (DATA.root_status || []).filter(r => r.exists && r.alias !== "SKILLS");
  const label = { NEXUS: "Nexus 根", D: "D 盘根", HOME: "用户主目录" };
  const val = { NEXUS: "nexus", D: "d", HOME: "custom" };
  const opts = rs.map(r =>
    '<option value="' + (val[r.alias] || "custom") + '" data-path="' + esc(r.path) + '">' +
    esc(label[r.alias] || r.alias) + "（" + esc(r.path) + "）</option>").join("");
  let html = '<div class="section"><div class="filter-row">' +
    '<button class="chip-btn" id="np-back">← 返回</button>' +
    '<h2 style="border:0;margin:0;flex:1">新项目 · 填表 → 点创建 → 全部自动装好</h2></div>' +
    '<div class="form-grid">' +
    '<label>项目名<input id="np-name" placeholder="如：my-tool"></label>' +
    '<label>落点<select id="np-root">' + opts +
    '<option value="custom">选一个文件夹…</option></select></label>' +
    '<label id="np-custom-wrap" style="display:none">建到这个文件夹下' +
    '<span class="filter-row"><input id="np-custom" placeholder="点右边按钮选，或直接粘路径" style="flex:1">' +
    '<button class="chip-btn" id="np-pick" type="button">📂 浏览…</button></span></label>' +
    '</div>' +
    '<h4>终极之果（至少填 1 行；果落在用户身上，不是过程量）</h4>' +
    '<div id="np-goals">' +
    [0, 1, 2].map(i =>
      '<div class="form-grid"><input data-g="name' + i + '" placeholder="指标名（如：客户 5 分钟上手）">' +
      '<input data-g="def' + i + '" placeholder="定义（怎么算达成）">' +
      '<input data-g="line' + i + '" placeholder="达标线（如：≤5 分钟）"></div>').join("") +
    '</div>' +
    '<h4>红线（一行一条，绝不做的事）</h4>' +
    '<textarea id="np-red" rows="3" placeholder="🔴 不动生产数据&#10;🔴 不花预算外的一分钱"></textarea>' +
    '<div class="filter-row"><button class="chip-btn primary" id="np-go">🚀 创建（自动装六器官+跑状态生成器）</button></div>' +
    '<div id="np-result"></div></div>';
  main.innerHTML = html;
  document.getElementById("np-back").onclick = () => go("home");
  const npRoot = document.getElementById("np-root");
  const npWrap = document.getElementById("np-custom-wrap");
  const npCustom = document.getElementById("np-custom");
  const syncNpRoot = () => {
    const opt = npRoot.options[npRoot.selectedIndex];
    const isCustom = npRoot.value === "custom";
    npWrap.style.display = isCustom ? "" : "none";
    // HOME 这类根也走 custom 通道，但路径是现成的，直接填好省得用户再选一次
    if (isCustom && opt && opt.dataset.path) npCustom.value = opt.dataset.path;
  };
  npRoot.onchange = syncNpRoot;
  syncNpRoot();
  // 已经有系统文件夹对话框了，就别让人手打路径
  document.getElementById("np-pick").onclick = () => {
    const b = document.getElementById("np-pick");
    b.disabled = true; b.textContent = "选择中…";
    post("api/pick_folder", { title: "选择新项目建在哪个文件夹下" }).then(r => {
      b.disabled = false; b.textContent = "📂 浏览…";
      if (r.ok && !r.cancelled) npCustom.value = r.path;
      else if (!r.ok) document.getElementById("np-result").innerHTML =
        '<div class="bad-box">✗ ' + esc(r.error) + "</div>";
    });
  };
  document.getElementById("np-go").onclick = async () => {
    const name = document.getElementById("np-name").value.trim();
    const root_choice = document.getElementById("np-root").value;
    const custom_path = document.getElementById("np-custom").value.trim();
    const goals = [0, 1, 2].map(i => ({
      name: document.querySelector('[data-g="name' + i + '"]').value.trim(),
      def: document.querySelector('[data-g="def' + i + '"]').value.trim(),
      line: document.querySelector('[data-g="line' + i + '"]').value.trim(),
      who: "创始人", when: "每天",
    })).filter(g => g.name);
    const redlines = document.getElementById("np-red").value.split("\n");
    const btn = document.getElementById("np-go");
    btn.disabled = true; btn.textContent = "创建中…";
    try {
      const r = await fetch("api/create_project", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, root_choice, custom_path, goals, redlines }),
      });
      const d = await r.json();
      const out = document.getElementById("np-result");
      if (d.ok) {
        out.innerHTML = '<div class="ok-box">✓ 装好了：<code>' + esc(d.path) + "</code><br>" +
          "六器官 " + (d.organs ? d.organs.length : 9) + " 个文件已写入 brain\\ 目录，状态也生成好了<br>" +
          '<pre>' + esc((d.generator && (d.generator.out || d.generator.error)) || "") + "</pre>" +
          '<button class="chip-btn" id="np-refresh">去项目页看卡片</button></div>';
        document.getElementById("np-refresh").onclick = () => {
          fetch("data.json").then(r => r.json()).then(dd => { DATA = dd; go("projects"); });
        };
      } else {
        out.innerHTML = '<div class="bad-box">✗ ' + esc(d.error) + "</div>";
      }
    } catch (e) {
      document.getElementById("np-result").innerHTML =
        '<div class="bad-box">✗ 请求失败：' + esc(String(e)) + "</div>";
    }
    btn.disabled = false; btn.textContent = "🚀 创建（自动装六器官+跑状态生成器）";
  };
}

/* ---------- 路由 ---------- */
const PAGES = {
  home: renderHome,
  projects: renderProjects,
  pitfall: renderPitfall,
  system: renderSystem,
  newproj: renderNewProject,
};

function go(page) {
  lastPage = page;
  document.querySelectorAll(".nav-btn").forEach(b => b.classList.toggle("active", b.dataset.page === page));
  PAGES[page]();
  // 换页必须回到顶部。否则从首页滚到底再点「项目库」，落点是页面中部，
  // 标题和操作按钮都在视野外——用户会以为点了没反应。
  const m = document.getElementById("main");
  if (m) m.scrollTop = 0;
}

/* 页内重渲染（移出/撤销/添加之后）要**保住**滚动位置，
   跟换页正相反：在第 10 张卡片上点了取消，不该被甩回顶部。 */
function keepScroll(fn) {
  const m = document.getElementById("main");
  const y = m ? m.scrollTop : 0;
  fn();
  if (m) m.scrollTop = y;
}

document.querySelectorAll(".nav-btn").forEach(b => b.onclick = () => go(b.dataset.page));

/* 开发者微信：点「复制」直接进剪贴板，省得手抄 */
(function () {
  const btn = document.getElementById("dev-copy");
  const wx = document.getElementById("dev-wx");
  if (!btn || !wx) return;
  btn.onclick = async () => {
    const ok = await copyText(wx.textContent.trim());
    btn.textContent = ok ? "已复制" : "复制失败";
    setTimeout(() => { btn.textContent = "复制"; }, 1600);
  };
})();

/* 主题切换：墨色（默认）⇄ 宣纸，选择持久化 */
(function () {
  const tb = document.getElementById("theme-toggle");
  if (!tb) return;
  const upd = () => {
    const dark = document.documentElement.dataset.theme === "dark";
    tb.textContent = dark ? "☀️ 宣纸" : "🌙 墨色";
  };
  upd();
  tb.onclick = () => {
    document.documentElement.dataset.theme =
      document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    try { localStorage.setItem("lt-theme", document.documentElement.dataset.theme); } catch (e) {}
    upd();
  };
})();

/* ---------- 首跑向导 ----------
   界面上只有一个概念：**你的项目清单**。
   加项目 = 点「添加项目」→ 弹出我的电脑 → 选中文件夹 → 确定。可以反复加。
   ⛔ 不猜哪个是项目：实测 105 个 md 的真项目零工程信号，而有全套工程信号的
   ruflow\v2、nexus_ai_backup 又不是独立项目。VS Code / JetBrains 同样不猜。
   ⛔ 「工作区」这个词不出现在界面上——勾「把里面的项目全部加进来」时内部才存成
   workspaces（好处是以后新建的项目会自动出现），用户不必理解这个词。 */
let SETUP = { ws: [], extra: [], excluded: [], found: null, foundMs: 0, foundTotal: 0, pick: {} };
let PICKER = { open: false, cwd: "", crumbs: [], parent: null, dirs: [], files: [],
               fileTotal: 0, sel: "", childCand: 0, whole: false };

function sameP(a, b) { return String(a).toLowerCase() === String(b).toLowerCase(); }
function has(list, p) { return list.some(x => sameP(x, p)); }
function underAny(list, p) {
  return list.some(w => String(p).toLowerCase().startsWith(String(w).toLowerCase() + "\\"));
}
/* 去重的唯一入口：单独加过、或已被某个「整个文件夹」罩住，都算已有 */
function alreadyHave(p) {
  return has(SETUP.extra, p) || has(SETUP.ws, p) || underAny(SETUP.ws, p);
}
function addProject(p, whole) {
  if (!p) return "empty";
  if (whole) {
    if (has(SETUP.ws, p)) return "dup";
    SETUP.ws.push(p);
    // 这个文件夹罩住的单个项目就不用再单列了
    SETUP.extra = SETUP.extra.filter(x => !sameP(x, p) && !underAny([p], x));
    return "ok";
  }
  if (alreadyHave(p)) return "dup";
  SETUP.extra.push(p);
  return "ok";
}
function kb(n) {
  if (n < 1024) return n + " B";
  if (n < 1048576) return (n / 1024).toFixed(0) + " KB";
  return (n / 1048576).toFixed(1) + " MB";
}
function addedCount() { return SETUP.extra.length + SETUP.ws.length; }

/* ================= 主界面 ================= */
function renderSetup() {
  main.innerHTML = '<div class="section"><p class="muted-note">正在读配置…</p></div>';
  fetch("api/setup_state", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
  }).then(r => r.json()).then(st => {
    SETUP.ws = (st.workspaces || []).slice();
    SETUP.extra = (st.projects || []).slice();
    SETUP.excluded = (st.excluded || []).slice();
    drawSetup();
  }).catch(e => {
    main.innerHTML = '<div class="bad-box">✗ ' + esc(String(e)) + "</div>";
  });
}

function drawSetup() {
  let html = '<div class="section"><h2>把你的项目加进来</h2>' +
    '<p class="muted-note">灵台不含任何业务数据，只读你机器上原地的文件。' +
    "知道项目在哪就点「添加项目」，不记得放哪了就点「帮我找找」。</p>" +
    '<div class="filter-row" style="margin-top:10px">' +
    '<button class="chip-btn primary" id="btn-add">📂 添加项目…</button>' +
    '<button class="chip-btn" id="btn-find">🔍 帮我找找</button></div>' +
    '<div id="pick-hint"></div></div>';

  html += '<div class="section"><h3>已加 ' + addedCount() + " 个</h3>";
  if (!addedCount()) {
    html += '<p class="muted-note">还没加。</p>';
  } else {
    html += SETUP.ws.map(p =>
      '<div class="q-label inline"><code>' + esc(p) + "</code> " +
      '<span class="chip good">里面的项目全要 · 新建的也会自动出现</span> ' +
      '<button class="chip-btn rm-ws" data-p="' + esc(p) + '">移除</button></div>').join("");
    html += SETUP.extra.map(p =>
      '<div class="q-label inline"><code>' + esc(p) + "</code> " +
      '<button class="chip-btn rm-extra" data-p="' + esc(p) + '">移除</button></div>').join("");
  }
  html += "</div>";

  html += '<div id="find-result"></div>';
  html += '<div class="section"><div class="filter-row">' +
    '<button class="chip-btn primary" id="setup-save">完成，进驾驶舱</button>' +
    '<button class="chip-btn" id="setup-skip">跳过，先随便看看</button></div>' +
    '<div id="setup-msg"></div></div>';
  html += '<div id="picker-host"></div>';

  main.innerHTML = html;

  // 界面上只有两条路：添加项目 / 帮我找找。
  // 网页版选择器留着，但不给按钮——只有系统对话框真的用不了时才自动顶上来兜底。
  document.getElementById("btn-add").onclick = pickNative;
  document.getElementById("btn-find").onclick = doFind;
  main.querySelectorAll(".rm-ws").forEach(b => b.onclick = () => {
    SETUP.ws = SETUP.ws.filter(x => !sameP(x, b.dataset.p)); drawSetup();
  });
  main.querySelectorAll(".rm-extra").forEach(b => b.onclick = () => {
    SETUP.extra = SETUP.extra.filter(x => !sameP(x, b.dataset.p)); drawSetup();
  });
  document.getElementById("setup-skip").onclick = () => { location.hash = "#skip-setup"; go("home"); };
  document.getElementById("setup-save").onclick = saveSetup;
  if (SETUP.found) drawFound();
  if (PICKER.open) drawPicker();
}

/* ========== 点「添加项目」→ 弹 Windows 原生对话框（真正的我的电脑） ========== */
function pickNative() {
  const hint = document.getElementById("pick-hint");
  if (hint) {
    hint.innerHTML = '<p class="muted-note"><span class="spin"></span> ' +
      "已经弹出「浏览文件夹」窗口——选好项目所在的文件夹，点确定。" +
      "（没看见就看看任务栏）</p>";
  }
  fetch("api/pick_folder", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: "选择项目所在的文件夹" }),
  }).then(r => r.json()).then(r => {
    if (hint) hint.innerHTML = "";
    if (!r.ok) {
      // 对话框用不了就退回网页版选择器，不把人卡死在这儿
      setupMsg('<div class="bad-box">✗ ' + esc(r.error) +
        "——改用网页里的选择器</div>");
      openPicker("");
      return;
    }
    if (r.cancelled) return;
    if (alreadyHave(r.path)) {
      setupMsg('<div class="ok-box">这个已经加过了：<code>' + esc(r.path) + "</code></div>");
      return;
    }
    addProject(r.path, false);
    drawSetup();
    let msg = '<div class="ok-box">✓ 已添加 <code>' + esc(r.path) + "</code>" +
      (r.installed ? "（已装六器官）" : "") + "</div>";
    if (r.child_candidates >= 2) {
      msg += '<div class="filter-row" style="margin-top:8px">' +
        '<span class="muted-note">这个文件夹里还有 ' + r.child_candidates +
        " 个子文件夹——如果它其实是装项目的地方：</span>" +
        '<button class="chip-btn" id="promote-ws" data-p="' + esc(r.path) +
        '">把里面的都加进来</button></div>';
    }
    setupMsg(msg);
    const pw = document.getElementById("promote-ws");
    if (pw) pw.onclick = () => { addProject(pw.dataset.p, true); drawSetup(); };
  }).catch(e => {
    if (hint) hint.innerHTML = "";
    setupMsg('<div class="bad-box">✗ ' + esc(String(e)) + "——改用网页里的选择器</div>");
    openPicker("");
  });
}

/* ========== 备选：网页里的选择器（非 Windows 或对话框不可用时） ========== */
function openPicker(path) {
  PICKER.open = true;
  PICKER.sel = "";
  PICKER.whole = false;
  pickerGo(path);
}
function closePicker() {
  PICKER.open = false;
  const h = document.getElementById("picker-host");
  if (h) h.innerHTML = "";
}
function pickerGo(path) {
  fetch("api/browse", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path: path }),
  }).then(r => r.json()).then(r => {
    if (!r.ok) { alert("打不开：" + r.error); return; }
    PICKER.cwd = r.path;
    PICKER.crumbs = r.crumbs || [];
    PICKER.parent = r.parent;
    PICKER.dirs = r.dirs || [];
    PICKER.files = r.files || [];
    PICKER.fileTotal = r.file_total || 0;
    PICKER.childCand = r.child_candidates || 0;
    PICKER.sel = r.path || "";       // 默认选中当前所在文件夹
    PICKER.whole = false;
    drawPicker();
  }).catch(e => alert(String(e)));
}

function drawPicker() {
  const host = document.getElementById("picker-host");
  if (!host) return;
  const crumbs = (PICKER.crumbs || []).map(c =>
    '<button class="chip-btn pk-go" data-p="' + esc(c.path) + '">' + esc(c.name) + "</button>")
    .join('<span class="muted-note"> › </span>');

  let rows = PICKER.dirs.map(d => {
    const dup = alreadyHave(d.path);
    const sig = (d.signals || []).map(s =>
      '<span class="chip ' + (s === "已装六器官" ? "good" : "muted") + '">' + esc(s) + "</span>").join("");
    const meta = [];
    if (d.subs) meta.push(d.subs + " 文件夹");
    if (d.md) meta.push(d.md + " md");
    return '<div class="fs-row' + (sameP(PICKER.sel, d.path) ? " sel" : "") +
      '" data-p="' + esc(d.path) + '">' +
      "<span>📁</span><span class=\"fs-name\">" + esc(d.name) + "</span>" +
      sig + (dup ? '<span class="chip good">已加</span>' : "") +
      '<span class="muted-note">' + esc(meta.join(" · ")) + "</span>" +
      '<button class="chip-btn pk-in" data-p="' + esc(d.path) + '">打开 ›</button></div>';
  }).join("");
  rows += PICKER.files.map(f =>
    '<div class="fs-row file"><span>📄</span><span class="fs-name">' + esc(f.name) +
    '</span><span class="muted-note">' + kb(f.size) + "</span></div>").join("");
  if (PICKER.fileTotal > PICKER.files.length) {
    rows += '<div class="fs-row file"><span></span><span class="fs-name muted-note">…还有 ' +
      (PICKER.fileTotal - PICKER.files.length) + " 个文件</span></div>";
  }
  if (!rows) rows = '<div class="fs-row file"><span class="muted-note">这里是空的</span></div>';

  const dupSel = PICKER.sel && alreadyHave(PICKER.sel);
  host.innerHTML =
    '<div class="modal-mask" id="pk-mask"><div class="modal">' +
    '<div class="modal-head"><h3>选择项目所在的文件夹</h3>' +
    '<div class="filter-row">' +
    '<button class="chip-btn pk-go" data-p="">💻 我的电脑</button>' +
    (PICKER.parent ? '<button class="chip-btn pk-go" data-p="' + esc(PICKER.parent) + '">⬆ 上一层</button>' : "") +
    "</div>" +
    (crumbs ? '<div class="filter-row" style="margin-top:6px">' + crumbs + "</div>" : "") +
    "</div>" +
    '<div class="modal-body">' + rows + "</div>" +
    '<div class="modal-foot">' +
    '<span class="muted-note">已选</span><span class="fs-path">' +
    esc(PICKER.sel || "（还没选）") + "</span></div>" +
    '<div class="modal-foot" style="border-top:0;padding-top:0">' +
    (PICKER.childCand
      ? '<label class="q-label inline"><input type="checkbox" id="pk-whole"' +
        (PICKER.whole ? " checked" : "") + "> 把这个文件夹里的 " + PICKER.childCand +
        " 个文件夹全部加进来（以后新建的也自动进来）</label>"
      : "") +
    '<span style="flex:1"></span>' +
    (dupSel && !PICKER.whole ? '<span class="chip good">这个已经加过了</span>' : "") +
    '<button class="chip-btn" id="pk-cancel">取消</button>' +
    '<button class="chip-btn primary" id="pk-ok">确定添加</button>' +
    "</div></div></div>";

  host.querySelectorAll(".fs-row[data-p]").forEach(el => {
    el.onclick = ev => {
      if (ev.target.classList.contains("pk-in")) return;
      PICKER.sel = el.dataset.p;
      drawPicker();
    };
    el.ondblclick = () => pickerGo(el.dataset.p);
  });
  host.querySelectorAll(".pk-in").forEach(b => {
    b.onclick = ev => { ev.stopPropagation(); pickerGo(b.dataset.p); };
  });
  host.querySelectorAll(".pk-go").forEach(b => { b.onclick = () => pickerGo(b.dataset.p); });
  const w = document.getElementById("pk-whole");
  if (w) w.onchange = () => { PICKER.whole = w.checked; drawPicker(); };
  document.getElementById("pk-cancel").onclick = closePicker;
  document.getElementById("pk-mask").onclick = ev => {
    if (ev.target.id === "pk-mask") closePicker();
  };
  document.getElementById("pk-ok").onclick = () => {
    const target = PICKER.whole ? PICKER.cwd : PICKER.sel;
    const r = addProject(target, PICKER.whole);
    closePicker();
    drawSetup();
    if (r === "dup") setupMsg('<div class="ok-box">这个已经加过了，没有重复添加：<code>' + esc(target) + "</code></div>");
    else if (r === "empty") setupMsg('<div class="bad-box">✗ 还没选文件夹</div>');
  };
}

function setupMsg(h) {
  const b = document.getElementById("setup-msg");
  if (b) b.innerHTML = h;
}

/* ================= 扫描找项目 ================= */
function doFind() {
  const box = document.getElementById("find-result");
  box.innerHTML = '<div class="section"><p><span class="spin"></span> 正在找…</p></div>';
  fetch("api/find_projects", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ depth: 3 }),
  }).then(r => r.json()).then(r => {
    if (!r.ok) { box.innerHTML = '<div class="bad-box">✗ ' + esc(r.error) + "</div>"; return; }
    SETUP.found = r.groups || [];
    SETUP.foundMs = r.ms;
    SETUP.foundTotal = r.total;
    SETUP.pick = {};
    SETUP.found.forEach(g => g.items.forEach(it => {
      if (it.installed && !alreadyHave(it.path)) SETUP.pick[it.path] = true;
    }));
    drawFound();
  }).catch(e => { box.innerHTML = '<div class="bad-box">✗ ' + esc(String(e)) + "</div>"; });
}

function drawFound() {
  const box = document.getElementById("find-result");
  if (!box) return;
  const groups = (SETUP.found || []).map(g => ({
    // 去重：已经加过的不再列出来让人重复勾
    ...g, items: g.items.filter(it => !alreadyHave(it.path)),
  })).filter(g => g.items.length);
  const hidden = (SETUP.foundTotal || 0) -
    groups.reduce((n, g) => n + g.items.length, 0);
  if (!groups.length) {
    box.innerHTML = '<div class="section"><div class="ok-box">✓ 扫完了，' +
      (hidden ? "找到的 " + hidden + " 个都已经加过了" : "没找到更多") + "</div></div>";
    return;
  }
  let html = '<div class="section"><h3>找到的（勾上要加的）</h3>' +
    '<p class="muted-note">扫了 ' + SETUP.foundMs + " ms。已装六器官的替你勾上了" +
    (hidden ? "；已经加过的 " + hidden + " 个没再列出来" : "") + "。</p>";
  groups.forEach((g, gi) => {
    const title = g.kind === "solo"
      ? "单独放在外面的（" + g.items.length + "）"
      : "<code>" + esc(g.parent) + "</code> 里的（" + g.items.length + "）";
    html += "<details" + (gi < 2 || g.installed_n ? " open" : "") + "><summary>" + title +
      (g.installed_n ? '　<span class="chip good">已装 ' + g.installed_n + "</span>" : "") +
      (g.software ? '　<span class="chip muted">像软件目录</span>' : "") + "</summary>" +
      '<div class="filter-row" style="margin:8px 0">' +
      '<button class="chip-btn fg-all" data-g="' + gi + '">全选</button>' +
      '<button class="chip-btn fg-none" data-g="' + gi + '">全不选</button>' +
      (g.kind !== "solo"
        ? '<button class="chip-btn fg-ws" data-p="' + esc(g.parent) +
          '">整个文件夹都要</button>' : "") +
      '</div><div data-fg="' + gi + '">' +
      g.items.map(it =>
        '<label class="q-label inline"><input type="checkbox" class="fp" value="' +
        esc(it.path) + '"' + (SETUP.pick[it.path] ? " checked" : "") + "> <b>" +
        esc(it.name) + "</b> " +
        (it.signals || []).map(s => '<span class="chip ' +
          (s === "已装六器官" ? "good" : "muted") + '">' + esc(s) + "</span>").join("") +
        ' <span class="muted-note">' + esc(it.path) + "</span></label>").join("") +
      "</div></details>";
  });
  html += '<div class="filter-row"><button class="chip-btn primary" id="fp-add">＋ 添加勾选的</button>' +
    '<span class="muted-note" id="fp-count"></span></div></div>';
  box.innerHTML = html;

  const count = () => {
    const el = document.getElementById("fp-count");
    if (el) el.textContent = "勾了 " + box.querySelectorAll(".fp:checked").length + " 个";
  };
  box.querySelectorAll(".fp").forEach(c => {
    c.onchange = () => { SETUP.pick[c.value] = c.checked; count(); };
  });
  box.querySelectorAll(".fg-all").forEach(b => b.onclick = () => {
    box.querySelectorAll('[data-fg="' + b.dataset.g + '"] .fp').forEach(c => {
      c.checked = true; SETUP.pick[c.value] = true;
    });
    count();
  });
  box.querySelectorAll(".fg-none").forEach(b => b.onclick = () => {
    box.querySelectorAll('[data-fg="' + b.dataset.g + '"] .fp').forEach(c => {
      c.checked = false; SETUP.pick[c.value] = false;
    });
    count();
  });
  box.querySelectorAll(".fg-ws").forEach(b => b.onclick = () => {
    addProject(b.dataset.p, true);
    drawSetup();
  });
  const add = document.getElementById("fp-add");
  if (add) add.onclick = () => {
    let n = 0, dup = 0;
    box.querySelectorAll(".fp:checked").forEach(c => {
      const r = addProject(c.value, false);
      if (r === "ok") n++; else if (r === "dup") dup++;
    });
    drawSetup();
    setupMsg('<div class="ok-box">✓ 加了 ' + n + " 个" +
      (dup ? "，跳过 " + dup + " 个重复的" : "") + "</div>");
  };
  count();
}

function saveSetup() {
  const m = document.getElementById("setup-msg");
  if (!addedCount()) {
    m.innerHTML = '<div class="bad-box">✗ 还没加任何项目</div>';
    return;
  }
  m.innerHTML = '<p><span class="spin"></span> 保存并重算…</p>';
  fetch("api/setup_save", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      workspaces: SETUP.ws, projects: SETUP.extra,
      excluded: SETUP.excluded, roots: {},
    }),
  }).then(r => r.json()).then(r => {
    if (!r.ok) { m.innerHTML = '<div class="bad-box">✗ ' + esc(r.error) + "</div>"; return; }
    location.hash = "";
    location.reload();
  }).catch(e => { m.innerHTML = '<div class="bad-box">✗ ' + esc(String(e)) + "</div>"; });
}


fetch("data.json")
  .then(r => r.json())
  .then(d => {
    DATA = d;
    // 版本号从 data.json 取，index.html 里不再存第二份。
    // ⛔ 此前 VERSION / README / index.html 各写一份，靠 make_release 的
    //    「三处一致」检查兜着——检查只拦得住不一致，拦不住三处一起忘。
    const vb = document.getElementById("ver-badge");
    if (vb) vb.textContent = d.version ? "v" + d.version : "";
    // 反馈出口：跑起来过至少一个项目才露出来。没被帮到过就问「帮到你了吗」，
    // 既尴尬，也把唯一的需求信号口糟蹋了——那是零遥测下仅有的信号来源。
    const fb = document.getElementById("nav-feedback");
    if (fb && (d.projects || []).some(p => p.state === "generated")) {
      fb.href = REPO_URL + "/discussions";
      fb.hidden = false;
    }
    // 侧栏原来印着「生成时间 + machine_id」。时间首页已经有了；machine_id 是给
    // 多机分数据用的内部标识，用户看了不知道要拿它干什么——去掉，侧栏留给版本号。
    document.getElementById("nav-foot").textContent = "";
    // 第一次打开：先问清楚你的项目在哪，别拿探测结果替用户做主
    if (d.first_run && location.hash !== "#skip-setup") { renderSetup(); return; }
    // 直达链接：#home / #projects / #pitfall / #detail=<项目名>（录 demo 与分享用）
    const h = location.hash;
    if (h.startsWith("#detail=")) goProjectDetail(decodeURIComponent(h.slice(8)));
    else if (h === "#projects") go("projects");
    else if (h === "#pitfall") go("pitfall");
    else go("home");
  })
  .catch(e => {
    main.innerHTML = '<div class="section"><h2>✗ 数据加载失败</h2><p>' + esc(String(e)) + "<br>请先跑 <code>python -X utf8 dashboard.py</code> 生成数据。</p></div>";
  });
