# -*- coding: utf-8 -*-
"""检查器与入口的测试。

分两层：
- 单元层：用假 doc 直接喂检查器，快、能精确控制边界
- 集成层：跑真实的 .docx fixture，连 audit.py 的退出码一起验

验收标准第 8 条（报告里不能出现方案原文）单独一个用例，因为它是最容易
随着改动悄悄失效的一条。
"""

import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import audit                                    # noqa: E402
import core                                     # noqa: E402
from checks import coverage, format as fmt, structure, wording   # noqa: E402

FIXTURES = os.path.join(ROOT, "tests", "fixtures")


# --------------------------------------------------------------- 假 doc
class FakeDoc:
    """按 core.SchemeDoc 的形状造一个，不碰磁盘。"""

    def __init__(self, paragraphs=(), tables=(), headings=None, filename="t.docx"):
        self.paragraphs = []
        for i, text in enumerate(paragraphs):
            self.paragraphs.append({"text": text, "style": "", "index": i})
        if headings is None:
            headings = []
        self.headings = list(headings)
        self.tables = [list(t) for t in tables]
        self.filename = filename
        self.docx_bytes = 0

    @property
    def full_text(self):
        return "\n".join(p["text"] for p in self.paragraphs)


def _doc(paras, tables=(), headings=()):
    return FakeDoc(paras, tables, headings)


def _ids(findings):
    return [f["id"] for f in findings]


# ----------------------------------------------------- structure 单元
def test_heading_variants_recognised():
    """三种标题写法都要认：一、/ 1. / 第一章。"""
    for title in ("一、背景", "1. 背景", "第一章 背景", "1 背景", "第1章 背景"):
        doc = _doc([title])
        found = structure.find_chapters(doc)
        assert 1 in found, "没识别出：%s" % title


def test_body_text_not_mistaken_for_chapter():
    """正文里出现「背景」两个字，不算有第 1 章。"""
    doc = _doc(["这个项目背景比较复杂，涉及多个部门的历史系统改造工作。"])
    assert structure.find_chapters(doc) == {}


def test_missing_chapter_reported_with_number():
    doc = _doc(["1 背景", "2 系统概述", "3 需求分析", "4 目标与原则",
                "6 安全管理", "7 合规性分析", "8 实施保障"])
    got = structure.run(doc)
    titles = [f["detail"] for f in got if f["id"] == "S-01"]
    assert any("第 5 章" in t for t in titles), titles


def test_key_management_requires_ten_stages():
    """密钥管理只有 5 个环节时要报缺。"""
    doc = _doc([
        "5 密码应用设计",
        "5.3 详细设计",
        "a) 甲", "b) 乙", "c) 丙", "d) 丁", "e) 戊",
        "f) 己", "g) 庚", "h) 辛", "i) 壬",
        "密钥管理",
        "a) 密钥生成", "b) 密钥存储", "c) 密钥分发", "d) 密钥使用", "e) 密钥更新",
        "6 安全管理",
    ])
    got = structure.run(doc)
    km = [f for f in got if f["id"] == "S-06"]
    assert km, "缺环节没报"
    assert "归档" in km[0]["detail"] or "销毁" in km[0]["detail"]


# ------------------------------------------------------- wording 单元
@pytest.mark.parametrize("text", [
    "本系统各项指标符合第三级要求。",
    "该指标符合要求。",
])
def test_wording_flags_plain_compliant(text):
    got = wording.run(_doc([text]))
    assert got and got[0]["id"] == "W-01"


@pytest.mark.parametrize("text", [
    "整改后符合要求。",
    "目前不符合要求，需要补充设备。",
    "未符合相关条款。",
    "本方案符合 GB/T 43207-2023 的编写要求。",
    "详见第七节符合性分析。",
])
def test_wording_excludes_allowed_contexts(text):
    got = wording.run(_doc([text]))
    assert got == [], "不该报但报了：%s → %s" % (text, got)


def test_wording_reports_table_cells():
    doc = _doc(["正文没问题。"], tables=[[["条款", "级别", "自评"],
                                          ["8.1 a)", "宜", "符合"]]])
    got = wording.run(doc)
    assert any(f["id"] == "W-02" for f in got)


