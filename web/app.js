/* 大脑驾驶舱 · 前端（零框架）。只渲染 fetch 到的 data.json，本文件不含任何知识。 */
"use strict";

let DATA = null;
const main = document.getElementById("main");

function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function statusBadge(status) {
  const map = {
    ok: ["good", "✓ 在位"],
    missing: ["bad", "✗ 缺失"],
    noroot: ["muted", "— 本机无此根"],
    absent: ["muted", "— 本机无此件"],
  };
  const [cls, label] = map[status] || ["muted", esc(status)];
  return '<span class="chip ' + cls + '">' + label + "</span>";
}

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
  const [scls, sl] = PROJ_STATE[p.state] || PROJ_STATE.null;
  const n = organN(p);
  return '<div class="card slim clickable" data-path="' + esc(p.path) + '"><div class="card-head"><strong>' + esc(p.name) + "</strong>" +
    '<span class="chip ' + scls + '">' + sl + "</span></div>" +
    '<div class="chip-row">' + organDots(p) +
    '<span class="chip ' + (n > 0 ? "good" : "muted") + '">器官 ' + n + "/9</span>" +
    (p.alarms.length ? '<span class="chip warn">告警 ' + p.alarms.length + "</span>" : "") +
    (p.outdated && p.outdated.length ? '<span class="chip warn">⚠ 可升级 ' + p.outdated.length + "</span>" : "") +
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
    '<span class="chip ' + (n > 0 ? "good" : "muted") + '">器官 ' + n + '/9</span></div>' +
    '<p class="muted-note"><code>' + esc(d.path) + "</code></p>" +
    '<div class="filter-row">' +
    '<button class="chip-btn primary" id="pd-resume">📋 复制「继续做」指令</button>' +
    '<button class="chip-btn" id="pd-open">📁 打开项目目录</button>' +
    '<button class="chip-btn" id="pd-remove">🗂 移出项目库</button></div>' +
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
  if (d.handoff_done) {
    html += '<div class="section"><h3>✅/⏳ 上一窗做完的与没做完的</h3><div class="doc">' + d.handoff_done + "</div></div>";
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
          box.innerHTML = '<div class="ok-box">✓ 装好了：六器官 12 件 + 02_状态已生成 + 装配图已登记' +
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
  // 分母是「这台机器该有的」，不是登记总数——无根件和本机专属件不该算成你缺东西
  const denom = (h.applicable != null ? h.applicable : h.total) || 0;
  const pct = denom ? Math.round(h.ok / denom * 100) : 0;
  const R = 52, C = 2 * Math.PI * R;
  const ringColor = h.missing.length ? "#fb7185" : "#34d399";
  const ring = '<div class="hero-ring">' +
    '<svg width="128" height="128" viewBox="0 0 128 128"><defs>' +
    '<linearGradient id="ringGrad" x1="0" y1="1" x2="1" y2="0">' +
    '<stop offset="0" stop-color="' + ringColor + '"/><stop offset="1" stop-color="#6ea8fe"/>' +
    "</linearGradient></defs>" +
    '<circle class="ring-bg" cx="64" cy="64" r="' + R + '"/>' +
    '<circle class="ring-val" cx="64" cy="64" r="' + R + '" stroke-dasharray="' + C + '" stroke-dashoffset="' + (C * (1 - pct / 100)).toFixed(1) + '"/>' +
    '</svg><div class="ring-num"><b>' + h.ok + "</b><span>/ " + denom + " 真源在位</span></div></div>";
  const tiles = [
    ["告警项目", String(alarmProjects.length), alarmProjects.length ? "warn" : "good"],
    ["项目总数", String(DATA.projects.length), "good"],
    ["坑库", String(DATA.pitfall.rows.length), "good"],
  ];
  let html = '<div class="hero">' + ring + tiles.map(t =>
    '<div class="tile ' + t[2] + '"><div class="tile-num">' + esc(t[1]) + '</div><div class="tile-label">' + esc(t[0]) + "</div></div>"
  ).join("") + "</div>";

  html += '<div class="section card start-card"><h2>今日开工</h2>' +
    '<p class="muted-note">红绿灯全绿 → 复制 → 粘给任何 AI → 开工。收窗不用管——AI 分段落盘，进度一直在文件里。</p>' +
    '<div class="filter-row">' +
    '<button class="chip-btn primary" id="h-open-btn">📋 复制开窗三句话</button>' +
    '<button class="chip-btn accent-btn" id="h-newproj">＋ 新项目（自动装六器官）</button>' +
    // 「新项目」是从零建一个；「添加已有」是把电脑上已经存在的项目收进来。
    // 两回事，用户想收录已有项目时不该只能去项目页找
    '<button class="chip-btn" id="h-addproj">📂 添加已有项目</button>' +
    '<button class="chip-btn" id="h-refresh">🔄 深查（重算全部真源）</button></div>' +
    '<p class="muted-note">快照生成于 ' + esc(DATA.generated_at) + " · 数据全部机器生成，人不手写</p>" +
    '<p class="muted-note" id="h-note"></p></div>';

  const ev = DATA.evolution || {};
  const staleN = (ev.stale_handoffs || []).length;
  // 够不着的项目要出声：外接硬盘拔了/网络盘断了，项目从列表消失而不吭一声，
  // 人只会以为东西丢了
  const gone = DATA.unreachable_projects || [];
  if (h.missing.length || h.identical_pairs.length || staleN || gone.length) {
    html += '<div class="section"><h2>🔴 先修这里</h2><ul>' +
      h.missing.map(m => "<li>" + esc(m.path) + " → " + esc(m.resolved) + "</li>").join("") +
      h.identical_pairs.map(p => "<li>同名同内容双份：" + esc(p.a) + " ⟷ " + esc(p.b) + "</li>").join("") +
      gone.map(p => "<li>📴 够不着：<code>" + esc(p) +
        "</code>——外接硬盘没插？网络盘断了？目录挪走了？（它还记在你的项目清单里）</li>").join("") +
      // 提到哪儿就得能点过去：写「见设置→进化审计」却不给链接，等于让人自己找路
      (staleN ? "<li>🟡 有 " + staleN + " 个项目的交接超 7 天没更新——该生核了 " +
        '<a href="#" id="h-goto-evolve">去进化审计 →</a></li>' : "") +
      "</ul></div>";
  }
  if (alarmProjects.length) {
    html += '<div class="section"><h2>⚠ 有告警的项目</h2><div class="cards">' +
      alarmProjects.map(slimCard).join("") + "</div></div>";
  }
  html += '<div class="section" style="margin-bottom:14px"><span class="muted-note">' +
    '🧠 经验库 <b>' + esc(ev.total_pitfalls || DATA.pitfall.rows.length) + '</b> 条' +
    (ev.new_this_week ? '（本周 +' + esc(ev.new_this_week) + "）" : "") +
    ' · <a href="#" id="h-goto-pitfall">查坑/记坑</a>' +
    ' · <a href="#" id="h-goto-sys">设置与审计</a>' +
    "</span></div>";
  html += '<div class="section"><h2>进行中的项目（' + active.length + '）</h2><div class="cards">' +
    active.slice(0, 6).map(slimCard).join("") + "</div>" +
    (active.length > 6 ? '<p class="muted-note">更多见 <a href="#" class="h-goto-projects">项目库 →</a></p>' : "") +
    '<p class="muted-note">其余 ' + (DATA.projects.length - active.length) +
    ' 个未装系统的项目（可能没完工）→ <a href="#" class="h-goto-projects">去项目库看，全部可点开续做 →</a></p></div>';

  main.innerHTML = html;
  attachCardClicks();
  document.getElementById("h-newproj").onclick = () => go("newproj");
  const hAdd = document.getElementById("h-addproj");
  if (hAdd) hAdd.onclick = () => { go("projects"); addProjectHere(); };
  document.getElementById("h-goto-pitfall").onclick = e => { e.preventDefault(); go("pitfall"); };
  document.getElementById("h-goto-sys").onclick = e => { e.preventDefault(); go("system"); };
  main.querySelectorAll(".h-goto-projects").forEach(a => {
    a.onclick = e => { e.preventDefault(); go("projects"); };
  });
  const gev = document.getElementById("h-goto-evolve");
  if (gev) gev.onclick = e => { e.preventDefault(); go("system"); };
  document.getElementById("h-refresh").onclick = async () => {
    const b = document.getElementById("h-refresh");
    b.disabled = true; b.textContent = "🔄 深查中…";
    try {
      const r = await fetch("api/refresh", { method: "POST" });
      const d = await r.json();
      if (d.generated_at) { DATA = d; renderHome(); }
      else { b.disabled = false; b.textContent = "✗ " + (d.error || "深查失败"); }
    } catch (e) {
      b.disabled = false; b.textContent = "✗ 深查失败";
    }
  };
  fetch("api/templates", { method: "POST" }).then(r => r.json()).then(t => {
    document.getElementById("h-open-btn").onclick = async () => {
      const ok = await copyText(t.open);
      document.getElementById("h-note").textContent =
        ok ? "✓ 已复制——打开任意 AI，粘贴，开工。" : "✗ 复制失败，手动选中下面文本";
      if (!ok) {
        const ta = document.createElement("textarea");
        ta.value = t.open; ta.rows = 4; ta.readOnly = true;
        document.getElementById("h-note").appendChild(ta);
      }
    };
  });
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

/* ---------- 坑库：搜索 + 分区 + 分页 ---------- */
let PIT_ROWS = [];
const PIT_PAGE = 20;
function renderPitfall() {
  PIT_ROWS = DATA.pitfall.rows;
  // `__` 开头 = 后端内部字段（如 __section 是给分区筛选用的），不该出现在表格里
  const cols = (DATA.pitfall.columns || []).filter(c => !String(c).startsWith("__"));
  const sections = DATA.pitfall.sections;
  let html = '<div class="section"><h2>坑库（' + PIT_ROWS.length + " 条 · 踩坑前查一眼）</h2>" +
    '<div class="filter-row"><input id="pit-q" type="search" placeholder="搜索：坑 / 防法 / 出处">' +
    '<select id="pit-sec"><option value="">全部分区</option>' +
    sections.map(s => '<option value="' + esc(s.name) + '">' + esc(s.name) + "（" + s.count + "）</option>").join("") +
    '</select><button class="chip-btn accent-btn" id="pit-add">＋ 记一条坑</button></div>' +
    '<div id="pit-form-wrap" style="display:none"><div class="form-grid">' +
    '<label>分区<select id="pf-section">' +
    sections.map(s => '<option>' + esc(s.name) + "</option>").join("") + "</select></label>" +
    '<label>一句话坑<input id="pf-pit" placeholder="踩的是什么坑"></label>' +
    '<label>防法（照做即可）<input id="pf-fix" placeholder="下次怎么做就不踩"></label>' +
    '<label>出处<input id="pf-src" placeholder="哪个项目/窗口"></label>' +
    '<label>失效判据（必填）<input id="pf-inv" placeholder="防的事被结构性消除即删，如：XX工具修复后"></label>' +
    '</div><div class="filter-row"><button class="chip-btn primary" id="pf-go">入库</button>' +
    '<span class="muted-note">防法/失效判据缺一不放行——涨有门槛</span></div><div id="pf-result"></div></div>' +
    '<table id="pit-table"><thead><tr>' + cols.map(c => "<th>" + esc(c) + "</th>").join("") + "</tr></thead><tbody></tbody></table>" +
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
      out.innerHTML = '<div class="ok-box">✓ 已入库（编号 ' + esc(rj.code) + "）</div>";
      fetch("data.json").then(r2 => r2.json()).then(dd => { DATA = dd; go("pitfall"); });
    } else {
      out.innerHTML = '<div class="bad-box">✗ ' + esc(rj.error) + "</div>";
    }
  };
  drawPitRows();
}
let pitLimit = PIT_PAGE;
function drawPitRows() {
  const q = (document.getElementById("pit-q").value || "").toLowerCase();
  const sec = document.getElementById("pit-sec").value;
  // `__` 开头 = 后端内部字段（如 __section 是给分区筛选用的），不该出现在表格里
  const cols = (DATA.pitfall.columns || []).filter(c => !String(c).startsWith("__"));
  const rows = PIT_ROWS.filter(r =>
    (!sec || r.__section === sec) &&
    (!q || cols.some(c => String(r[c] || "").toLowerCase().includes(q))));
  const shown = rows.slice(0, pitLimit);
  document.querySelector("#pit-table tbody").innerHTML = shown.map(r =>
    "<tr>" + cols.map(c => "<td>" + esc(r[c]) + "</td>").join("") + "</tr>").join("");
  document.getElementById("pit-count").textContent = "显示 " + shown.length + " / " + rows.length;
  document.getElementById("pit-more").style.display = rows.length > shown.length ? "" : "none";
  if (document.getElementById("pit-more").style.display === "none") pitLimit = PIT_PAGE;
  else if (pitLimit < rows.length) pitLimit += PIT_PAGE;
}

