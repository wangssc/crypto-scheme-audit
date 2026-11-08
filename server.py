#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地界面服务：起一个只绑 127.0.0.1 的 HTTP 服务，浏览器里拖文件看结果。

为什么要有这一层：双击 exe 弹系统选文件框，用户反馈「用着不方便」。
界面在 ui/index.html，拖进来就出结果，不用选文件。

安全边界（三条，缺一条就出事）：
1. 只 bind 127.0.0.1，不 bind 0.0.0.0 —— 局域网里别的机器连不进来。
2. 每个 POST 都过 _local_ok()，校验 Host 和 Origin —— 挡住 DNS rebinding
   和「你正在看的别的网页偷偷往本机发请求」。
3. 不发任何出站请求，页面不引 CDN/字体/图标。断网就是全功能。

端口 8788：8787 是面试助手的中转，8765 是脱敏工具，别撞。
"""

import base64
import datetime
import json
import os
import socket
import sys
import tempfile
import threading
import time
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote

# windowed exe（console=False）里这两个流是 None，下面每句 print 都会崩成
# AttributeError，而窗口化程序连报错都看不见。先兜住再用。
for _name in ("stdout", "stderr"):
    if getattr(sys, _name, None) is None:
        try:
            setattr(sys, _name, open(os.devnull, "w", encoding="utf-8"))
        except Exception:
            pass

# 控制台按 UTF-8 输出，中文提示不乱码
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ---- 路径解析：源码运行 vs 打包成 exe ----
# 打包后 __file__ 在 PyInstaller 的临时解压目录里，ui/ 在那儿，
# 但报告要写出来给用户看，不能写进 _MEIPASS（进程一退就没了）。
if getattr(sys, "frozen", False):
    BUNDLE = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    HERE = os.path.dirname(os.path.abspath(sys.executable))
else:
    BUNDLE = os.path.dirname(os.path.abspath(__file__))
    HERE = BUNDLE

sys.path.insert(0, BUNDLE)

import audit  # noqa: E402
import core   # noqa: E402


APP_NAME = "crypto-scheme-audit"
APP_VERSION = "1.1"
BASE_PORT = int(os.environ.get("CRYPTOAUDIT_PORT", "8788"))
MAX_BODY = 64 * 1024 * 1024        # docx 撑死几十 MB，超过这个数就是有人在灌数据

UI_PATH = os.path.join(BUNDLE, "ui", "index.html")
LAST = {"dir": None}
SERVER = None
LOCK = threading.Lock()
LAST_PING = {"t": 0.0}
IDLE_EXIT_S = 20 * 60       # 见 _reaper


def _out_root():
    """报告落盘目录。exe 可能被放在 Program Files 这种不可写的地方，要能退化。"""
    for cand in (os.path.join(HERE, "自检报告"),
                 os.path.join(os.environ.get("LOCALAPPDATA")
                              or os.path.expanduser("~"), "CryptoSchemeAudit", "自检报告")):
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


def do_audit(payload):
    """收 base64 docx → 跑检查 → 返回结构化结果 + 自包含报告 HTML。"""
    name = os.path.basename(str(payload.get("name") or "方案.docx"))
    if not name.lower().endswith(".docx"):
        return {"ok": False, "error": "只支持 .docx。Word 97-2003 的 .doc 和扫描件 PDF "
                                      "请先另存为 .docx。"}
    b64 = payload.get("data") or ""
    if not isinstance(b64, str) or not b64:
        return {"ok": False, "error": "没有收到文件内容。"}
    try:
        raw = base64.b64decode(b64, validate=False)
    except Exception:
        return {"ok": False, "error": "文件内容传输不完整，请重新拖一次。"}
    if not raw:
        return {"ok": False, "error": "文件是空的。"}

    if core.docx is None:
        return {"ok": False, "error": "缺少 python-docx，这个包打得不对。"}

    # python-docx 只认路径，所以要落一个临时文件；处理完立刻删。
    # 放系统临时目录，不放 自检报告/ —— 那儿是要给用户拷走的，不能躺原件。
    fd, tmp = tempfile.mkstemp(suffix=".docx", prefix="csa_")
    os.close(fd)
    try:
        with open(tmp, "wb") as f:
            f.write(raw)
        try:
            doc = core.SchemeDoc(tmp)
        except Exception as e:
            return {"ok": False, "error": "读不了这个文件（可能加密或损坏）：%s: %s"
                                          % (type(e).__name__, e)}
        # SchemeDoc 拿的是临时文件名，报告里要显示用户拖进来的那个名字
        doc.filename = name

        mods, missing = audit.load_checks()
        assessed, hits = audit.assess(doc)

        if not assessed:
            sc = dict(core.NOT_ASSESSED)
            findings = []
            reason = ("只命中 %d/8 个一级章节，判断不是方案文档。" % hits)
        else:
            findings = audit.run_checks(doc, mods)
            sc = core.score(findings)
            reason = ""

        html = core.render_html(doc, findings, sc, assessed)

        # 目录名精确到毫秒：只到秒的话，连拖三份文件会挤进同一个文件夹，
        # 用户点「打开报告文件夹」看到一坨，分不清哪份是哪次。
        now = datetime.datetime.now()
        stamp = now.strftime("%m%d_%H%M%S") + ("%03d" % (now.microsecond // 1000))
        outdir = os.path.join(_out_root(), stamp)
        os.makedirs(outdir, exist_ok=True)
        outfile = os.path.join(outdir, "%s_自检.html" % _safe_name(name))
        with open(outfile, "w", encoding="utf-8") as f:
            f.write(html)
        LAST["dir"] = outdir

        return {
            "ok": True,
            "assessed": bool(assessed),
            "reason": reason,
            "score": sc["score"],
            "grade": sc["grade"],
            "label": sc["label"],
            "penalty": sc["penalty"],
            "capped_by_critical": sc["capped_by_critical"],
            "counts": sc["counts"],
            "findings": findings,
            "stats": {"paragraphs": len(doc.paragraphs),
                      "tables": len(doc.tables),
                      "headings": len(doc.headings),
                      "bytes": len(raw)},
            "file": name,
            "dir": outdir,
            "report_file": os.path.basename(outfile),
            "report_html": html,
            "missing_checks": missing,
            "version": APP_VERSION,
        }
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


class Handler(BaseHTTPRequestHandler):
    server_version = "CryptoSchemeAuditUI/" + APP_VERSION

    def log_message(self, fmt, *args):
        pass

    # ---------------------------------------------------------- 工具
    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False))

    def _local_ok(self):
        """Host 必须是回环（rebinding 时 Host 是攻击者域名），Origin 不许是别的站。"""
        host = (self.headers.get("Host") or "").split(":")[0].strip().lower()
        if host not in ("127.0.0.1", "localhost", "::1", "[::1]"):
            return False
        origin = self.headers.get("Origin") or ""
        if not origin:
            return True
        try:
            hostpart = origin.split("//", 1)[1].split("/", 1)[0].split(":")[0].lower()
        except Exception:
            return False
        return hostpart in ("127.0.0.1", "localhost")

    # ---------------------------------------------------------- GET
    def do_GET(self):
        path = unquote(self.path.split("?")[0])
        if path in ("/", "/index.html"):
            try:
                with open(UI_PATH, "rb") as f:
                    self._send(200, f.read(), "text/html; charset=utf-8")
            except Exception as e:
                self._send(500, "界面文件缺失：%s" % e, "text/plain; charset=utf-8")
            return
        if path == "/api/ping":
            LAST_PING["t"] = time.time()
            self._json({"ok": True, "app": APP_NAME, "version": APP_VERSION,
                        "port": PORT, "pid": os.getpid()})
            return
        self._send(404, "not found", "text/plain; charset=utf-8")

    # ---------------------------------------------------------- POST
    def do_POST(self):
        if not self._local_ok():
            self._json({"ok": False, "error": "非本机来源，已拒绝。"}, 403)
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except Exception:
            length = 0
        if length > MAX_BODY:
            self._json({"ok": False, "error": "文件太大（超过 64MB），请确认选对文件。"}, 413)
            return
        path = self.path.split("?")[0]
        try:
            body = self.rfile.read(length) if length else b"{}"
            payload = json.loads(body.decode("utf-8")) if body else {}
        except Exception as e:
            self._json({"ok": False, "error": "请求解析失败：%s" % e}, 400)
            return

        try:
            if path == "/api/audit":
                # 不锁：检查是纯 CPU、只读文档，两个文件同时拖进来各算各的没冲突。
                self._json(do_audit(payload))
            elif path == "/api/ping":
                LAST_PING["t"] = time.time()
                self._json({"ok": True, "app": APP_NAME, "version": APP_VERSION,
                            "port": PORT, "pid": os.getpid()})
            elif path == "/api/opendir":
                with LOCK:
                    d = LAST.get("dir")
                if d and os.path.isdir(d):
                    try:
                        if hasattr(os, "startfile"):
                            os.startfile(d)          # Windows
                        else:
                            webbrowser.open("file:///" + d.replace("\\", "/"))
                        self._json({"ok": True, "dir": d})
                    except Exception as e:
                        self._json({"ok": False, "error": "打不开文件夹：%s" % e, "dir": d})
                else:
                    self._json({"ok": False, "error": "还没有生成过报告。"})
            elif path == "/api/quit":
                self._json({"ok": True})
                threading.Thread(target=_shutdown, daemon=True).start()
            else:
                self._json({"ok": False, "error": "未知接口。"}, 404)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._json({"ok": False, "error": "%s: %s" % (type(e).__name__, e)}, 500)


def _shutdown():
    """先关服务再硬退出。

    只调 shutdown() 不够：ThreadingHTTPServer 的非 daemon 线程会把进程吊住，
    用户点「退出工具」后任务管理器里还留一个 exe，这是最常见的差评来源。
    所以 daemon_threads=True + 200ms 缓冲 + os._exit 三道一起上。
    """
    time.sleep(0.25)          # 给浏览器时间收下 {"ok":true}
    try:
        if SERVER is not None:
            SERVER.shutdown()
    except Exception:
        pass
    try:
        if SERVER is not None:
            SERVER.server_close()
    except Exception:
        pass
    os._exit(0)


def _reaper():
    """没页面连着就自己退，别当僵尸。

    console=False 的 exe 没有窗口可关：用户直接关掉浏览器标签页之后，
    进程还挂在那儿，只能在任务管理器里看到。这里做兜底。

    阈值给到 20 分钟，是因为浏览器会节流后台标签页的定时器（能到一分钟一次），
    设短了会把「切去开个会再回来」的用户误杀。0 表示还没人连过，不算数——
    否则服务刚起来、浏览器还没打开就会被杀掉。
    """
    while True:
        time.sleep(30)
        t = LAST_PING["t"]
        if t and time.time() - t > IDLE_EXIT_S:
            _shutdown()


def pick_port(start=BASE_PORT, span=20):
    for p in range(start, start + span):
        s = socket.socket()
        try:
            s.bind(("127.0.0.1", p))
            s.close()
            return p
        except OSError:
            s.close()
    return start


# 回环请求绝不走系统代理。很多机器设了 HTTP_PROXY 却没设 NO_PROXY，
# urllib 会把 127.0.0.1 也塞给代理，导致「检测已有实例」永远失败。
_LOCAL_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _local_get(url, timeout=1.0):
    with _LOCAL_OPENER.open(url, timeout=timeout) as r:
        return r.read()


def _listening(port, timeout=0.08):
    s = socket.socket()
    s.settimeout(timeout)
    try:
        return s.connect_ex(("127.0.0.1", port)) == 0
    except OSError:
        return False
    finally:
        s.close()


def find_running(start=BASE_PORT, span=20):
    """已有本工具实例在跑就返回它的端口，避免重复双击开出一堆服务和标签页。"""
    for p in range(start, start + span):
        if not _listening(p):
            continue
        try:
            d = json.loads(_local_get("http://127.0.0.1:%d/api/ping" % p).decode("utf-8"))
            if d.get("app") == APP_NAME:
                return p
        except Exception:
            continue
    return None


def main(no_open=False):
    global PORT, SERVER
    os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost,::1")
    os.environ.setdefault("no_proxy", "127.0.0.1,localhost,::1")

    no_open = no_open or bool(os.environ.get("CRYPTOAUDIT_NO_BROWSER"))

    # 不能靠 bind 失败判断端口被占：Windows 的 SO_REUSEADDR 允许重复绑定，
    # 第二个实例会「成功」占住同一端口，然后两个服务抢同一个浏览器页面。
    if _listening(BASE_PORT):
        running = find_running(BASE_PORT)
        if running:
            url = "http://127.0.0.1:%d/" % running
            print("=" * 56)
            print("  工具已经在运行，直接打开已有的那个。")
            print("  地址：%s" % url)
            print("  浏览器没自动打开就手动复制上面的地址。")
            print("=" * 56)
            if not no_open:
                webbrowser.open(url)
                time.sleep(1.5)
            return 0
        PORT = pick_port(BASE_PORT)
    else:
        PORT = BASE_PORT

    ThreadingHTTPServer.daemon_threads = True
    ThreadingHTTPServer.allow_reuse_address = True
    SERVER = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = "http://127.0.0.1:%d/" % PORT
    print("=" * 56)
    print("  密码应用方案自检已启动（本地运行，不联网）")
    print("  地址：%s" % url)
    print("  关掉这个窗口，或者点页面上的「退出工具」")
    print("=" * 56)
    if not no_open:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    threading.Thread(target=_reaper, daemon=True).start()
    try:
        SERVER.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出")
    return 0


if __name__ == "__main__":
    sys.exit(main("--no-open" in sys.argv))