# -------------------------------------------------------- format 单元
def test_f03_flags_tight_clause_number():
    got = fmt.run(_doc(["对应条款 8.2b 的要求。"]))
    assert any(f["id"] == "F-03" and "缺分隔" in f["title"] for f in got)


def test_f03_flags_dash_clause_number():
    got = fmt.run(_doc(["对应条款 8.2-b 的要求。"]))
    assert any(f["id"] == "F-03" and "连字符" in f["title"] for f in got)


def test_f03_accepts_proper_form():
    got = fmt.run(_doc(["对应条款 8.2 b) 的要求。"]))
    assert not any(f["id"] == "F-03" for f in got)


@pytest.mark.parametrize("text,label", [
    ("这里待补充具体型号。", "待补充"),
    ("填写单位名称 TODO", "TODO"),
    ("联系人 XXX", "XXX"),
    ("地址【】", "空方括号"),
])
def test_f04_placeholders(text, label):
    got = fmt.run(_doc([text]))
    f4 = [f for f in got if f["id"] == "F-04"]
    assert f4 and label in f4[0]["detail"]


def test_f01_ragged_table():
    doc = _doc(["表格"], tables=[[["a", "b", "c"], ["d", "e"]]])
    got = fmt.run(doc)
    assert any(f["id"] == "F-01" for f in got)


def test_f02_hand_typed_headings():
    """有章节名但没有标题样式 → 报手打标题。"""
    doc = _doc(["1 背景", "2 系统概述", "3 需求分析"])
    got = fmt.run(doc)
    assert any(f["id"] == "F-02" for f in got)


# ------------------------------------------------------ coverage 单元
def test_coverage_without_table_is_critical():
    got = coverage.run(_doc(["没有任何表格。"]))
    assert got[0]["id"] == "C-01"
    assert got[0]["level"] == "critical"


def _make_table(rows):
    body = [["条款", "级别", "自评"]]
    body += [["%s %s)" % (c.split(" ")[0], c.split(" ")[1]), lv, "设计满足"]
             for c, lv in rows]
    return [body]


def test_coverage_row_count_checked():
    rows = coverage.TECH_INDICATORS[:5]
    got = coverage.run(_doc(["x"], tables=_make_table(rows)))
    assert any(f["id"] == "C-02" for f in got)


def test_coverage_missing_indicator_reported():
    rows = [r for r in coverage.TECH_INDICATORS if r[0] != "8.4 c"]
    got = coverage.run(_doc(["x"], tables=_make_table(rows)))
    c3 = [f for f in got if f["id"] == "C-03"]
    assert c3 and "8.4 c" in c3[0]["detail"]


def test_coverage_level_mismatch_reported():
    rows = [("8.2 b", "应") if c == "8.2 b" else (c, l) for c, l in coverage.TECH_INDICATORS]
    got = coverage.run(_doc(["x"], tables=_make_table(rows)))
    c4 = [f for f in got if f["id"] == "C-04"]
    assert c4 and "8.2 b" in c4[0]["detail"]


def test_coverage_mgmt_missing_reported():
    """管理 19 项少一条就要报——这部分以前是空白，现在有真数据了。"""
    rows = [(c, l) for c, l in coverage.TECH_INDICATORS + coverage.MGMT_INDICATORS
            if c != "8.8 c"]
    got = coverage.run(_doc(["x"], tables=_make_table(rows)))
    c5 = [f for f in got if f["id"] == "C-05"]
    assert c5 and "8.8 c" in c5[0]["detail"]


def test_coverage_mgmt_level_mismatch_reported():
    """管理 19 项全部是「应」，写「宜」就是与原文不符。"""
    base = coverage.TECH_INDICATORS + coverage.MGMT_INDICATORS
    rows = [("8.5 d", "宜") if c == "8.5 d" else (c, l) for c, l in base]
    got = coverage.run(_doc(["x"], tables=_make_table(rows)))
    c6 = [f for f in got if f["id"] == "C-06"]
    assert c6 and "8.5 d" in c6[0]["detail"]


