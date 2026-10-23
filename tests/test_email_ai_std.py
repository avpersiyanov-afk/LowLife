# -*- coding: utf-8 -*-
"""Тесты для lowlife.email_ai_std — запуск программы и HTTP на stdlib в
отдельном приложении «Задачи из почты»: stdin в UTF-8, код выхода, отмена,
ответы HTTP и отсутствие связи. Здесь нет clr, поэтому email_ai_net
выбирает именно эту обвязку."""

import json
import sys
import threading

try:
    from http.server import BaseHTTPRequestHandler, HTTPServer
except ImportError:  # Python 2
    from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer

import pytest

from lowlife import email_ai_core, email_ai_net, email_ai_std


def test_net_picks_stdlib_without_clr():
    assert email_ai_net.run_process is email_ai_std.run_process
    assert email_ai_net.post_json is email_ai_std.post_json


def test_run_process_passes_utf8_stdin():
    code = (u"import sys; i = getattr(sys.stdin, 'buffer', sys.stdin); o = getattr(sys.stdout, 'buffer', sys.stdout); "
            u"o.write(i.read().decode('utf-8').upper().encode('utf-8')); sys.stderr.write('err'); sys.exit(3)")
    exit_code, out, err = email_ai_std.run_process(sys.executable, [u"-c", code], u"письмо", u"python")
    assert (exit_code, out, err) == (3, u"ПИСЬМО", u"err")


def test_run_process_cancel_kills():
    ticks = []

    def tick():
        ticks.append(1)
        return len(ticks) > 1

    with pytest.raises(email_ai_core.Cancelled):
        email_ai_std.run_process(sys.executable, [u"-c", u"import time; time.sleep(30)"], u"", u"python",
                                 tick=tick)


def test_run_process_missing_program_is_fatal():
    with pytest.raises(email_ai_core.AIError) as info:
        email_ai_std.run_process(u"/нет/такой/программы", [], u"", u"claude")
    assert info.value.fatal


@pytest.fixture
def server():
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            calls.append((self.headers.get("x-api-key"), json.loads(body.decode("utf-8"))))
            status = 401 if self.path == "/bad" else 200
            self.send_response(status)
            self.end_headers()
            self.wfile.write(json.dumps({"ok": status == 200}).encode("utf-8"))

        def log_message(self, *args):
            pass

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever)
    thread.daemon = True
    thread.start()
    yield "http://127.0.0.1:{}".format(httpd.server_port), calls
    httpd.shutdown()


def test_post_json_ok_and_http_error(server):
    url, calls = server
    status, text = email_ai_std.post_json(url + "/ok", {"x-api-key": "k", "content-type": "application/json"},
                                          {"text": u"привет"})
    assert status == 200 and json.loads(text) == {"ok": True}
    assert calls[0] == ("k", {"text": u"привет"})
    status, text = email_ai_std.post_json(url + "/bad", {}, {})
    assert status == 401 and json.loads(text) == {"ok": False}


def test_post_json_no_connection():
    status, text = email_ai_std.post_json("http://127.0.0.1:9/", {}, {}, timeout_seconds=5)
    assert status is None and text
