# -*- coding: utf-8 -*-
"""指标覆盖：技术 22 项 + 管理 19 项，共 41 行的对照表。

做法是「先从表格里把条款号和级别抠出来，再跟 SPEC 4.2 的清单对」。
不从正文里找指标——正文写法千变万化，对不准；对照表是方案里唯一
结构化的地方，对它就够了。

找不到对照表就报一条 critical，**不猜**。硬凑出来的覆盖结论比没有更糟。
"""

import re

# SPEC 4.2：级别不可改，与 GB/T 39786-2021 原文一致
TECH_INDICATORS = [
    ("8.1 a", "宜"), ("8.1 b", "宜"), ("8.1 c", "宜"),
    ("8.2 a", "应"), ("8.2 b", "宜"), ("8.2 c", "应"), ("8.2 d", "宜"), ("8.2 e", "可"),
    ("8.3 a", "应"), ("8.3 b", "应"), ("8.3 c", "宜"), ("8.3 d", "宜"),
    ("8.3 e", "宜"), ("8.3 f", "宜"),
    ("8.4 a", "应"), ("8.4 b", "宜"), ("8.4 c", "宜"), ("8.4 d", "应"),
    ("8.4 e", "应"), ("8.4 f", "宜"), ("8.4 g", "宜"), ("8.4 h", "宜"),
]

# 管理 19 项：GB/T 39786-2021 第 8 章 8.5 ~ 8.8 原文逐条抄录。
# 注意第三级的管理要求编号是 8.5~8.8，不是第 9 章的 9.1~9.8——
# 9.x 是第四级的要求，抄错了整张表就对不上。
# 这 19 条**全部是「应」**，没有「宜」也没有「可」。这是标准原文如此，
# 不是我们统一填的：管理要求不给企业留选择余地。
MGMT_INDICATORS = [
    # 8.5 管理制度（6 条）
    ("8.5 a", "应"),   # 应具备密码应用安全管理制度
    ("8.5 b", "应"),   # 应根据密码应用方案建立密钥管理规则
    ("8.5 c", "应"),   # 应对日常管理操作建立操作规程
    ("8.5 d", "应"),   # 应定期论证审定制度合理性并修订
    ("8.5 e", "应"),   # 应明确发布流程并进行版本控制
    ("8.5 f", "应"),   # 应保存操作规程的执行记录
    # 8.6 人员管理（5 条）
    ("8.6 a", "应"),   # 相关人员应了解并遵守法规与制度
    ("8.6 b", "应"),   # 应建立岗位责任制度（含密钥管理员/审计员/操作员分设）
    ("8.6 c", "应"),   # 应建立上岗人员培训制度
    ("8.6 d", "应"),   # 应定期对密码应用安全岗位人员进行考核
    ("8.6 e", "应"),   # 应建立关键人员保密和调离制度
    # 8.7 建设运行（5 条）
    ("8.7 a", "应"),   # 应制定密码应用方案
    ("8.7 b", "应"),   # 应确定密钥种类、体系及生存周期环节
    ("8.7 c", "应"),   # 应按照方案实施建设
    ("8.7 d", "应"),   # 投入运行前应进行密码应用安全性评估
    ("8.7 e", "应"),   # 运行中应严格执行制度、定期评估与攻防对抗演习
    # 8.8 应急处置（3 条）
    ("8.8 a", "应"),   # 应制定应急策略、做好准备、及时处置
    ("8.8 b", "应"),   # 事件发生后应及时向主管部门报告
    ("8.8 c", "应"),   # 处置完成后应报告事件及处置情况
]

TOTAL_ROWS = 41

_RE_CLAUSE = re.compile(r"(\d{1,2})\s*[.．]\s*(\d{1,2})\s*[\)）]?\s*([a-z])?")
_RE_HEADER = re.compile(r"条款|序号|指标|要求|级别|自评|编号")


def _parse_clause(cell):
    """从单元格里抠出 `8.2 b` 这种规范写法，抠不出就 None。"""
    s = (cell or "").strip()
    if not s or len(s) > 24:      # 太长的是描述不是条款号
        return None
    m = _RE_CLAUSE.search(s)
    if not m:
        return None
    major, minor, letter = m.group(1), m.group(2), m.group(3)
    major, minor = int(major), int(minor)
    if not (8 <= major <= 9 and 1 <= minor <= 9):
        return None
    return "%d.%d %s" % (major, minor, letter) if letter else "%d.%d" % (major, minor)


def _parse_level(cell):
    """级别单元格 → 应 / 宜 / 可 / 不应。抠不出就 None。"""
    s = (cell or "").strip()
    if not s or len(s) > 12:
        return None
    if "不应" in s:
        return "不应"
    if "不宜" in s:
        return "不宜"
    if "应" in s:
        return "应"
    if "宜" in s:
        return "宜"
    if "可" in s:
        return "可"
    return None


def _find_table(doc):
    """找出最像指标对照表的那张表。

    两条判据，先严后宽：
    1. 表头第一行含「条款」，且至少两行能解析出条款号 → 就是它（表头点名了，不用猜）
    2. 否则退回「条款号行数 ≥ 10」的候选——但这个阈值放宽到 6，
       半张表（比如只列了 5 条）也要能被抓到行数不对，而不是被误判成「没有对照表」。
    """
    fallback, fb_hit = None, 0
    for ti, table in enumerate(doc.tables):
        if not table:
            continue
        head = " ".join(c for c in table[0] if c)
        hit = sum(1 for row in table if any(_parse_clause(c) for c in row))
        if "条款" in head and hit >= 2:
            return ti
        if hit > fb_hit:
            fallback, fb_hit = ti, hit
    if fb_hit >= 6:
        return fallback
    return None


