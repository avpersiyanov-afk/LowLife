# -*- coding: utf-8 -*-
"""Тесты для lowlife.favorites — раскладка своих панелей («Мои панели») по папкам-ячейкам."""

import io
import os

from lowlife import favorites


def _write(path, text=u""):
    folder = os.path.dirname(path)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _read(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read()


def _extension(root):
    tab = os.path.join(root, u"LowLife.tab")
    _write(os.path.join(tab, u"bundle.yaml"), u"layout:\n  - SCS\n  - Tools\n")
    _write(os.path.join(tab, u"SCS.panel", u"bundle.yaml"), u"title: СКС\n")
    _write(os.path.join(tab, u"SCS.panel", u"Nodes.pushbutton", u"script.py"), u"print(1)\n")
    _write(os.path.join(tab, u"SCS.panel", u"Nodes.pushbutton", u"window.xaml"), u"<Window/>\n")
    _write(os.path.join(tab, u"Tools.panel", u"Pull.pulldown", u"Zoom.pushbutton", u"script.py"), u"print(2)\n")
    return tab


def _data(*buttons):
    return {u"panels": [{u"title": u"моя", u"buttons": [{u"panel": p, u"path": list(path)} for p, path in buttons]}]}


def test_write_panels_copies_buttons_into_slot(tmpdir):
    root = str(tmpdir)
    tab = _extension(root)
    changed, problems = favorites.write_panels(_data((u"SCS", [u"Nodes"]), (u"Tools", [u"Pull", u"Zoom"])), root)
    assert changed and problems == []
    slot = os.path.join(tab, u"MyPanel1.panel")
    assert _read(os.path.join(slot, u"bundle.yaml")) == u'title: "моя"\nlayout:\n  - SCS-Nodes\n  - Tools-Pull-Zoom\n'
    assert _read(os.path.join(slot, u"SCS-Nodes.pushbutton", u"window.xaml")) == u"<Window/>\n"
    assert _read(os.path.join(slot, u"Tools-Pull-Zoom.pushbutton", u"script.py")) == u"print(2)\n"
    # повторно — ничего не меняется, перезагрузка не нужна
    assert favorites.write_panels(_data((u"SCS", [u"Nodes"]), (u"Tools", [u"Pull", u"Zoom"])), root) == (False, [])


def test_write_panels_updates_copies_and_removes_stale(tmpdir):
    root = str(tmpdir)
    tab = _extension(root)
    favorites.write_panels(_data((u"SCS", [u"Nodes"]), (u"Tools", [u"Pull", u"Zoom"])), root)
    _write(os.path.join(tab, u"SCS.panel", u"Nodes.pushbutton", u"script.py"), u"print(3)\n")  # обновили LowLife
    os.remove(os.path.join(tab, u"SCS.panel", u"Nodes.pushbutton", u"window.xaml"))
    changed, _ = favorites.write_panels(_data((u"SCS", [u"Nodes"])), root)
    copy = os.path.join(tab, u"MyPanel1.panel", u"SCS-Nodes.pushbutton")
    assert changed
    assert _read(os.path.join(copy, u"script.py")) == u"print(3)\n"
    assert not os.path.exists(os.path.join(copy, u"window.xaml"))
    assert not os.path.exists(os.path.join(tab, u"MyPanel1.panel", u"Tools-Pull-Zoom.pushbutton"))
    # панель убрали — ячейка удаляется
    assert favorites.write_panels({u"panels": []}, root)[0]
    assert not os.path.exists(os.path.join(tab, u"MyPanel1.panel"))


def test_write_panels_reports_missing_button(tmpdir):
    root = str(tmpdir)
    _extension(root)
    changed, problems = favorites.write_panels(_data((u"SCS", [u"Нет"])), root)
    assert not changed and len(problems) == 1
