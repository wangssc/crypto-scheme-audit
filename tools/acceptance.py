#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对打包后的 exe 做黑盒验收。

为什么要有这个：改完界面、改完 server，源码版都好好的，打成 exe 之后
路径、stdout、动态导入都可能坏掉，而且窗口化程序坏了不报错。
这个脚本只认 exe 本身，跟源码无关。

用法：
    python tools/acceptance.py dist/密码应用方案自检.exe
"""

import base64
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(ROOT, "tests", "fixtures")
PORT = 8788
DETACHED_PROCESS = 0x00000008

ROWS = []


def item(no, name, ok, evidence):
    ROWS.append({"no": no, "name": name,
                 "result": "PASS" if ok else "FAIL", "evidence": evidence})


def free_port(port):
    s = socket.socket()
    s.settimeout(0.1)
    try:
        return s.connect_ex(("127.0.0.1", port)) != 0
    finally:
        s.close()


def get(path, timeout=20):
    with urllib.request.urlopen("http://127.0.0.1:%d%s" % (PORT, path),
                                timeout=timeout) as r:
        return r.read().decode("utf-8")


def post(path, payload, timeout=90):
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (PORT, path),
                                 data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


def audit(fixture):
    raw = open(os.path.join(FIXTURES, fixture), "rb").read()
    st, d = post("/api/audit", {"name": fixture,
                                "data": base64.b64encode(raw).decode()})
    return d


def launch(exe):
    env = dict(os.environ, CRYPTOAUDIT_NO_BROWSER="1")
    return subprocess.Popen([exe], env=env, stdout=None, stderr=None,
                            creationflags=DETACHED_PROCESS)


def wait_up(seconds=25):
    for _ in range(seconds * 10):
        try:
            get("/api/ping", timeout=1.5)
            return True
        except Exception:
            time.sleep(0.1)
    return False


def main():
    exe = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        ROOT, "dist", "密码应用方案自检.exe")
    exe = os.path.abspath(exe)
    if not os.path.isfile(exe):
        print("找不到 exe：%s" % exe)
        return 2

    proc = None
    try:
        if not free_port(PORT):
            print("端口 %d 已被占用，先关掉正在运行的实例再跑。" % PORT)
            return 2

        proc = launch(exe)
        up = wait_up()
        item(1, "双击启动，服务在 127.0.0.1:%d 就绪" % PORT, up,
             "ping %s" % ("通" if up else "25 秒内没起来"))
        if not up:
            raise SystemExit(_report())

        html = get("/")
        ok = "把方案 .docx 拖到这里" in html and "点这里选" in html
        item(2, "界面文件已打进 exe", ok,
             "GET / 返回 %d 字符，拖拽区%s" % (len(html), "在" if ok else "缺失"))

        d = audit("good.docx")
        ok = d["assessed"] and d["score"] == 100 and d["grade"] == "A"
        item(3, "good.docx → 100 分 A", ok,
             "score=%s grade=%s critical=%s" % (d["score"], d["grade"],
                                                d["counts"]["critical"]))

        d = audit("missing-mgmt.docx")
        ok = (d["assessed"] and d["score"] == 64 and d["grade"] == "D"
              and d["counts"]["critical"] == 2)
        item(4, "missing-mgmt.docx → 64 分 D，必须修 2 项", ok,
             "score=%s grade=%s critical=%s ids=%s"
             % (d["score"], d["grade"], d["counts"]["critical"],
                [f["id"] for f in d["findings"] if f["level"] == "critical"]))

        d = audit("not-a-scheme.docx")
        ok = (d["assessed"] is False and d["score"] is None
              and d["grade"] == "?")
        item(5, "随便一个 Word → 未评估，不显示 0 分", ok,
             "assessed=%s score=%r grade=%s"
             % (d["assessed"], d["score"], d["grade"]))

        # 报告落盘
        d = audit("missing-mgmt.docx")
        out = os.path.join(d["dir"], d["report_file"])
        ok = os.path.isfile(out)
        item(6, "报告落盘到「自检报告」目录", ok, out)

        # 另存的 HTML 必须自包含
        html = d["report_html"]
        ok = ("http://" not in html and "https://" not in html
              and "<link" not in html and "<script" not in html)
        item(7, "报告 HTML 自包含（断网可看）", ok,
             "%d 字符，外链 0，无 link/script" % len(html))

        # 二次启动要认领已有实例
        before = json.loads(get("/api/ping"))["pid"]
        p2 = subprocess.Popen([exe], env=dict(os.environ, CRYPTOAUDIT_NO_BROWSER="1"),
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            code = p2.wait(timeout=15)
        except subprocess.TimeoutExpired:
            p2.kill()
            code = None
        time.sleep(0.5)
        after = json.loads(get("/api/ping"))["pid"]
        item(8, "已有实例时二次启动不报错、不复用端口", code == 0 and after == before,
             "退出码=%s 服务 pid %d→%d" % (code, before, after))

        # 退出
        post("/api/quit", {})
        for _ in range(60):
            time.sleep(0.2)
            if not free_port(PORT):
                continue
            break
        gone = free_port(PORT) and proc.poll() is not None
        item(9, "「退出工具」后进程真的退出", gone,
             "端口 %d %s，主进程 %s"
             % (PORT, "已释放" if free_port(PORT) else "仍被占",
                "已退出" if proc.poll() is not None else "还活着"))
        proc = None

        # 界面不许有外链
        ui = open(os.path.join(ROOT, "ui", "index.html"), encoding="utf-8").read()
        n = ui.count("http://") + ui.count("https://")
        item(10, "ui/index.html 无任何外部地址", n == 0, "命中 %d 处" % n)

        return _report()
    finally:
        if proc is not None and proc.poll() is None:
            try:
                post("/api/quit", {}, timeout=3)
            except Exception:
                proc.kill()


def _report():
    print("")
    print("=" * 78)
    for r in ROWS:
        print("[%s] %-2s %s" % (r["result"], r["no"], r["name"]))
        print("         %s" % r["evidence"])
    bad = [r for r in ROWS if r["result"] == "FAIL"]
    print("=" * 78)
    print("总计 %d/%d PASS" % (len(ROWS) - len(bad), len(ROWS)))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