def _columns(table):
    """猜哪一列是条款号、哪一列是级别。"""
    width = max((len(r) for r in table), default=0)
    clause_col, level_col = 0, None
    best_c = 0
    for ci in range(width):
        n = sum(1 for r in table if ci < len(r) and _parse_clause(r[ci]))
        if n > best_c:
            clause_col, best_c = ci, n
    best_l = 0
    for ci in range(width):
        if ci == clause_col:
            continue
        n = sum(1 for r in table if ci < len(r) and _parse_level(r[ci]))
        if n > best_l:
            level_col, best_l = ci, n
    return clause_col, level_col


def _finding(fid, level, title, detail, location, fix):
    return {"id": fid, "level": level, "title": title,
            "detail": detail, "location": location, "fix": fix}


def run(doc):
    out = []
    idx = _find_table(doc)
    if idx is None:
        out.append(_finding(
            "C-01", "critical", "未找到指标对照表",
            "全文没有找到含条款号的指标对照表（技术 22 项 + 管理 19 项，共 41 行）",
            "全文",
            "在第 7 章合规性分析里补一张对照表，逐条列出条款号、级别、自评结论",
        ))
        return out

    table = doc.tables[idx]
    where = "表 %d" % (idx + 1)

    # 去掉表头行再数
    body = [r for r in table if not (r and _RE_HEADER.search(" ".join(r)))]
    rows = len(body)

    if rows != TOTAL_ROWS:
        # 对照表不全就是不全，不按缺几行分轻重：
        # 缺 1 行和缺 6 行在评审眼里是同一件事——这张表没法直接用。
        out.append(_finding(
            "C-02", "critical",
            "对照表行数不对",
            "%s 有 %d 行，按标准应为 %d 行（技术 22 + 管理 19）"
            % (where, rows, TOTAL_ROWS),
            where,
            "补齐缺的行；如果某些指标不适用，也要单独列一行写「不适用」，不要省略",
        ))

    clause_col, level_col = _columns(table)
    present = {}
    for row in body:
        if clause_col >= len(row):
            continue
        c = _parse_clause(row[clause_col])
        if not c:
            continue
        lv = _parse_level(row[level_col]) if level_col is not None and level_col < len(row) else None
        present.setdefault(c, lv)

    # ---- 技术 22 项：缺了哪条 ----
    missing = [c for c, _ in TECH_INDICATORS if c not in present]
    if missing:
        out.append(_finding(
            "C-03", "critical", "技术指标有遗漏",
            "%s 缺 %d 条技术指标：%s" % (where, len(missing), "、".join(missing)),
            where,
            "把缺的条款补进对照表：8.1 物理环境 3 条、8.2 网络通信 5 条、"
            "8.3 设备计算 6 条、8.4 应用数据 8 条",
        ))

    # ---- 级别对不对 ----
    wrong = []
    for clause, level in TECH_INDICATORS:
        got = present.get(clause)
        if got is None:
            continue                     # 缺的上面已经报过，不重复
        if got != level:
            wrong.append((clause, level, got))
    if wrong:
        shown = "；".join("条款 %s 应为『%s』，方案写的是『%s』" % (c, want, got)
                         for c, want, got in wrong[:6])
        more = "（另有 %d 条）" % (len(wrong) - 6) if len(wrong) > 6 else ""
        out.append(_finding(
            "C-04", "critical", "指标级别与标准不一致",
            shown + more,
            where,
            "级别按 GB/T 39786-2021 第三级原文填，不要按项目自行升降级",
        ))

    # ---- 管理 19 项：缺了哪条 ----
    mgmt_missing = [c for c, _ in MGMT_INDICATORS if c not in present]
    if mgmt_missing:
        out.append(_finding(
            "C-05", "critical", "管理指标有遗漏",
            "%s 缺 %d 条管理指标：%s" % (where, len(mgmt_missing), "、".join(mgmt_missing)),
            where,
            "把缺的条款补进对照表：8.5 管理制度 6 条、8.6 人员管理 5 条、"
            "8.7 建设运行 5 条、8.8 应急处置 3 条",
        ))

    # ---- 管理部分的级别也要对 ----
    mgmt_wrong = []
    for clause, level in MGMT_INDICATORS:
        got = present.get(clause)
        if got is None:
            continue                     # 缺的上面已经报过
        if got != level:
            mgmt_wrong.append((clause, level, got))
    if mgmt_wrong:
        shown = "；".join("条款 %s 应为『%s』，方案写的是『%s』" % (c, want, got)
                         for c, want, got in mgmt_wrong[:6])
        more = "（另有 %d 条）" % (len(mgmt_wrong) - 6) if len(mgmt_wrong) > 6 else ""
        out.append(_finding(
            "C-06", "critical", "管理指标级别与标准不一致",
            shown + more,
            where,
            "管理 19 项在 GB/T 39786-2021 第三级里全部是「应」，"
            "不存在「宜」或「可」——把级别改回原文",
        ))

    return out
