# -*- coding: utf-8 -*-
"""S-01 ~ S-06：结构完整性。

只判断「章节在不在、子节编号全不全」，不判断内容写得对不对。

两条自我约束：
1. 报告里的 detail 只能是章节名、编号、表序号，**不摘录方案原文**。
2. 章节标题写法五花八门（「一、背景」「1. 项目背景」「第一章 背景」），
   一律用「章号 + 固定名称」双条件匹配，不用精确等于。
"""

import re

CHAPTERS = [
    (1, "背景"),
    (2, "系统概述"),
    (3, "需求分析"),
    (4, "目标与原则"),
    (5, "密码应用设计"),
    (6, "安全管理"),
    (7, "合规性分析"),
    (8, "实施保障"),
]

# 密钥管理十环节，SPEC 4.1 给了固定名称
KEY_STAGES = ["生成", "存储", "分发", "使用", "更新",
              "归档", "撤销", "备份", "恢复", "销毁"]

_CN = "一二三四五六七八九十"

# 章号前缀。三种写法都要吃：
#   「第1章 / 第一章」  「1. / 一、/ 1）」  「1 背景」（数字 + 空白）
# 三个分支各自带一个捕获组，取的时候按顺序取第一个非空的。
_PREFIX = re.compile(
    r"^\s*(?:第\s*([一二三四五六七八九十\d]{1,3})\s*[章节]\s*"
    r"|([一二三四五六七八九十]{1,3}|\d{1,3})\s*[、.．)）]\s*"
    r"|(\d{1,3})\s+)"
)

# 去掉章号前缀后剩下的部分，用来跟固定章节名比对
_STRIP = re.compile(
    r"^\s*(?:第\s*[一二三四五六七八九十\d]{1,3}\s*[章节]\s*"
    r"|[一二三四五六七八九十]{1,3}\s*[、.．)）]\s*"
    r"|\d{1,3}\s*[、.．)）]?\s*)"
)

# a) / a） / （a） / a、 四种写法
_MARK = re.compile(r"(?:^|[\s\(（])([a-j])\s*[\)）．.、]")


def _to_int(s):
    if not s:
        return None
    if s.isdigit():
        return int(s)
    if len(s) == 1 and s in _CN:
        return _CN.index(s) + 1
    return None


def _prefix_num(text):
    """取出这一行开头的章号，没有就 None。"""
    m = _PREFIX.match(text)
    if not m:
        return None
    for g in m.groups():
        if g:
            return _to_int(g)
    return None


def _bare(text):
    return _STRIP.sub("", text).strip()


def _heading_like(p, head_indexes):
    """像不像一个标题行。

    在 Word 标题样式里 → 算。
    否则要求：不长（<=40 字）且以章号开头。
    这样可以避开正文里出现的「背景」两个字。
    """
    if p["index"] in head_indexes:
        return True
    t = p["text"]
    return len(t) <= 40 and _prefix_num(t) is not None


def find_chapters(doc):
    """返回 {章号: 段落}。缺的章不出现在里面。"""
    heads = {h["index"] for h in doc.headings}
    out = {}
    for p in doc.paragraphs:
        if not _heading_like(p, heads):
            continue
        text = p["text"]
        num = _prefix_num(text)
        bare = _bare(text)
        for cnum, cname in CHAPTERS:
            if num is not None:
                # 有章号：章号要对得上，名称也要出现在同一行
                if num == cnum and cname in text:
                    out.setdefault(cnum, p)
                    break
            else:
                # 没章号（靠标题样式识别）：名称要在行首附近
                if bare.startswith(cname) or bare == cname:
                    out.setdefault(cnum, p)
                    break
    return out


def _span(paras, found, num):
    """第 num 章覆盖的段落下标区间 [start, end)。下一章起点就是终点。"""
    if num not in found:
        return None
    start = found[num]["index"]
    later = [found[k]["index"] for k in sorted(found) if k > num]
    end = min(later) if later else 10 ** 9
    return start, end


def _within(doc, span):
    if not span:
        return []
    s, e = span
    return [p for p in doc.paragraphs if s <= p["index"] < e]


def _subs_missing(paras, major, minors):
    """在给定段落里找 `major.minor` 编号，返回缺的那些编号字符串。"""
    blob = "\n".join(p["text"] for p in paras)
    missing = []
    for mn in minors:
        pat = re.compile(r"(?<![\d.])%d\s*[.．]\s*%d(?![\d])" % (major, mn))
        if not pat.search(blob):
            missing.append("%d.%d" % (major, mn))
    return missing


