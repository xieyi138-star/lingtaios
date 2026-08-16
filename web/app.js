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
    '<button class="chip-btn" id="pd-open">📁 打开项目目录</button></div>';

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
  const pct = h.total ? Math.round(h.ok / h.total * 100) : 0;
  const R = 52, C = 2 * Math.PI * R;
  const ringColor = h.missing.length ? "#fb7185" : "#34d399";
  const ring = '<div class="hero-ring">' +
    '<svg width="128" height="128" viewBox="0 0 128 128"><defs>' +
    '<linearGradient id="ringGrad" x1="0" y1="1" x2="1" y2="0">' +
    '<stop offset="0" stop-color="' + ringColor + '"/><stop offset="1" stop-color="#6ea8fe"/>' +
    "</linearGradient></defs>" +
    '<circle class="ring-bg" cx="64" cy="64" r="' + R + '"/>' +
    '<circle class="ring-val" cx="64" cy="64" r="' + R + '" stroke-dasharray="' + C + '" stroke-dashoffset="' + (C * (1 - pct / 100)).toFixed(1) + '"/>' +
    '</svg><div class="ring-num"><b>' + h.ok + "</b><span>/ " + h.total + " 真源在位</span></div></div>";
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
    '<button class="chip-btn" id="h-refresh">🔄 深查（重算全部真源）</button></div>' +
    '<p class="muted-note">快照生成于 ' + esc(DATA.generated_at) + " · 数据全部机器生成，人不手写</p>" +
    '<p class="muted-note" id="h-note"></p></div>';

  const ev = DATA.evolution || {};
  const staleN = (ev.stale_handoffs || []).length;
  if (h.missing.length || h.identical_pairs.length || staleN) {
    html += '<div class="section"><h2>🔴 先修这里</h2><ul>' +
      h.missing.map(m => "<li>" + esc(m.path) + " → " + esc(m.resolved) + "</li>").join("") +
      h.identical_pairs.map(p => "<li>同名同内容双份：" + esc(p.a) + " ⟷ " + esc(p.b) + "</li>").join("") +
      (staleN ? "<li>🟡 有 " + staleN + " 个项目的交接超 7 天没更新——该生核了（见「设置 → 进化审计」）</li>" : "") +
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
    (active.length > 6 ? '<p class="muted-note">更多见「项目」页 →</p>' : "") +
    '<p class="muted-note">其余 ' + (DATA.projects.length - active.length) +
    ' 个未装系统的项目（可能没完工）→ 「项目」页全部可点开续做</p></div>';

  main.innerHTML = html;
  attachCardClicks();
  document.getElementById("h-newproj").onclick = () => go("newproj");
  document.getElementById("h-goto-pitfall").onclick = e => { e.preventDefault(); go("pitfall"); };
  document.getElementById("h-goto-sys").onclick = e => { e.preventDefault(); go("system"); };
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
function renderProjects() {
  const active = DATA.projects.filter(isActive)
    .sort((a, b) => (organN(b) - organN(a)) || (b.alarms.length - a.alarms.length));
  const rest = DATA.projects.filter(p => !isActive(p));
  let html = '<div class="section"><h2>装系统的项目（' + active.length + "）</h2><div class=\"cards\">" +
    active.map(slimCard).join("") + "</div></div>";
  html += '<div class="section"><details open><summary>未装系统的项目（' + rest.length +
    " · 没完工也能点开续做——点进去看它的交接/施工图）</summary>" +
    '<div class="cards" style="margin-top:10px">' +
    rest.map(slimCard).join("") + "</div></details></div>";
  main.innerHTML = html;
  attachCardClicks();
}

/* ---------- 坑库：搜索 + 分区 + 分页 ---------- */
let PIT_ROWS = [];
const PIT_PAGE = 20;
function renderPitfall() {
  PIT_ROWS = DATA.pitfall.rows;
  const cols = DATA.pitfall.columns || [];
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
  const cols = DATA.pitfall.columns || [];
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
    '<div class="section"><h3>🔴 断头 / 双份（只读，去「方法」页查装配图修指针）</h3>' +
    ((ev.broken || []).map(m => "<p>断头：" + esc(m.path) + "</p>").join("") +
     (ev.identical_pairs || []).map(p => "<p>双份：" + esc(p.a) + " ⟷ " + esc(p.b) + "</p>").join("") ||
     '<p class="muted-note">无。</p>') + "</div>";
  let any = false;
  for (const [title, items, kind, fmt] of secs) {
    if (!items.length) continue;
    any = true;
    html += '<div class="section"><h3>' + esc(title) + "（" + items.length + "）</h3>" +
      items.map((r, i) =>
        '<label class="q-label"><input type="checkbox" data-kind="' + kind + '" data-id="' +
        esc(r["编号"] || r["project"] || i) + '" data-proj="' + esc(r["path"] || "") + '"> ' +
        esc(fmt(r)) + "</label>").join("") + "</div>";
  }
  if (!any) {
    html += '<div class="ok-box">✓ 五清单全空——壳是干净的，继续生长。</div>';
  } else {
    html += '<div class="filter-row"><button class="chip-btn bad-btn" id="ev-delete">🗑 删除所选（不可恢复，git 有回滚点）</button></div>' +
      '<div id="ev-result"></div>';
  }
  box.innerHTML = html;
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
  let html = '<div class="section"><h2>新项目 · 填表 → 点创建 → 全部自动装好</h2>' +
    '<div class="form-grid">' +
    '<label>项目名<input id="np-name" placeholder="如：my-tool"></label>' +
    '<label>落点<select id="np-root">' +
    '<option value="nexus">Nexus 根（C:\\nexus_local 下）</option>' +
    '<option value="d">D 盘根</option>' +
    '<option value="custom">自定义路径</option></select></label>' +
    '<label id="np-custom-wrap" style="display:none">自定义路径<input id="np-custom" placeholder="D:\\myprojects"></label>' +
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
  document.getElementById("np-root").onchange = e => {
    document.getElementById("np-custom-wrap").style.display =
      e.target.value === "custom" ? "" : "none";
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
}

document.querySelectorAll(".nav-btn").forEach(b => b.onclick = () => go(b.dataset.page));

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

fetch("data.json")
  .then(r => r.json())
  .then(d => {
    DATA = d;
    document.getElementById("nav-foot").textContent =
      "生成 " + d.generated_at + "\n" + d.machine_id;
    go("home");
  })
  .catch(e => {
    main.innerHTML = '<div class="section"><h2>✗ 数据加载失败</h2><p>' + esc(String(e)) + "<br>请先跑 <code>python -X utf8 dashboard.py</code> 生成数据。</p></div>";
  });