/* ---------- 进化审计（渲染进设置页 tab） ---------- */
function renderEvolutionInto(box) {
  const ev = DATA.evolution || {};
  const secs = [
    ["待补失效判据（只降不涨才是活）", ev.missing_invalid || [], "pitfall",
      r => r["编号"] + " " + (r["一句话坑"] || "").slice(0, 50)],
    ["候选删除（入库>3个月 且 触发≤1）", ev.candidates || [], "pitfall",
      r => r["编号"] + " " + (r["一句话坑"] || "").slice(0, 50)],
    ["C 类待办已到期", ev.expired_todos || [], "todo",
      r => r["project"] + "： " + (r["line"] || "").slice(0, 80)],
    ["🟡 交接超 7 天没更新（该生核了）", ev.stale_handoffs || [], "handoff",
      r => r["project"] + "（" + r["days"] + " 天）"],
    ["🔄 通用件落后（体系已升级，项目可同步）", (DATA.sync || []).map(s => ({
      编号: s.project, path: s.path, line: "落后：" + s.outdated.join("、") })), "sync", r => r["编号"] + "：" + r.line],
  ];
  let html = '<p class="muted-note">每周跑一次（双击即重算）。勾选 → 点删除 → 真源行被删（git 有回滚点）。</p>' +
    // 同样的道理：提到「方法」页就得能点过去，别让人自己找 tab
    '<div class="section"><h3>🔴 断头 / 双份（只读，' +
    '<a href="#" id="ev-goto-method">去「方法」页查装配图修指针 →</a>）</h3>' +
    ((ev.broken || []).map(m => "<p>断头：" + esc(m.path) + "</p>").join("") +
     (ev.identical_pairs || []).map(p => "<p>双份：" + esc(p.a) + " ⟷ " + esc(p.b) + "</p>").join("") ||
     '<p class="muted-note">无。</p>') + "</div>";
  let any = false;
  for (const [title, items, kind, fmt] of secs) {
    if (!items.length) continue;
    any = true;
    // 长清单默认折叠：38 条待补全平铺会把后面几张清单和「删除所选」全埋了，
    // 实测整页 2 屏高——勾选框散在各处，按钮却在最底下，交互链是断的
    const long = items.length > 8;
    const body = items.map((r, i) =>
      '<label class="q-label inline"><input type="checkbox" data-kind="' + kind + '" data-id="' +
      esc(r["编号"] || r["project"] || i) + '" data-proj="' + esc(r["path"] || "") + '"> ' +
      esc(fmt(r)) + "</label>").join("");
    html += '<div class="section">' +
      (long
        ? "<details><summary><b>" + esc(title) + "（" + items.length + "）</b>" +
          '<span class="muted-note"> · 点开逐条勾</span></summary>' +
          '<div style="margin-top:8px">' + body + "</div></details>"
        : "<h3>" + esc(title) + "（" + items.length + "）</h3>" + body) +
      "</div>";
  }
  if (!any) {
    html += '<div class="ok-box">✓ 五清单全空——壳是干净的，继续生长。</div>';
  } else {
    html += '<div class="filter-row"><button class="chip-btn bad-btn" id="ev-delete">🗑 删除所选（不可恢复，git 有回滚点）</button>' +
      '<span class="muted-note" id="ev-count">未勾选</span></div>' +
      '<div id="ev-result"></div>';
  }
  box.innerHTML = html;
  // 勾了几条要看得见——折叠之后更需要，否则不知道自己到底选了没有
  const evCount = () => {
    const el = document.getElementById("ev-count");
    if (!el) return;
    const n = box.querySelectorAll('input[type="checkbox"]:checked').length;
    el.textContent = n ? "已勾 " + n + " 条" : "未勾选";
  };
  box.querySelectorAll('input[type="checkbox"]').forEach(c => { c.onchange = evCount; });
  evCount();
  const gm = document.getElementById("ev-goto-method");
  if (gm) {
    gm.onclick = e => {
      e.preventDefault();
      document.querySelectorAll(".stab").forEach(x =>
        x.classList.toggle("active", x.dataset.s === "methods"));
      renderSysTab("methods");
    };
  }
  const delBtn = document.getElementById("ev-delete");
  if (delBtn) {
    delBtn.onclick = async () => {
      const checked = [...box.querySelectorAll('input[type="checkbox"]:checked')];
      if (!checked.length) {
        document.getElementById("ev-result").innerHTML =
          '<div class="bad-box">✗ 先勾选要删的条目</div>';
        return;
      }
      if (!confirm("确定删除 " + checked.length + " 条？真源行会被删（git 回滚点可恢复）")) return;
      const groups = {};
      checked.forEach(c => {
        const k = c.dataset.kind + "|" + c.dataset.proj;
        (groups[k] = groups[k] || []).push(c.dataset.id);
      });
      const out = document.getElementById("ev-result");
      out.innerHTML = '<p><span class="spin"></span> 执行中…</p>';
      for (const [k, ids] of Object.entries(groups)) {
        const [kind, path] = k.split("|");
        try {
          if (kind === "sync") {
            const r = await fetch("api/sync_project", {
              method: "POST", headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ path }),
            });
            const rj = await r.json();
            out.innerHTML += "<p>" + (rj.ok ? "✓ " + kind + " 已同步 " + rj.synced + " 件" : "✗ " + esc(rj.error)) + "</p>";
            continue;
          }
          const r = await fetch("api/audit_delete", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ kind, ids, path }),
          });
          const rj = await r.json();
          out.innerHTML += '<p>' + (rj.ok ? "✓ 已删 " + rj.removed + " 条（" + kind + "）" : "✗ " + esc(rj.error)) + "</p>";
        } catch (e) {
          out.innerHTML += "<p>✗ " + esc(String(e)) + "</p>";
        }
      }
      out.innerHTML += '<p class="muted-note">已重建数据，刷新页面即可。</p>';
    };
  }
}

