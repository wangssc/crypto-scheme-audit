#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""crypto-scheme-audit 入口。

用法：
    python audit.py <方案.docx>
    python audit.py <方案.docx> --json
    python audit.py <方案.docx> --markdown -o report.md
    python audit.py <方案.docx> --fail-on critical

退出码：0 无 critical / 1 有 critical / 2 输入不可读
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import core  # noqa: E402

# checks 下每个模块都要有 run(doc)。缺文件不算错误——开发过程中会缺。
CHECK_MODULES = ["structure", "coverage", "wording", "format"]

CHAPTERS = ["背景", "系统概述", "需求分析", "目标与原则",
            "密码应用设计", "安全管理", "合规性分析", "实施保障"]


def load_checks():
    """导入存在的检查模块。缺模块只提示不中断。"""
    mods = []
    missing = []
    for name in CHECK_MODULES:
        try:
            mod = __import__("checks." + name, fromlist=["run"])
        except ImportError:
            missing.append(name)
            continue
        if not hasattr(mod, "run"):
            missing.append(name)
            continue
        mods.append((name, mod))
    return mods, missing


def assess(doc):
    """判断这份文档到底是不是一份方案。

    判据用「八章命中数 ≥ 5」而不是 8，因为有的方案章节标题写法不同
    （"一、背景" / "1. 项目背景"），硬性要求 8 个会误杀。
    """
    text = doc.full_text
    hit = sum(1 for c in CHAPTERS if c in text)
    return hit >= 5, hit


def run_checks(doc, mods):
    findings = []
    for name, mod in mods:
        try:
            got = mod.run(doc) or []
        except Exception as e:  # 单个检查器崩了不能拖垮整份报告
            findings.append({
                "id": name.upper(),
                "level": "warn",
                "title": "检查器异常",
                "detail": "%s 模块抛出 %s: %s" % (name, type(e).__name__, e),
                "location": "工具自身",
                "fix": "这是工具的 bug，请把这条报给维护者",
            })
            continue
        for f in got:
            f.setdefault("level", "warn")
            findings.append(f)

    order = {"critical": 0, "warn": 1, "hint": 2}
    findings.sort(key=lambda f: (order.get(f.get("level"), 9), f.get("id", "")))
    return findings


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="audit.py",
        description="检查《信息系统密码应用方案》的结构完整性与指标覆盖")
    ap.add_argument("target", help="方案 .docx 文件")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--markdown", action="store_true", help="输出 Markdown")
    ap.add_argument("-o", "--out", help="写文件（不给就打到 stdout）")
    ap.add_argument("--fail-on", choices=["critical", "warn", "none"],
                    default="none", help="CI 用：命中哪一级就返回 1")
    args = ap.parse_args(argv)

    if not os.path.exists(args.target):
        _err("文件不存在：%s" % args.target)
        return 2
    if not args.target.lower().endswith(".docx"):
        _err("只支持 .docx。扫描件 PDF 和 .doc 请先转成 .docx。")
        return 2
    if core.docx is None:
        _err("缺少 python-docx。运行：pip install python-docx")
        return 2

    try:
        doc = core.SchemeDoc(args.target)
    except Exception as e:
        _err("读不了这个文件（可能加密或损坏）：%s: %s" % (type(e).__name__, e))
        return 2

    mods, missing = load_checks()
    assessed, chapter_hits = assess(doc)

    if not assessed:
        sc = dict(core.NOT_ASSESSED)
        findings = []
        if missing:
            findings.append({
                "id": "TOOL", "level": "hint",
                "title": "部分检查器尚未就位",
                "detail": "缺 " + ", ".join(missing),
                "location": "工具自身",
                "fix": "补齐 checks/%s.py" % missing[0],
            })
        payload = {
            "ok": True, "target": doc.filename, "assessed": False,
            "reason": "只命中 %d/8 个一级章节，判断不是方案文档" % chapter_hits,
            "score": sc, "findings": findings,
            "stats": {"paragraphs": len(doc.paragraphs),
                      "tables": len(doc.tables),
                      "headings": len(doc.headings)},
        }
    else:
        findings = run_checks(doc, mods)
        sc = core.score(findings)
        payload = {
            "ok": True, "target": doc.filename, "assessed": True,
            "score": sc, "findings": findings,
            "stats": {"paragraphs": len(doc.paragraphs),
                      "tables": len(doc.tables),
                      "headings": len(doc.headings)},
        }
        if missing:
            payload["missing_checks"] = missing

    if args.json:
        text = json.dumps(payload, ensure_ascii=False, indent=2)
    elif args.markdown:
        text = core.render_markdown(doc, findings, sc, assessed)
    else:
        text = core.render_text(doc, findings, sc, assessed)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print("已写入 %s" % args.out)
    else:
        print(text)

    if args.fail_on == "none":
        return 0
    severities = {f.get("level") for f in findings}
    if args.fail_on == "warn":
        return 1 if severities & {"critical", "warn"} else 0
    return 1 if "critical" in severities else 0


def _err(msg):
    print("[错误] " + msg, file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
