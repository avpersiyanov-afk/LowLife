# -*- coding: utf-8 -*-
"""Тесты для lowlife.ribbon_catalog — список панелей/кнопок для окна «Обратная связь»."""

import io
import os

from lowlife import ribbon_catalog


def _write(root, rel, text):
    path = os.path.join(root, *rel.split("/"))
    folder = os.path.dirname(path)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(text)


def test_titles_and_layout_order(tmpdir):
    root = str(tmpdir)
    _write(root, "LowLife.tab/bundle.yaml", u"layout:\n  - B\n  - A\n")
    _write(root, "LowLife.tab/A.panel/bundle.yaml", u"title: Панель А\n")
    _write(root, "LowLife.tab/A.panel/One.pushbutton/bundle.yaml", u"title: Первая\ntooltip: x\n")
    _write(root, "LowLife.tab/B.panel/bundle.yaml",
           u"title: 'Панель Б'\ntooltip: t\nlayout:\n  - Zed\n  - Alpha\n")
    _write(root, "LowLife.tab/B.panel/Alpha.pushbutton/script.py",
           u'# -*- coding: utf-8 -*-\n__title__ = u"Цепи\\nшлейфов"\n')
    _write(root, "LowLife.tab/B.panel/Zed.pushbutton/bundle.yaml", u"title: >-\n  Длинная\n  подпись\n")
    _write(root, "LowLife.tab/B.panel/Extra.pushbutton/script.py", u"pass\n")
    assert ribbon_catalog.list_panels(root) == [
        (u"Панель Б", [u"Длинная подпись", u"Цепи шлейфов", u"Extra"]),
        (u"Панель А", [u"Первая"]),
    ]


def test_stack_expanded_and_empty_panel_skipped(tmpdir):
    root = str(tmpdir)
    _write(root, "LowLife.tab/_Themes.panel/Theme.combobox/bundle.yaml", u"title: Тема\n")
    _write(root, "LowLife.tab/S.panel/Group.stack/X.pushbutton/bundle.yaml", u"title: Икс\n")
    _write(root, "LowLife.tab/S.panel/Group.stack/Y.pushbutton/bundle.yaml", u"title: Игрек\n")
    _write(root, "LowLife.tab/Empty.panel/bundle.yaml", u"title: Пусто\n")
    assert ribbon_catalog.list_panels(root) == [
        (u"Themes", [u"Тема"]),
        (u"S", [u"Икс", u"Игрек"]),
    ]


def test_real_extension_lists_feedback_button():
    panels = dict(ribbon_catalog.list_panels())
    assert u"Обратная связь" in panels[u"LowLife"]
    assert all(buttons for buttons in panels.values())
