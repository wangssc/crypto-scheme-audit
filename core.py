#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""crypto-scheme-audit 的核心：读 docx、跑规则、打分、出报告。

设计原则：这里只做「把文档变成数据结构」和「把结果变成人话」。
所有业务判断都在 checks/ 里，这里一行规则都不写。
"""

import datetime
import math
import os
import re
import sys

try:
    import docx  # python-docx
except ImportError:  # pragma: no cover
    docx = None


GRADE_TABLE = [(90, "A", "结构完整，可以直接提交评审"),
               (80, "B", "基本完整，修完 must 项即可"),
               (70, "C", "有明显缺口，需要补写"),
               (0,  "D", "缺口较多，建议重写受影响章节")]

LEVEL_WEIGHT = {"critical": 20, "warn": 6, "hint": 0}


class SchemeDoc:
    """把 docx 拍平成检查器好用的形状。"""

    def __init__(self, path):
        self.path = path
        self.filename = os.path.basename(path)
        self.docx_bytes = os.path.getsize(path)
        self.paragraphs = []
        self.headings = []
        self.tables = []
        self._load()

    def _load(self):
        d = docx.Document(self.path)
        for i, p in enumerate(d.paragraphs):
            text = (p.text or "").strip()
            if not text:
                continue
            style = ""
            try:
                style = p.style.name or ""
            except Exception:
                pass
            self.paragraphs.append({"text": text, "style": style, "index": i})
            lvl = _style_level(style)
            if lvl:
                self.headings.append({"text": text, "level": lvl, "index": i})

        for t in d.tables:
            rows = []
            for row in t.rows:
                cells = []
                for c in row.cells:
                    cells.append((c.text or "").strip())
                rows.append(cells)
            self.tables.append(rows)

    @property
    def full_text(self):
        return "\n".join(p["text"] for p in self.paragraphs)


def _style_level(style):
    """把 'Heading 1' / '标题 1' / 'heading1' 统一成 1/2/3。"""
    if not style:
        return 0
    s = style.lower().replace(" ", "")
    m = re.search(r"(?:heading|标题)(\d+)", s)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return 0
    return 0


def score(findings):
    """指数衰减，与 electron-surface-audit 同一套公式。"""
    penalty = 0
    worst = None
    for f in findings:
        lv = f.get("level", "warn")
        penalty += LEVEL_WEIGHT.get(lv, 0)
        if lv == "critical":
            worst = "critical"

    total = round(100 * math.exp(-penalty / 90))
    capped = False
    if worst == "critical" and total > 65:
        total = 65
        capped = True

    for floor, grade, label in GRADE_TABLE:
        if total >= floor:
            return {"score": total, "grade": grade, "label": label,
                    "penalty": penalty, "capped_by_critical": capped,
                    "counts": _count_levels(findings)}
    return {"score": total, "grade": "D", "label": GRADE_TABLE[-1][2],
            "penalty": penalty, "capped_by_critical": capped,
            "counts": _count_levels(findings)}


def _count_levels(findings):
    c = {"critical": 0, "warn": 0, "hint": 0}
    for f in findings:
        lv = f.get("level", "warn")
        if lv in c:
            c[lv] += 1
    return c


NOT_ASSESSED = {
    "score": None,
    "grade": "?",
    "label": "not assessed",
    "penalty": 0,
    "capped_by_critical": False,
    "counts": {"critical": 0, "warn": 0, "hint": 0},
}


def render_markdown(doc, findings, sc, assessed=True):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    L = []
    L.append("# 密码应用方案自检报告\n")
    L.append("| 项 | 值 |")
    L.append("|---|---|")
    L.append("| 方案 | %s |" % doc.filename)
    L.append("| 检查时间 | %s |" % now)
    L.append("| 标准 | GB/T 39786-2021 第三级 |")
    L.append("| 段落 / 表格 | %d / %d |" % (len(doc.paragraphs), len(doc.tables)))
    L.append("")

    L.append("## 一、结论\n")
    if not assessed:
        L.append("**未评估。** 这份文档里找不到方案的八章结构，")
        L.append("可能是：不是方案文件、扫描件、或者章节标题没用 Word 标题样式。")
        L.append("**这不是「通过」，也不代表 0 分。**\n")
    else:
        L.append("| 项 | 结果 |")
        L.append("|---|---|")
        L.append("| 综合评分 | %d / 100（%s） |" % (sc["score"], sc["grade"]))
        L.append("| 判定 | %s |" % sc["label"])
        L.append("| 必须修 | %d 项 |" % sc["counts"]["critical"])
        L.append("| 建议改 | %d 项 |" % sc["counts"]["warn"])
        L.append("| 提示 | %d 项 |" % sc["counts"]["hint"])
        if sc["capped_by_critical"]:
            L.append("| 说明 | 存在必须修项，总分已封顶 65 |")
        L.append("")

    for lv, title in (("critical", "二、必须修"),
                      ("warn", "三、建议改"),
                      ("hint", "四、提示（不参与评分）")):
        rows = [f for f in findings if f.get("level") == lv]
        if not rows:
            continue
        L.append("## %s\n" % title)
        L.append("| 编号 | 位置 | 问题 | 怎么改 |")
        L.append("|---|---|---|---|")
        for f in rows:
            L.append("| %s | %s | %s | %s |" % (
                f.get("id", ""), _esc(f.get("location", "")),
                _esc(f.get("title", "")) + ("：" + _esc(f.get("detail", "")) if f.get("detail") else ""),
                _esc(f.get("fix", ""))))
        L.append("")

    L.append("## 五、工具没检查什么\n")
    L.append("- 不判断技术方案是否可行、密码产品选型是否合理")
    L.append("- 不验证方案里提到的密码产品是否真实存在、是否有资质")
    L.append("- 不读图片内容（图片里可能藏着表格和漏洞，工具看不见）")
    L.append("- 扫描件 PDF 不支持，只支持 .docx")
    L.append("- 跨章一致性只做提示，不做判定——那需要理解语义，容易误报")
    L.append("")
    return "\n".join(L)


def _esc(s):
    if not s:
        return ""
    return str(s).replace("|", "\\|").replace("\n", " ")


def _h(s):
    """HTML 转义。和 _esc 分开写：那边是 Markdown，这边是 HTML。"""
    if not s:
        return ""
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


_HTML_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:"Microsoft YaHei","PingFang SC","Hiragino Sans GB",
 "Source Han Sans SC",sans-serif;background:#f5f6f7;color:#1f2328;
 line-height:1.7;padding:32px 16px 64px}
.wrap{max-width:860px;margin:0 auto}
h1{font-size:22px;font-weight:600;letter-spacing:.5px}
.meta{color:#6b7280;font-size:13px;margin-top:10px;line-height:2}
.meta b{color:#374151;font-weight:600}
.card{background:#fff;border:1px solid #e5e7eb;border-radius:12px;
 padding:24px;margin-top:20px}
.verdict{display:flex;align-items:center;gap:28px;flex-wrap:wrap}
.num{font-size:56px;font-weight:700;line-height:1;letter-spacing:-2px}
.num small{font-size:18px;font-weight:400;color:#9ca3af;margin-left:4px}
.gA{color:#15803d}.gB{color:#4d7c0f}.gC{color:#b45309}
.gD{color:#c2410c}.gE{color:#b91c1c}.gQ{color:#6b7280}
.verdict .txt{flex:1;min-width:220px}
.verdict .txt strong{display:block;font-size:16px;margin-bottom:6px}
.verdict .txt span{color:#6b7280;font-size:14px}
.counts{display:flex;gap:12px;margin-top:20px;flex-wrap:wrap}
.pill{flex:1;min-width:130px;border-radius:10px;padding:14px 16px;
 border:1px solid #e5e7eb;background:#fafafa}
.pill b{display:block;font-size:26px;font-weight:700;line-height:1.2}
.pill span{font-size:13px;color:#6b7280}
.pill.c{border-color:#fecaca;background:#fef2f2}
.pill.c b{color:#b91c1c}
.pill.w{border-color:#fed7aa;background:#fff7ed}
.pill.w b{color:#c2410c}
.pill.h b{color:#6b7280}
.sec{margin-top:28px}
.sec h2{font-size:15px;font-weight:600;color:#374151;
 padding-bottom:8px;border-bottom:1px solid #eceff1;margin-bottom:14px}
.item{border-left:3px solid #e5e7eb;padding:12px 0 12px 16px;margin-bottom:14px}
.item.c{border-color:#ef4444}
.item.w{border-color:#f59e0b}
.item.h{border-color:#d1d5db}
.item .hd{display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}
.tag{font-size:11px;font-weight:700;padding:2px 7px;border-radius:5px;
 letter-spacing:.5px;flex-shrink:0}
.tag.c{background:#fee2e2;color:#991b1b}
.tag.w{background:#ffedd5;color:#9a3412}
.tag.h{background:#f3f4f6;color:#4b5563}
.item .ttl{font-size:15px;font-weight:600}
.item .loc{font-size:12px;color:#9ca3af;font-family:Consolas,monospace}
.item p{font-size:14px;color:#4b5563;margin-top:6px}
.item .fix{font-size:13px;color:#15803d;margin-top:8px;
 padding-left:18px;position:relative}
.item .fix::before{content:"→";position:absolute;left:0;color:#22c55e}
.empty{color:#6b7280;font-size:14px;padding:8px 0}
.warnbox{background:#fffbeb;border:1px solid #fde68a;border-radius:10px;
 padding:18px 20px;margin-top:20px}
.warnbox strong{color:#92400e;display:block;margin-bottom:8px;font-size:15px}
.warnbox p{font-size:14px;color:#78350f;margin-top:6px}
.limits li{font-size:13.5px;color:#6b7280;margin:6px 0 6px 18px}
footer{max-width:860px;margin:28px auto 0;color:#9ca3af;font-size:12px;
 line-height:1.9;text-align:center}
@media print{body{background:#fff;padding:0}.card{border:none;padding:0}}
"""


