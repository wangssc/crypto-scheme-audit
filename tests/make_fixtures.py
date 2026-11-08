#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成测试用的 .docx。

五个文件共用一套构建逻辑，靠参数开关控制差异——这样"只改了一个变量"
这件事在代码里是看得见的，不会出现 good 和 missing-ch5 因为别的原因不同
而把测试结论带偏。

    python tests/make_fixtures.py          # 生成到 tests/fixtures/
"""

import os
import sys

from docx import Document

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "fixtures")

CHAPTERS = ["背景", "系统概述", "需求分析", "目标与原则",
            "密码应用设计", "安全管理", "合规性分析", "实施保障"]

# SPEC 4.2 技术 22 项
TECH = [
    ("8.1 a", "宜"), ("8.1 b", "宜"), ("8.1 c", "宜"),
    ("8.2 a", "应"), ("8.2 b", "宜"), ("8.2 c", "应"), ("8.2 d", "宜"), ("8.2 e", "可"),
    ("8.3 a", "应"), ("8.3 b", "应"), ("8.3 c", "宜"), ("8.3 d", "宜"),
    ("8.3 e", "宜"), ("8.3 f", "宜"),
    ("8.4 a", "应"), ("8.4 b", "宜"), ("8.4 c", "宜"), ("8.4 d", "应"),
    ("8.4 e", "应"), ("8.4 f", "宜"), ("8.4 g", "宜"), ("8.4 h", "宜"),
]

# 管理 19 项：GB/T 39786-2021 第三级原文的 8.5 ~ 8.8。
# 注意编号是 8.5~8.8，不是第 9 章的 9.1~9.8（9.x 是第四级的要求）。
# 这 19 条全部是「应」——标准原文如此，管理要求不留选择余地。
MGMT = (
    [("8.5 %s" % c, "应") for c in "abcdef"] +    # 6  管理制度
    [("8.6 %s" % c, "应") for c in "abcde"] +     # 5  人员管理
    [("8.7 %s" % c, "应") for c in "abcde"] +     # 5  建设运行
    [("8.8 %s" % c, "应") for c in "abc"]         # 3  应急处置
)  # 合计 19

SELF_ASSESS = "设计满足"


def _h(doc, text, level):
    doc.add_heading(text, level=level)


def _p(doc, text):
    doc.add_paragraph(text)


def build(path, drop_ch5=False, wrong_level=False, add_compliant=False,
          drop_mgmt=False, wrong_mgmt_level=False, vague_na=False):
    doc = Document()

    # ---- 1 背景 ----
    _h(doc, "1 背景", 1)
    _p(doc, "本方案针对某信息系统的密码应用需求编制，说明系统边界、"
            "需保护的对象以及拟采用的密码技术路线。")

    # ---- 2 系统概述 ----
    _h(doc, "2 系统概述", 1)
    for i, name in enumerate(["系统定位", "业务功能", "用户范围", "网络架构", "数据情况"], 1):
        _h(doc, "2.%d %s" % (i, name), 2)
        _p(doc, "本节说明%s相关情况。" % name)

    # ---- 3 需求分析 ----
    _h(doc, "3 需求分析", 1)
    for i, name in enumerate(["需保护对象", "合规要求", "风险分析"], 1):
        _h(doc, "3.%d %s" % (i, name), 2)
        _p(doc, "本节说明%s的结论。" % name)

    # ---- 4 目标与原则 ----
    _h(doc, "4 目标与原则", 1)
    _h(doc, "4.1 设计目标", 2)
    _p(doc, "设计目标是在不改变现有业务流程的前提下引入国产密码技术。")
    _h(doc, "4.2 设计原则", 2)
    _p(doc, "遵循总体性、可行性和可扩展性原则。")

    # ---- 5 密码应用设计 ----
    if not drop_ch5:
        _h(doc, "5 密码应用设计", 1)

        # 5.1 / 5.2 / 5.3 先写，九要素要落在 5.3 的范围里（到 5.4 之前）
        for i, name in enumerate(["总体设计", "技术架构", "详细设计"], 1):
            _h(doc, "5.%d %s" % (i, name), 2)
            _p(doc, "本节说明%s的安排。" % name)

        # 5.3 下的九要素 a) – i)，其中 f) 是密钥管理
        _p(doc, "详细设计按下列九个要素展开：")
        elements = [
            "物理和环境安全设计", "网络和通信安全设计", "设备和计算安全设计",
            "应用和数据安全设计", "密码服务接口设计", "密钥管理设计",
            "密码产品选型", "密码技术应用方式", "安全管理措施设计",
        ]
        for letter, name in zip("abcdefghi", elements):
            _p(doc, "%s) %s" % (letter, name))

        # 密钥管理的十个环节，同样必须在 5.3 范围内
        _p(doc, "密钥管理覆盖以下十个环节：")
        stages = ["生成", "存储", "分发", "使用", "更新",
                  "归档", "撤销", "备份", "恢复", "销毁"]
        for letter, name in zip("abcdefghij", stages):
            _p(doc, "%s) 密钥%s环节的要求与责任划分。" % (letter, name))

        for i, name in enumerate(["部署架构", "运行维护"], 4):
            _h(doc, "5.%d %s" % (i, name), 2)
            _p(doc, "本节说明%s的安排。" % name)

    # ---- 6 安全管理 ----
    _h(doc, "6 安全管理", 1)
    _p(doc, "安全管理覆盖制度、人员、建设运行与应急处置四个方面。")

    # ---- 7 合规性分析 ----
    _h(doc, "7 合规性分析", 1)
    _h(doc, "7.1 指标对照表", 2)

    rows = TECH + MGMT
    if wrong_level:
        rows = [("8.2 b", "应") if c == "8.2 b" else (c, l) for c, l in rows]
    if drop_mgmt:
        # 删掉 8.8 三条，模拟「管理部分没写完」
        rows = [(c, l) for c, l in rows if not c.startswith("8.8 ")]
    if wrong_mgmt_level:
        # 8.5 d 写成「宜」，模拟「管理要求被降级」
        rows = [("8.5 d", "宜") if c == "8.5 d" else (c, l) for c, l in rows]

    table = doc.add_table(rows=len(rows) + 1, cols=3)
    table.style = "Table Grid"
    header = table.rows[0].cells
    header[0].text = "条款"
    header[1].text = "级别"
    header[2].text = "自评结论"
    # 三条「宜」直接标不适用、不给理由——模拟「不想写就说一句不涉及」。
    # 这正是 C-07 存在的理由：不给理由的「不适用」不会让这一条跳过测评，
    # 反而把它从「可以不测」拉成「必须测」。表里也没有「说明」列可写理由。
    vague = {"8.1 a", "8.1 b", "8.2 d"} if vague_na else set()
    for i, (clause, level) in enumerate(rows, 1):
        cells = table.rows[i].cells
        # 条款号写成 8.2 b) 形式
        num, _, letter = clause.partition(" ")
        cells[0].text = "%s %s)" % (num, letter) if letter else num
        cells[1].text = level
        cells[2].text = "不适用" if clause in vague else SELF_ASSESS

    if add_compliant:
        _h(doc, "7.2 自评说明", 2)
        _p(doc, "本系统各项密码应用指标均符合第三级要求，可以直接投入使用。")

    # ---- 8 实施保障 ----
    _h(doc, "8 实施保障", 1)
    _p(doc, "实施保障包括组织保障、进度安排与经费预算。")

    doc.save(path)


def build_not_a_scheme(path):
    """一份跟密码应用方案无关的文档，用来验证 not assessed 分支。"""
    doc = Document()
    _h(doc, "会议纪要", 1)
    _p(doc, "本次会议讨论了办公区域的搬迁安排，与会人员就时间节点达成一致。")
    _p(doc, "下周一开始打包，月底前完成搬迁。")
    _h(doc, "待办事项", 1)
    _p(doc, "联系搬家公司；清点资产；通知各部门。")
    doc.save(path)


def main():
    os.makedirs(OUT, exist_ok=True)
    jobs = [
        ("good.docx", {}),
        ("missing-ch5.docx", {"drop_ch5": True}),
        ("wrong-level.docx", {"wrong_level": True}),
        ("wording.docx", {"add_compliant": True}),
        ("missing-mgmt.docx", {"drop_mgmt": True}),
        ("wrong-mgmt-level.docx", {"wrong_mgmt_level": True}),
        ("vague-na.docx", {"vague_na": True}),
    ]
    for name, kw in jobs:
        path = os.path.join(OUT, name)
        build(path, **kw)
        print("生成 %-20s %6d 字节" % (name, os.path.getsize(path)))

    path = os.path.join(OUT, "not-a-scheme.docx")
    build_not_a_scheme(path)
    print("生成 %-20s %6d 字节" % ("not-a-scheme.docx", os.path.getsize(path)))


if __name__ == "__main__":
    sys.exit(main())