/* ---------- 设置页：进化审计 / 开工四问 / 换机 / 方法 ---------- */
function renderSystem() {
  let html = '<div class="section"><h2>设置</h2>' +
    '<div class="doc-tabs">' +
    '<button class="doc-tab stab active" data-s="evolve">进化审计（每周一次）</button>' +
    '<button class="doc-tab stab" data-s="fourq">开工四问</button>' +
    '<button class="doc-tab stab" data-s="portable">换机</button>' +
    '<button class="doc-tab stab" data-s="methods">方法</button>' +
    '</div><div id="sys-box"></div></div>';
  main.innerHTML = html;
  document.querySelectorAll(".stab").forEach(b => b.onclick = () => {
    document.querySelectorAll(".stab").forEach(x => x.classList.toggle("active", x === b));
    renderSysTab(b.dataset.s);
  });
  renderSysTab("evolve");
}

function renderSysTab(which) {
  const box = document.getElementById("sys-box");
  if (which === "evolve") {
    renderEvolutionInto(box);
  } else if (which === "methods") {
    box.innerHTML = '<div class="doc-tabs">' +
      DATA.methods.map((m, i) => '<button class="doc-tab" data-i="' + i + '">' + esc(m.name) + "</button>").join("") +
      '</div><div class="doc" id="doc-box">' + DATA.methods[0].html + "</div>";
    document.querySelectorAll("#sys-box .doc-tab").forEach(b => b.onclick = () => {
      document.querySelectorAll("#sys-box .doc-tab").forEach(x => x.classList.toggle("active", x === b));
      document.getElementById("doc-box").innerHTML = DATA.methods[+b.dataset.i].html;
    });
    document.querySelectorAll("#sys-box .doc-tab")[0].classList.add("active");
  } else if (which === "map") {
    box.innerHTML = '<div class="doc">' + DATA.map_html + "</div>" +
      '<details style="margin-top:12px"><summary>逐文件清单（' + DATA.sources.length + " · 完整状态）</summary>" +
      '<table><thead><tr><th>层</th><th>文件</th><th>性质</th><th>状态</th></tr></thead><tbody>' +
      DATA.sources.map(s =>
        "<tr><td>" + esc(s.layer) + "</td><td><code>" + esc(s.path) + "</code></td><td>" + esc(s.nature) + "</td><td>" + statusBadge(s.status) + "</td></tr>"
      ).join("") + "</tbody></table></details>";
  } else if (which === "fourq") {
    const qs = [
      ["服务哪个终极指标？", "说不出 = 这步可能在偏"],
      ["完工判据是什么？（不能是过程量）", "如：客户真机 5 分钟跑通"],
      ["胃口多少？（愿意花多少，不是估多久）", "如：两天 / ￥50"],
      ["到期没做完怎么办？", "默认作废，不默认延期"],
    ];
    box.innerHTML = qs.map((q, i) =>
      '<label class="q-label"><strong>' + (i + 1) + ". " + esc(q[0]) + "</strong>" +
      '<input data-q="' + i + '" placeholder="' + esc(q[1]) + '"></label>').join("") +
      '<div class="filter-row"><button class="chip-btn" id="q-check">✅ 检查</button></div>' +
      '<div id="q-result"></div>';
    document.getElementById("q-check").onclick = () => {
      const missing = [];
      for (let i = 0; i < 4; i++) {
        if (!document.querySelector('[data-q="' + i + '"]').value.trim()) missing.push(i + 1);
      }
      document.getElementById("q-result").innerHTML = missing.length
        ? '<div class="bad-box">✗ 缺第 ' + missing.map(n => "<b>" + n + "</b>").join("、") + " 问——答完再开工</div>"
        : '<div class="ok-box">✓ 四问齐，可以开工。</div>';
    };
  } else {
    const roots = DATA.root_status;
    box.innerHTML = '<ol class="steps">' +
      "<li>clone skills 仓库到新机器</li>" +
      "<li><code>python -X utf8 install.py</code>（自动探测各根）</li>" +
      "<li><code>python -X utf8 dashboard.py</code>（起服务开浏览器）</li></ol>" +
      '<table style="margin-top:10px"><thead><tr><th>根</th><th>路径</th><th>状态</th></tr></thead><tbody>' +
      roots.map(r => "<tr><td>{" + esc(r.alias) + "}</td><td><code>" + esc(r.path || "— 未配置") + "</code></td><td>" + statusBadge(r.exists ? "ok" : "noroot") + "</td></tr>").join("") +
      "</tbody></table>" +
      '<p class="muted-note">机器：' + esc(DATA.machine_id) + " · 团队版预留：roots.json 带 machine_id，多机数据分得开（网络同步 v0.2+ 另立项）</p>";
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
          "六器官 " + (d.organs ? d.organs.length : 9) + " 件 + 02_状态已生成，已登记进装配图<br>" +
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
    document.getElementById("nav-foot").textContent =
      "生成 " + d.generated_at + "\n" + d.machine_id;
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
