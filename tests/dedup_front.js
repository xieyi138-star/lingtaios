/* 前端去重逻辑单测：把 wizard 里的去重函数原样搬过来跑 */
let SETUP = { ws: [], extra: [] };

function sameP(a, b) { return String(a).toLowerCase() === String(b).toLowerCase(); }
function has(list, p) { return list.some(x => sameP(x, p)); }
function underAny(list, p) {
  return list.some(w => String(p).toLowerCase().startsWith(String(w).toLowerCase() + "\\"));
}
function alreadyHave(p) {
  return has(SETUP.extra, p) || has(SETUP.ws, p) || underAny(SETUP.ws, p);
}
function addProject(p, whole) {
  if (!p) return "empty";
  if (whole) {
    if (has(SETUP.ws, p)) return "dup";
    SETUP.ws.push(p);
    SETUP.extra = SETUP.extra.filter(x => !sameP(x, p) && !underAny([p], x));
    return "ok";
  }
  if (alreadyHave(p)) return "dup";
  SETUP.extra.push(p);
  return "ok";
}

let pass = 0, fail = 0;
function chk(name, cond, detail) {
  if (cond) { pass++; console.log("[PASS] " + name); }
  else { fail++; console.log("[FAIL] " + name + "  " + (detail || "")); }
}

// 1) 同一个项目加两次
SETUP = { ws: [], extra: [] };
chk("首次添加成功", addProject("D:\\work\\a", false) === "ok");
chk("再加同一个 → dup", addProject("D:\\work\\a", false) === "dup");
chk("只留一份", SETUP.extra.length === 1, JSON.stringify(SETUP.extra));

// 2) 大小写/斜杠差异也算重复
chk("大小写不同也算重复", addProject("d:\\WORK\\a", false) === "dup");

// 3) 先加单个，再加整个父文件夹 → 单个被吸收
SETUP = { ws: [], extra: [] };
addProject("D:\\work\\a", false);
addProject("D:\\work\\b", false);
chk("加整个父文件夹", addProject("D:\\work", true) === "ok");
chk("被罩住的单个项目被清掉", SETUP.extra.length === 0, JSON.stringify(SETUP.extra));
chk("父文件夹进了 ws", SETUP.ws.length === 1);

// 4) 已有整个文件夹，再加它里面的单个 → dup
chk("父文件夹罩住的子项 → dup", addProject("D:\\work\\c", false) === "dup");
chk("父文件夹本身再加 → dup", addProject("D:\\work", true) === "dup");

// 5) 不在父文件夹下的照常能加
chk("别处的项目照常加", addProject("E:\\other\\x", false) === "ok");
chk("最终 extra 只有别处那个", SETUP.extra.length === 1 && SETUP.extra[0] === "E:\\other\\x",
    JSON.stringify(SETUP.extra));

// 6) 前缀相似但不是子目录，不该被误判
SETUP = { ws: ["D:\\work"], extra: [] };
chk("D:\\workshop 不算 D:\\work 的子目录", addProject("D:\\workshop", false) === "ok",
    JSON.stringify(SETUP.extra));

// 7) 空路径
chk("空路径被拒", addProject("", false) === "empty");

console.log("\n" + pass + " passed, " + fail + " failed");
process.exit(fail ? 1 : 0);
