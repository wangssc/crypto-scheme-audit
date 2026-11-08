# -*- coding: utf-8 -*-
"""F-01 ~ F-04：排版与格式。

这四项都是「不影响内容对错、但会让评审第一印象变差」的问题，
所以除了手打标题（结构性）用 warn，其余用 hint，不参与打分。
"""

import re

CHAPTERS = ["背景", "系统概述", "需求分析", "目标与原则",
            "密码应用设计", "安全管理", "合规性分析", "实施保障"]

# 8.2b —— 数字和字母之间没有分隔。后面不能紧跟字母或数字（"8.2bc" 不算），
# 但允许空格、右括号、句号——「8.2b 的要求」和「8.2b)」都要能报出来。
_RE_TIGHT = re.compile(r"(?<![\d.])\d{1,2}\s*[.．]\s*\d{1,2}[a-z](?![a-z\d])")
# 8.2-B —— 用了连字符
_RE_DASH = re.compile(r"(?<![\d.])\d{1,2}\s*[.．]\s*\d{1,2}\s*[-－—]\s*[a-z](?![a-z])")
# 占位符
_RE_PLACEHOLDER = [
    ("TODO", re.compile(r"\bTODO\b", re.I)),
    ("TBD", re.compile(r"\bTBD\b", re.I)),
    ("XXX", re.compile(r"\bX{3,}\b", re.I)),
    ("待补充", re.compile(r"待补充")),
    ("空方括号", re.compile(r"【\s*】")),
]


def _finding(fid, level, title, detail, location, fix):
    return {"id": fid, "level": level, "title": title,
            "detail": detail, "location": location, "fix": fix}


def run(doc):
    out = []

    # ---- F-01 同一张表内列数不一致 ----
    for ti, table in enumerate(doc.tables, 1):
        if not table:
            continue
        counts = {}
        for ri, row in enumerate(table, 1):
            counts.setdefault(len(row), []).append(ri)
        if len(counts) > 1:
            main = max(counts, key=lambda k: len(counts[k]))
            odd = [r for k, rows in counts.items() if k != main for r in rows]
            out.append(_finding(
                "F-01", "hint", "表格列数不一致",
                "表 %d 里有 %d 种列数（多数是 %d 列），第 %s 行跟别的行不一样"
                % (ti, len(counts), main, "、".join(str(r) for r in odd[:8])),
                "表 %d" % ti,
                "统一列数；合并单元格要合并得整齐，别一边合并一边不合并",
            ))

    # ---- F-02 有没有用 Word 标题样式 ----
    if not doc.headings:
        hit = sum(1 for c in CHAPTERS if c in doc.full_text)
        if hit >= 3:
            out.append(_finding(
                "F-02", "warn", "没有使用 Word 标题样式",
                "文档里出现了 %d 个章节名，但没有任何一个用了标题样式。"
                "章节标题是手打的。" % hit,
                "全文",
                "用「开始 → 样式 → 标题 1/2/3」重排章节标题。"
                "手打标题会导致自动目录、导航窗格全部失效",
            ))

    # ---- F-03 条款号格式 ----
    tight, dash = [], []
    for p in doc.paragraphs:
        if _RE_TIGHT.search(p["text"]):
            tight.append(p["index"])
        if _RE_DASH.search(p["text"]):
            dash.append(p["index"])
    for ti, table in enumerate(doc.tables, 1):
        for row in table:
            for cell in row:
                if _RE_TIGHT.search(cell):
                    tight.append(-ti)
                    break
                if _RE_DASH.search(cell):
                    dash.append(-ti)
                    break

    if tight:
        out.append(_finding(
            "F-03", "hint", "条款号缺分隔",
            "有 %d 处条款号写成「8.2b」这种数字紧贴字母的形式" % len(tight),
            "正文 / 表格",
            "写成「8.2 b)」——数字、空格、字母、右括号，四段都要有",
        ))
    if dash:
        out.append(_finding(
            "F-03", "hint", "条款号用了连字符",
            "有 %d 处条款号写成「8.2-B」这种带连字符的形式" % len(dash),
            "正文 / 表格",
            "改成「8.2 b)」，别用连字符——跟标准原文对不上，检索会漏",
        ))

    # ---- F-04 占位符残留 ----
    found = {}
    for label, pat in _RE_PLACEHOLDER:
        locs = []
        for p in doc.paragraphs:
            if pat.search(p["text"]):
                locs.append(("正文", p["index"]))
        for ti, table in enumerate(doc.tables, 1):
            for row in table:
                hit = any(pat.search(cell) for cell in row)
                if hit:
                    locs.append(("表 %d" % ti, ti))
                    break
        if locs:
            found[label] = locs

    if found:
        parts = []
        total = 0
        for label, locs in found.items():
            total += len(locs)
            where = "、".join(sorted({w for w, _ in locs}))
            parts.append("%s（%s）" % (label, where))
        out.append(_finding(
            "F-04", "warn", "有占位符没填",
            "文档里还有 %d 处占位符：%s" % (total, "；".join(parts)),
            "正文 / 表格",
            "交出去之前全文搜一遍 TODO / XXX / 待补充 / 【】，全部替换成实际内容或删掉",
        ))

    return out