def test_mgmt_indicator_count_is_19():
    """22 + 19 = 41，这个数是整张表的骨架，写错了下面全错。"""
    assert len(coverage.TECH_INDICATORS) == 22
    assert len(coverage.MGMT_INDICATORS) == 19
    assert len(coverage.TECH_INDICATORS) + len(coverage.MGMT_INDICATORS) == coverage.TOTAL_ROWS


def test_mgmt_indicators_all_required():
    """第三级的管理要求没有「宜」也没有「可」，18 条以上写错就说明抄错了章。"""
    assert all(lv == "应" for _, lv in coverage.MGMT_INDICATORS)
    sections = {c.split()[0] for c, _ in coverage.MGMT_INDICATORS}
    assert sections == {"8.5", "8.6", "8.7", "8.8"}, sections


# ------------------------------------------------------------ 集成层
def _run(path, *extra):
    return audit.main([path] + list(extra))


def test_good_fixture_scores_high(capsys):
    code = _run(os.path.join(FIXTURES, "good.docx"))
    out = capsys.readouterr().out
    assert code == 0
    m = re.search(r"评分 (\d+)/100", out)
    assert m and int(m.group(1)) >= 80, out


def test_missing_ch5_fixture(capsys):
    code = _run(os.path.join(FIXTURES, "missing-ch5.docx"), "--fail-on", "critical")
    out = capsys.readouterr().out
    assert code == 1
    assert "第 5 章" in out


def test_wrong_level_fixture(capsys):
    _run(os.path.join(FIXTURES, "wrong-level.docx"))
    out = capsys.readouterr().out
    assert "级别" in out and "8.2 b" in out


def test_wording_fixture(capsys):
    code = _run(os.path.join(FIXTURES, "wording.docx"), "--fail-on", "critical")
    out = capsys.readouterr().out
    assert code == 1
    assert "越位" in out


def test_missing_mgmt_fixture(capsys):
    code = _run(os.path.join(FIXTURES, "missing-mgmt.docx"), "--fail-on", "critical")
    out = capsys.readouterr().out
    assert code == 1
    assert "管理指标" in out


def test_wrong_mgmt_level_fixture(capsys):
    code = _run(os.path.join(FIXTURES, "wrong-mgmt-level.docx"), "--fail-on", "critical")
    out = capsys.readouterr().out
    assert code == 1
    assert "8.5 d" in out


def test_not_a_scheme_fixture(capsys):
    code = _run(os.path.join(FIXTURES, "not-a-scheme.docx"))
    out = capsys.readouterr().out
    assert code == 0
    assert "未评估" in out
    assert "0/100" not in out


def test_missing_file_exit_2(capsys):
    code = _run(os.path.join(FIXTURES, "根本没有这个文件.docx"))
    assert code == 2


def test_non_docx_exit_2(tmp_path, capsys):
    p = tmp_path / "a.txt"
    p.write_text("x", encoding="utf-8")
    assert _run(str(p)) == 2


# ---------------------------------------------- 报告不泄漏原文（第 8 条）
LEAK_MARKERS = [
    "本方案针对某信息系统的密码应用需求编制",
    "会议讨论了办公区域的搬迁安排",
    "本节说明系统定位相关情况",
    "密钥生成环节的要求与责任划分",
]


@pytest.mark.parametrize("name", ["good.docx", "missing-ch5.docx",
                                  "wrong-level.docx", "wording.docx",
                                  "not-a-scheme.docx"])
def test_report_contains_no_source_snippet(name, capsys):
    """验收第 8 条：报告里搜不到 fixture 的原文片段。"""
    _run(os.path.join(FIXTURES, name), "--markdown")
    out = capsys.readouterr().out
    for m in LEAK_MARKERS:
        assert m not in out, "报告里出现了原文：%s" % m


def test_json_output_also_clean(capsys):
    import json
    _run(os.path.join(FIXTURES, "good.docx"), "--json")
    out = capsys.readouterr().out
    payload = json.loads(out)
    blob = json.dumps(payload, ensure_ascii=False)
    for m in LEAK_MARKERS:
        assert m not in blob
