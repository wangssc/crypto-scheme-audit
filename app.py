#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""双击入口：选一个方案 .docx，出一份 HTML 报告，用浏览器打开。

命令行也能用：
    python app.py <方案.docx>
    python app.py <方案.docx> --no-open

为什么不用纯 CLI：双击 exe 时没有终端，报错一闪而过。
这里所有失败都弹窗，不会静默退出。
"""

import os
import sys
import traceback
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import core        # noqa: E402
import audit       # noqa: E402


APP_TITLE = "密码应用方案自检"
APP_VERSION = "1.0"

# 双击时 exe 可能被放在 Program Files 之类不可写的地方，输出目录要能退化。
def _out_dir():
    here = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False)
                                           else __file__))
    for cand in (os.path.join(here, "自检报告"),
                 os.path.join(os.environ.get("LOCALAPPDATA")
                              or os.path.expanduser("~"), "CryptoSchemeAudit", "报告")):
        try:
            os.makedirs(cand, exist_ok=True)
            probe = os.path.join(cand, ".probe")
            with open(probe, "w", encoding="utf-8") as f:
                f.write("ok")
            os.remove(probe)
            return cand
        except Exception:
            continue
    return os.environ.get("TEMP") or "."


def _safe_name(path):
    base = os.path.splitext(os.path.basename(path))[0]
    keep = "".join(c for c in base if c not in '\\/:*?"<>|').strip()
    return (keep or "方案")[:60]


def check_file(path):
    """跑一遍检查，返回 (html, 输出路径, 提示语)。"""
    if core.docx is None:
        raise RuntimeError("缺少 python-docx，这个包打得不对")
    doc = core.SchemeDoc(path)
    mods, missing = audit.load_checks()
    assessed, hits = audit.assess(doc)

    if not assessed:
        sc = dict(core.NOT_ASSESSED)
        findings = []
        msg = ("没找到方案的八章结构（只命中 %d/8）。\n"
               "这不等于通过——请确认文件对不对，或者把章节标题套上「标题 1」。" % hits)
    else:
        findings = audit.run_checks(doc, mods)
        sc = core.score(findings)
        if sc["counts"]["critical"]:
            msg = "必须修 %d 项，先改这些。" % sc["counts"]["critical"]
        elif sc["counts"]["warn"]:
            msg = "没有必须修项，但建议改 %d 项。" % sc["counts"]["warn"]
        else:
            msg = "没发现问题。但这只是结构和覆盖检查，不等于能过评审。"
        if missing:
            msg += "\n（提示：%d 个检查器未就位）" % len(missing)

    html = core.render_html(doc, findings, sc, assessed)
    out = os.path.join(_out_dir(), "%s_自检.html" % _safe_name(path))
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    return html, out, msg


def _pick():
    import tkinter as tk
    from tkinter import filedialog, messagebox
    root = tk.Tk()
    root.withdraw()
    path = filedialog.askopenfilename(
        title="选一个密码应用方案（Word 文档）",
        filetypes=[("Word 文档", "*.docx"), ("所有文件", "*.*")])
    if not path:
        root.destroy()
        return None, root
    return path, root


def _fail(msg, root=None):
    try:
        from tkinter import messagebox
        messagebox.showerror(APP_TITLE, msg)
    except Exception:
        print(msg, file=sys.stderr)
    if root is not None:
        try:
            root.destroy()
        except Exception:
            pass


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    no_open = "--no-open" in argv
    argv = [a for a in argv if a != "--no-open"]

    root = None
    if argv:
        path = argv[0]
    else:
        path, root = _pick()
        if not path:
            return 0

    if not os.path.exists(path):
        _fail("找不到这个文件：\n%s" % path, root)
        return 2
    if not path.lower().endswith(".docx"):
        _fail("只支持 .docx。\nWord 97-2003 的 .doc 和扫描件 PDF 请先另存为 .docx。", root)
        return 2

    try:
        _, out, msg = check_file(path)
    except Exception:
        _fail("检查过程中出错了。\n\n%s" % traceback.format_exc()[-1200:], root)
        return 3

    if not no_open:
        try:
            webbrowser.open("file:///" + out.replace("\\", "/"))
        except Exception:
            pass

    if no_open:
        # --no-open 是给脚本用的：不弹窗、只打印，否则自动化测试会被 showinfo 卡住等点击。
        print(msg + "\n" + out)
    else:
        try:
            from tkinter import messagebox
            r = tk.Tk()
            r.withdraw()
            messagebox.showinfo(APP_TITLE + "  " + APP_VERSION,
                                msg + "\n\n报告已保存到：\n" + out)
            r.destroy()
        except Exception:
            print(msg + "\n" + out)

    if root is not None:
        try:
            root.destroy()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
