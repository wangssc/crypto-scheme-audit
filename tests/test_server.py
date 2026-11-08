# -*- coding: utf-8 -*-
"""本地界面服务的测试。

不依赖外面已经起着的服务：每个模块自己在一个随机端口上起一个真实实例，
测完关掉。这样 CI 和本机都能直接 `pytest tests/test_server.py`。

覆盖的都是「肉眼一看就知道坏没坏」的硬指标：
拖进去能不能出分、未评估会不会显示 0 分、界面有没有偷偷引外链、
别的网站能不能调这个接口。
"""

import base64
import json
import os
import sys
import threading
import urllib.error
import urllib.request

import pytest
from http.server import ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import server as S                              # noqa: E402

FIXTURES = os.path.join(ROOT, "tests", "fixtures")
UI = os.path.join(ROOT, "ui", "index.html")


@pytest.fixture(scope="module")
def live():
    """在随机空闲端口起一个真实服务，测完关。"""
    ThreadingHTTPServer.daemon_threads = True
    srv = ThreadingHTTPServer(("127.0.0.1", 0), S.Handler)
    port = srv.server_address[1]
    S.PORT = port
    S.SERVER = srv
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    yield port
    srv.shutdown()
    srv.server_close()


def _audit(port, name, origin=None):
    """把一个 fixture 走真实 HTTP 接口打进去。"""
    path = os.path.join(FIXTURES, name)
    raw = open(path, "rb").read() if os.path.isfile(path) else b""
    return _post(port, "/api/audit", {"name": name,
                                      "data": base64.b64encode(raw).decode()},
                 origin=origin)


def _post(port, p, payload, origin=None):
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if origin:
        headers["Origin"] = origin
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (port, p),
                                 data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def _get(port, p):
    with urllib.request.urlopen("http://127.0.0.1:%d%s" % (port, p), timeout=20) as r:
        return r.status, r.read().decode("utf-8")


# ------------------------------------------------------------ 服务活着
def test_ping(live):
    st, body = _get(live, "/api/ping")
    assert st == 200
    d = json.loads(body)
    assert d["ok"] is True and d["app"] == S.APP_NAME and d["version"]


def test_index_served(live):
    st, body = _get(live, "/")
    assert st == 200
    assert "把方案 .docx 拖到这里" in body
    assert "点这里选" in body


def test_find_running_sees_itself(live):
    """双击第二下要认出已开着的那个，不能再起一个。"""
    assert S.find_running(live, span=1) == live


# ------------------------------------------------------------ 拖拽结果
def test_good_docx_is_100_a(live):
    st, d = _audit(live, "good.docx")
    assert st == 200 and d["ok"] is True
    assert d["assessed"] is True
    assert d["score"] == 100 and d["grade"] == "A"
    assert d["counts"] == {"critical": 0, "warn": 0, "hint": 0}


def test_missing_mgmt_is_64_d_two_critical(live):
    st, d = _audit(live, "missing-mgmt.docx")
    assert d["ok"] is True and d["assessed"] is True
    assert d["score"] == 64 and d["grade"] == "D"
    assert d["counts"]["critical"] == 2
    assert sorted(f["id"] for f in d["findings"] if f["level"] == "critical") \
        == ["C-02", "C-05"]


def test_not_a_scheme_is_not_assessed_not_zero(live):
    """最容易被写错的一条：未评估时给 0 分，用户会以为文档烂透了。"""
    st, d = _audit(live, "not-a-scheme.docx")
    assert d["ok"] is True
    assert d["assessed"] is False
    assert d["score"] is None           # 不是 0
    assert d["grade"] == "?"
    assert "8" in d["reason"] or "章节" in d["reason"]


def test_rejects_non_docx(live):
    st, d = _post(live, "/api/audit", {"name": "方案.pdf", "data": "AAAA"})
    assert d["ok"] is False and ".docx" in d["error"]


def test_rejects_empty_payload(live):
    st, d = _post(live, "/api/audit", {"name": "a.docx", "data": ""})
    assert d["ok"] is False


# ------------------------------------------------------------ 报告产物
def test_report_html_is_self_contained(live):
    """另存为 HTML 之后断网也得能看，所以不能有任何外链。"""
    st, d = _audit(live, "good.docx")
    html = d["report_html"]
    assert html.startswith("<!doctype html>")
    assert "http://" not in html and "https://" not in html
    assert "<link" not in html and "<script" not in html


