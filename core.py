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
