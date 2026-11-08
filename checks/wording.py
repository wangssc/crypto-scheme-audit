# -*- coding: utf-8 -*-
"""表述越位：方案阶段不该出现「符合」。

为什么：方案是「打算怎么做」，「符合」是「已经做到并验证过」——
那需要实施证据 + 测评结论，方案阶段拿不出来。写了「符合」，
评审时要么被要求删，要么被追问证据。

允许的说法（SPEC 4.3）：
    设计满足 / 满足 / 依赖云商提供 / 待验证 / 部分满足 / 不适用

这一条最容易误报，所以判定里排除了三类：
1. 「不符合」——里面含「符合」两个字，但意思相反
2. 「整改后符合」——SPEC 明确允许
3. 「符合性」——是名词（如「符合性分析」），不是下结论
4. 「符合 GB/T xxx」——是说自己遵循了编写规范，不是对指标的断言

第 3、4 条是我在 SPEC 之外加的。理由：不加就会把章节名和标准引用
全部报成越位，一份正常方案能报出几十条假问题，报告就没人看了。
"""

import re

# 「符合」以及要排除的四类
_RE = re.compile(r"符合")

# 前面是这些词就不是越位
_ALLOW_BEFORE = ("不", "整改后", "未")

# 后面紧跟这些 → 是名词或标准引用，不是断言
_ALLOW_AFTER = ("性",)
_STD_AFTER = re.compile(r"^\s*(?:GB|GM|GA|ISO|IEC|RFC|WS|JR|YD)\s*/?\s*[A-Z]*\s*\d")


def _hit(text):
    """这段文字里有没有「越位的符合」。返回命中的那几处上下文类型，没有就空。"""
    hits = []
    for m in _RE.finditer(text):
        i = m.start()
        before = text[max(0, i - 4):i]
        after = text[m.end():m.end() + 12]

        if any(before.endswith(w) for w in _ALLOW_BEFORE):
            continue
        if after.startswith(_ALLOW_AFTER):
            continue
        if _STD_AFTER.match(after):
            continue
        hits.append(i)
    return hits


def _finding(fid, level, title, detail, location, fix):
    return {"id": fid, "level": level, "title": title,
            "detail": detail, "location": location, "fix": fix}


def run(doc):
    out = []

    # ---- 正文段落 ----
    para_hits = []
    for p in doc.paragraphs:
        if _hit(p["text"]):
            para_hits.append(p["index"])
    if para_hits:
        shown = "、".join(str(i + 1) for i in para_hits[:8])
        more = "（另有 %d 处）" % (len(para_hits) - 8) if len(para_hits) > 8 else ""
        out.append(_finding(
            "W-01", "critical", "自评表述越位",
            "正文第 %s 段出现「符合」%s。方案阶段没有实施证据，"
            "这个结论需要测评才能下。" % (shown, more),
            "正文 %d 处" % len(para_hits),
            "改成「设计满足」「满足」「待验证」或「部分满足」；"
            "确实要写「符合」的，加一句依据（如测评报告编号）",
        ))

    # ---- 表格 ----
    for ti, table in enumerate(doc.tables, 1):
        rows = []
        for ri, row in enumerate(table, 1):
            for cell in row:
                if _hit(cell):
                    rows.append(ri)
                    break
        if rows:
            shown = "、".join(str(r) for r in rows[:8])
            more = "（另有 %d 行）" % (len(rows) - 8) if len(rows) > 8 else ""
            out.append(_finding(
                "W-02", "critical", "指标自评表里有「符合」",
                "表 %d 第 %s 行出现「符合」%s" % (ti, shown, more),
                "表 %d" % ti,
                "自评列改成设计层面的说法（设计满足 / 待验证 / 部分满足）；"
                "「符合」留给测评结论",
            ))

    return out
