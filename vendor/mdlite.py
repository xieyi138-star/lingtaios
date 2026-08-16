# -*- coding: utf-8 -*-
"""mdlite · 本体系文档方言的极简 markdown 渲染器（零依赖）

只支持本体系文档实际用到的方言：
  # ~ #### 标题、| 表格 |、**加粗**、`行内码`、``` 围栏代码块、> 引用、
  - / 1. 列表、[文字](url)、--- 分隔线、⚠ ✅ 等符号原样。
不认识的块原样保留（HTML 转义后），**不静默吞内容**。

用法:
    from mdlite import render, table_rows
    html = render(text)                        # 全文渲染
    rows = table_rows(text, "判定侧")          # 抽某 ## 小节下所有表格为 dict 行
    python -X utf8 mdlite.py --selftest        # 破坏性自检
"""
import re
import sys

_ESC = [("&", "&amp;"), ("<", "&lt;"), (">", "&gt;")]


def _esc(s):
    for a, b in _ESC:
        s = s.replace(a, b)
    return s


_INLINE = [
    (re.compile(r"`([^`]+)`"), r"<code>\1</code>"),
    (re.compile(r"\*\*([^*]+)\*\*"), r"<strong>\1</strong>"),
    (re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)"), r'<a href="\2">\1</a>'),
]


def _inline(s):
    s = _esc(s)
    for rx, rep in _INLINE:
        s = rx.sub(rep, s)
    return s


def _split_row(line):
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def _is_sep(row):
    return all(re.fullmatch(r":?-{2,}:?", c or "-") for c in row)


def _aligns(row):
    out = []
    for c in row:
        l = c.startswith(":")
        r = c.endswith(":")
        out.append("center" if l and r else ("right" if r else ("left" if l else "")))
    return out


def render(text):
    """块级渲染。表格必须「表头行 + 分隔行」连在一起才成表，否则按段落。"""
    lines = text.split("\n")
    out = []
    i, n = 0, len(lines)

    def flush_para(buf):
        if buf:
            out.append("<p>%s</p>" % "<br>".join(_inline(x) for x in buf))
            buf[:] = []

    para = []
    while i < n:
        line = lines[i]

        # 围栏代码块
        m = re.match(r"^```(.*)$", line)
        if m:
            flush_para(para)
            buf = []
            i += 1
            while i < n and not lines[i].startswith("```"):
                buf.append(_esc(lines[i]))
                i += 1
            i += 1  # 吃掉收尾 ```
            out.append("<pre><code>%s</code></pre>" % "\n".join(buf))
            continue

        # 标题
        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            flush_para(para)
            lv = len(m.group(1))
            out.append("<h%d>%s</h%d>" % (lv, _inline(m.group(2)), lv))
            i += 1
            continue

        # 分隔线
        if re.match(r"^\s*---+\s*$", line):
            flush_para(para)
            out.append("<hr>")
            i += 1
            continue

        # 表格：当前行 + 下一行是分隔行
        if line.strip().startswith("|") and i + 1 < n and _is_sep(_split_row(lines[i + 1])):
            flush_para(para)
            header = _split_row(line)
            aligns = _aligns(_split_row(lines[i + 1]))
            i += 2
            body = []
            while i < n and lines[i].strip().startswith("|"):
                body.append(_split_row(lines[i]))
                i += 1
            th = "".join(
                '<th%s>%s</th>' % ((' align="%s"' % a) if a else "", _inline(c))
                for c, a in zip(header, aligns))
            out.append("<table><thead><tr>%s</tr></thead><tbody>" % th)
            for row in body:
                tds = []
                for j, cell in enumerate(row):
                    a = aligns[j] if j < len(aligns) else ""
                    tds.append('<td%s>%s</td>' % ((' align="%s"' % a) if a else "", _inline(cell)))
                out.append("<tr>%s</tr>" % "".join(tds))
            out.append("</tbody></table>")
            continue

        # 引用（连续 > 行合并）
        if line.startswith(">"):
            flush_para(para)
            buf = []
            while i < n and lines[i].startswith(">"):
                buf.append(lines[i][1:].lstrip())
                i += 1
            out.append("<blockquote>%s</blockquote>" % "<br>".join(_inline(x) for x in buf))
            continue

        # 列表（连续 - / N. 行合并）
        m = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", line)
        if m:
            flush_para(para)
            ordered = m.group(2)[0].isdigit()
            tag = "ol" if ordered else "ul"
            buf = []
            while i < n:
                mm = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", lines[i])
                if not mm:
                    break
                buf.append("<li>%s</li>" % _inline(mm.group(3)))
                i += 1
            out.append("<%s>%s</%s>" % (tag, "".join(buf), tag))
            continue

        # 空行 = 段落边界
        if not line.strip():
            flush_para(para)
            i += 1
            continue

        para.append(line)
        i += 1

    flush_para(para)
    return "".join(out)


def table_rows(text, section=None):
    """抽表格为 dict 行。section 给「## 名字」时只抽该小节；不给则全文。"""
    lines = text.split("\n")
    i, n = 0, len(lines)
    in_section = section is None
    rows = []
    while i < n:
        m = re.match(r"^##\s+(.*)$", lines[i])
        if m:
            in_section = (section is None or m.group(1).strip() == section)
            i += 1
            continue
        if in_section and lines[i].strip().startswith("|") and i + 1 < n \
                and _is_sep(_split_row(lines[i + 1])):
            header = _split_row(lines[i])
            i += 2
            while i < n and lines[i].strip().startswith("|"):
                cells = _split_row(lines[i])
                rows.append(dict(zip(header, cells + [""] * max(0, len(header) - len(cells)))))
                i += 1
        else:
            i += 1
    return rows


def _selftest():
    ok = True

    def ck(c, m):
        nonlocal ok
        print(("  ok " if c else "  ✗ ") + m)
        ok = ok and c

    h = render("# 标题\n\n| a | b |\n|---|---|\n| 1 | **粗** |\n\n> 引用\n\n- x\n- y\n\n```\n<raw>\n```\n\n普通 `码` 与 [链](http://x)")
    ck("<h1>标题</h1>" in h, "标题渲染")
    ck("<table>" in h and "<strong>粗</strong>" in h, "表格+单元格内加粗")
    ck("<blockquote>" in h, "引用")
    ck("<ul><li>x</li><li>y</li></ul>" in h, "列表")
    ck("<pre><code>&lt;raw&gt;</code></pre>" in h, "代码块转义不吞")
    ck("<a href=\"http://x\">链</a>" in h, "行内链接")
    h2 = render("| a | b |\n|---|---|\n| 1 | 2 |")
    ck("<td>1</td><td>2</td>" in h2, "裸表格")

    txt = "## 判定侧\n\n| 编号 | 坑 |\n|---|---|\n| P1 | 甲 |\n| P2 | 乙 |\n\n## 协作\n\n| 编号 | 坑 |\n|---|---|\n| W1 | 丙 |"
    rows = table_rows(txt, "判定侧")
    ck(len(rows) == 2 and rows[0]["编号"] == "P1" and rows[1]["坑"] == "乙", "table_rows 小节抽取")
    ck(len(table_rows(txt)) == 3, "table_rows 全文抽取")
    return ok


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        print("mdlite · 破坏性自检（零依赖）")
        sys.exit(0 if _selftest() else 1)
    import io
    data = sys.stdin.read()
    sys.stdout.write(render(data))