def test_report_written_to_disk(live):
    st, d = _audit(live, "missing-mgmt.docx")
    out = os.path.join(d["dir"], d["report_file"])
    assert os.path.isfile(out)
    text = open(out, encoding="utf-8").read()
    assert "密码应用方案自检报告" in text
    assert "missing-mgmt" in text


def test_report_dir_differs_per_call(live):
    """同一秒连拖两份，不能挤进同一个文件夹。"""
    _, a = _audit(live, "good.docx")
    _, b = _audit(live, "good.docx")
    assert a["dir"] != b["dir"]


# ------------------------------------------------------------ 安全
def test_blocks_cross_site_origin(live):
    """别的网页不能悄悄让本机跑检查。"""
    st, d = _post(live, "/api/audit", {"name": "good.docx", "data": "AAAA"},
                  origin="http://evil.example.com")
    assert st == 403 and d["ok"] is False


def test_allows_loopback_origin(live):
    st, d = _post(live, "/api/ping", {}, origin="http://127.0.0.1:%d" % live)
    assert st == 200 and d["ok"] is True


# ------------------------------------------------------------ 界面静态
def test_ui_has_no_external_resources():
    html = open(UI, encoding="utf-8").read()
    assert "http://" not in html and "https://" not in html
    for bad in ("cdn.", "googleapis", "unpkg", "jsdelivr", "@import"):
        assert bad not in html
    for fw in ("react", "vue", "tailwind", "jquery"):
        assert fw not in html.lower()


def test_ui_has_required_controls():
    html = open(UI, encoding="utf-8").read()
    for key in ("drop", "btnNew", "btnSave", "btnDir", "btnQuit",
                "未评估", "换一份", "另存为 HTML", "打开报告文件夹", "退出工具"):
        assert key in html, key


def test_ui_watchdog_pings():
    """服务挂了要盖遮罩，不能让用户对着转圈干等。"""
    html = open(UI, encoding="utf-8").read()
    assert "api/ping" in html and "服务已停止" in html


# ------------------------------------------------------------ 打开文件夹 / 退出
def test_opendir_opens_last_report(live, monkeypatch):
    _, d = _audit(live, "good.docx")
    seen = {}
    monkeypatch.setattr(S.os, "startfile", lambda p: seen.setdefault("dir", p),
                        raising=False)
    st, r = _post(live, "/api/opendir", {})
    assert r["ok"] is True
    assert seen["dir"] == d["dir"]


def _free_port():
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def test_quit_really_exits():
    """「退出工具」点完进程必须真没了。

    单独起一个子进程测：os._exit 会带走整个进程，
    在 pytest 自己的进程里调等于自杀。
    """
    import subprocess
    import time

    port = _free_port()
    env = dict(os.environ, CRYPTOAUDIT_PORT=str(port), CRYPTOAUDIT_NO_BROWSER="1")
    proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "app.py")],
                            env=env, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    try:
        for _ in range(80):
            try:
                _get(port, "/api/ping")
                break
            except Exception:
                time.sleep(0.1)
        else:
            pytest.fail("服务没起来")

        st, d = _post(port, "/api/quit", {})
        assert d["ok"] is True
        proc.wait(timeout=8)
        assert proc.poll() is not None, "退出接口调完进程还活着"
    finally:
        if proc.poll() is None:
            proc.kill()


@pytest.mark.skipif(sys.platform != "win32", reason="只用 Windows 的 pythonw")
def test_starts_without_console_streams():
    """双击 exe 时 sys.stdout 是 None，任何 print 都会崩成「双击没反应」。

    用 pythonw 起（GUI 子系统，没有控制台）来卡这一条：
    代码里没兜住 None 的话，服务根本起不来，下面的 ping 会超时。
    """
    import subprocess
    import time

    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.isfile(pythonw):
        pytest.skip("没有 pythonw.exe")

    port = _free_port()
    env = dict(os.environ, CRYPTOAUDIT_PORT=str(port), CRYPTOAUDIT_NO_BROWSER="1")
    DETACHED_PROCESS = 0x00000008
    proc = subprocess.Popen([pythonw, os.path.join(ROOT, "app.py")], env=env,
                            stdout=None, stderr=None,
                            creationflags=DETACHED_PROCESS)
    try:
        for _ in range(100):
            try:
                st, body = _get(port, "/api/ping")
                assert json.loads(body)["ok"] is True
                break
            except Exception:
                time.sleep(0.1)
        else:
            pytest.fail("无控制台启动失败——多半是 print 打到 None 上崩了")
    finally:
        try:
            _post(port, "/api/quit", {})
        except Exception:
            pass
        time.sleep(0.6)
        if proc.poll() is None:
            proc.kill()