def _marks_in(paras):
    """收集这些段落里出现的 a)–j) 标记。"""
    got = set()
    for p in paras:
        for m in _MARK.finditer(p["text"]):
            got.add(m.group(1))
    return got


def _finding(fid, level, title, detail, location, fix):
    return {"id": fid, "level": level, "title": title,
            "detail": detail, "location": location, "fix": fix}


def run(doc):
    out = []
    found = find_chapters(doc)

    # ---- S-01 八章齐不齐 ----
    for num, name in CHAPTERS:
        if num in found:
            continue
        out.append(_finding(
            "S-01", "critical", "缺少一级章节",
            "缺第 %d 章『%s』" % (num, name),
            "文档结构",
            "补写第 %d 章；确实不涉及的部分，在附录里说明理由" % num,
        ))

    # ---- S-02 第 2 章 2.1–2.5 ----
    span2 = _span(doc.paragraphs, found, 2)
    if span2:
        miss = _subs_missing(_within(doc, span2), 2, [1, 2, 3, 4, 5])
        if miss:
            out.append(_finding(
                "S-02", "warn", "第 2 章子节不全",
                "第 2 章缺子节编号：%s" % "、".join(miss),
                "第 2 章",
                "补齐 2.1–2.5 五个子节（系统概述该交代的五个方面）",
            ))

    # ---- S-03 第 3 章 3.1–3.3 ----
    span3 = _span(doc.paragraphs, found, 3)
    if span3:
        miss = _subs_missing(_within(doc, span3), 3, [1, 2, 3])
        if miss:
            out.append(_finding(
                "S-03", "warn", "第 3 章子节不全",
                "第 3 章缺子节编号：%s" % "、".join(miss),
                "第 3 章",
                "补齐 3.1–3.3 三个子节（需求分析该交代的三个方面）",
            ))

    # ---- S-04 第 5 章 5.1–5.5 ----
    span5 = _span(doc.paragraphs, found, 5)
    if span5:
        miss = _subs_missing(_within(doc, span5), 5, [1, 2, 3, 4, 5])
        if miss:
            out.append(_finding(
                "S-04", "warn", "第 5 章子节不全",
                "第 5 章缺子节编号：%s" % "、".join(miss),
                "第 5 章",
                "补齐 5.1–5.5 五个子节（设计层面该交代的五个部分）",
            ))

        # ---- S-05 / S-06 都在 5.3 里找 ----
        p53 = [p for p in _within(doc, span5)
               if re.search(r"(?<![\d.])5\s*[.．]\s*3(?![\d])", p["text"])]
        if p53:
            start = p53[0]["index"]
            later = [p["index"] for p in _within(doc, span5)
                     if p["index"] > start
                     and re.match(r"^\s*5\s*[.．]\s*[45]\b", p["text"])]
            end = min(later) if later else span5[1]
            seg = [p for p in doc.paragraphs if start <= p["index"] < end]

            # S-05：a)–i) 九要素
            got = _marks_in(seg)
            miss = [c for c in "abcdefghi" if c not in got]
            if miss:
                out.append(_finding(
                    "S-05", "warn", "5.3 九要素不全",
                    "第 5.3 节缺要素标记：%s" % "、".join(c + ")" for c in miss),
                    "第 5.3 节",
                    "按 a)–i) 九个要素逐个补齐设计说明",
                ))

            # S-06：密钥管理十环节（标记 + 固定名称都要对）
            km_at = None
            for p in seg:
                if "密钥管理" in p["text"]:
                    km_at = p["index"]
                    break
            if km_at is None:
                out.append(_finding(
                    "S-06", "critical", "缺密钥管理设计",
                    "第 5.3 节里找不到「密钥管理」",
                    "第 5.3 节",
                    "补一节密钥管理，按生成到销毁十个环节逐个写",
                ))
            else:
                km_seg = [p for p in seg if p["index"] >= km_at]
                got = _marks_in(km_seg)
                miss_mark = [c for c in "abcdefghij" if c not in got]
                km_text = "\n".join(p["text"] for p in km_seg)
                miss_name = [s for s in KEY_STAGES if s not in km_text]
                if miss_mark or miss_name:
                    bits = []
                    if miss_mark:
                        bits.append("缺环节标记 %s" % "、".join(c + ")" for c in miss_mark))
                    if miss_name:
                        bits.append("缺环节内容：%s" % "、".join(miss_name))
                    out.append(_finding(
                        "S-06", "warn", "密钥管理环节不全",
                        "第 5.3 节密钥管理" + "；".join(bits),
                        "第 5.3 节密钥管理",
                        "十个环节逐个补齐：生成、存储、分发、使用、更新、"
                        "归档、撤销、备份、恢复、销毁",
                    ))
    return out