def render_html(doc, findings, sc, assessed=True):
    """自包含 HTML 报告。不引用任何外部资源——断网也能看。"""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    P = []
    P.append("<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">")
    P.append("<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">")
    P.append("<title>方案自检 - %s</title>" % _h(doc.filename))
    P.append("<style>%s</style></head><body><div class=\"wrap\">" % _HTML_CSS)

    P.append("<h1>密码应用方案自检报告</h1>")
    P.append("<div class=\"meta\">")
    P.append("方案：<b>%s</b><br>" % _h(doc.filename))
    P.append("依据：<b>GB/T 39786-2021 第三级</b>　检查时间：<b>%s</b><br>" % now)
    P.append("读入：%d 个段落 / %d 张表格 / %d 个标题"
             % (len(doc.paragraphs), len(doc.tables), len(doc.headings)))
    P.append("</div>")

    if not assessed:
        P.append("<div class=\"warnbox\">")
        P.append("<strong>未评估 —— 这不等于「通过」</strong>")
        P.append("<p>这份文档里找不到方案的八章结构。可能是：不是方案文件、"
                 "是扫描件、或者章节标题没用 Word 的「标题」样式。</p>")
        P.append("<p>工具没有给出分数，也没有说它合格。请先确认文件对，"
                 "或者把章节标题套上「标题 1」。</p>")
        P.append("</div>")
        P.append("<div class=\"card\"><div class=\"sec\"><h2>工具没检查什么</h2><ul class=\"limits\">")
        for line in _LIMITS:
            P.append("<li>%s</li>" % _h(line))
        P.append("</ul></div></div>")
        P.append("<footer>crypto-scheme-audit　·　只做结构与覆盖检查，"
                 "不替代人工评审</footer></div></body></html>")
        return "".join(P)

    cls = {"A": "gA", "B": "gB", "C": "gC", "D": "gD", "E": "gE"}.get(sc["grade"], "gQ")
    P.append("<div class=\"card\"><div class=\"verdict\">")
    P.append("<div class=\"num %s\">%d<small>/100</small></div>" % (cls, sc["score"]))
    P.append("<div class=\"txt\"><strong>等级 %s　%s</strong>" % (_h(sc["grade"]), _h(sc["label"])))
    if sc["capped_by_critical"]:
        P.append("<span>存在「必须修」项，总分已封顶 65——"
                 "先修完再算分。</span>")
    else:
        P.append("<span>扣分合计 %d" % sc["penalty"])
        if sc["counts"]["hint"]:
            P.append("（提示项不计分）")
        P.append("</span>")
    P.append("</div></div>")

    P.append("<div class=\"counts\">")
    P.append("<div class=\"pill c\"><b>%d</b><span>必须修</span></div>"
             % sc["counts"]["critical"])
    P.append("<div class=\"pill w\"><b>%d</b><span>建议改</span></div>"
             % sc["counts"]["warn"])
    P.append("<div class=\"pill h\"><b>%d</b><span>提示</span></div>"
             % sc["counts"]["hint"])
    P.append("</div></div>")

    for lv, code, title in (("critical", "c", "必须修"),
                            ("warn", "w", "建议改"),
                            ("hint", "h", "提示（不参与评分）")):
        rows = [f for f in findings if f.get("level") == lv]
        P.append("<div class=\"card\"><div class=\"sec\"><h2>%s　%d 项</h2>"
                 % (title, len(rows)))
        if not rows:
            P.append("<div class=\"empty\">这一档没有发现问题。</div>")
        else:
            for f in rows:
                P.append("<div class=\"item %s\">" % code)
                P.append("<div class=\"hd\"><span class=\"tag %s\">%s</span>"
                         % (code, _h(f.get("id", ""))))
                P.append("<span class=\"ttl\">%s</span>" % _h(f.get("title", "")))
                if f.get("location"):
                    P.append("<span class=\"loc\">%s</span>" % _h(f["location"]))
                P.append("</div>")
                if f.get("detail"):
                    P.append("<p>%s</p>" % _h(f["detail"]))
                if f.get("fix"):
                    P.append("<div class=\"fix\">%s</div>" % _h(f["fix"]))
                P.append("</div>")
        P.append("</div></div>")

    P.append("<div class=\"card\"><div class=\"sec\"><h2>工具没检查什么</h2>"
             "<ul class=\"limits\">")
    for line in _LIMITS:
        P.append("<li>%s</li>" % _h(line))
    P.append("</ul></div></div>")

    P.append("<footer>crypto-scheme-audit　·　只做结构与覆盖检查，"
             "不替代人工评审</footer></div></body></html>")
    return "".join(P)


_LIMITS = [
    "不判断技术方案是否可行、密码产品选型是否合理",
    "不验证方案里提到的密码产品是否真实存在、是否有资质",
    "不读图片内容（图片里可能藏着表格和漏洞，工具看不见）",
    "扫描件 PDF 不支持，只支持 .docx",
    "跨章一致性只做提示，不做判定——那需要理解语义，容易误报",
]


def render_text(doc, findings, sc, assessed=True):
    L = []
    L.append("密码应用方案自检  %s" % doc.filename)
    L.append("=" * 46)
    if not assessed:
        L.append("未评估：找不到方案的八章结构。这不是通过。")
        return "\n".join(L)
    L.append("评分 %d/100 (%s)  %s" % (sc["score"], sc["grade"], sc["label"]))
    L.append("必须修 %d / 建议改 %d / 提示 %d" % (
        sc["counts"]["critical"], sc["counts"]["warn"], sc["counts"]["hint"]))
    for lv, tag in (("critical", "[必须修]"), ("warn", "[建议改]"), ("hint", "[提示]")):
        rows = [f for f in findings if f.get("level") == lv]
        if not rows:
            continue
        L.append("")
        for f in rows:
            L.append("%s %s %s  %s" % (tag, f.get("id", ""), f.get("location", ""), f.get("title", "")))
            if f.get("detail"):
                L.append("        %s" % f["detail"])
    return "\n".join(L)
