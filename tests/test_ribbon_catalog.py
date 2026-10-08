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


def _entry(title, panel_title=u"П", tooltip=u"", path=(u"B",)):
    return {u"panel": u"P", u"panel_title": panel_title, u"button": path[-1], u"path": list(path),
            u"title": title, u"tooltip": tooltip}


def test_list_buttons_fields_pulldown_and_combobox(tmpdir):
    root = str(tmpdir)
    _write(root, "LowLife.tab/A.panel/bundle.yaml", u"title: Панель А\n")
    _write(root, "LowLife.tab/A.panel/One.pushbutton/bundle.yaml",
           u"title: Первая\ntooltip: |\n  Строка один\n  строка два\n")
    _write(root, "LowLife.tab/A.panel/Two.pushbutton/script.py",
           u'__title__ = u"Вторая"\n__doc__ = u"Из скрипта"\n')
    _write(root, "LowLife.tab/A.panel/More.pulldown/Inner.pushbutton/bundle.yaml", u"title: Внутри\n")
    _write(root, "LowLife.tab/A.panel/Theme.combobox/bundle.yaml", u"title: Тема\n")
    buttons = ribbon_catalog.list_buttons(root)
    assert [(b[u"title"], b[u"path"], b[u"tooltip"]) for b in buttons] == [
        (u"Внутри", [u"More", u"Inner"], u""),
        (u"Первая", [u"One"], u"Строка один строка два"),
        (u"Вторая", [u"Two"], u"Из скрипта"),
    ]
    assert all(b[u"panel"] == u"A" and b[u"panel_title"] == u"Панель А" for b in buttons)


def test_search_ranking_and_normalization():
    entries = [
        _entry(u"Длина линий", tooltip=u"считает цепи"),
        _entry(u"Цепи СКС", panel_title=u"Цепи СКС"),
        _entry(u"Лоток СБ", panel_title=u"Лестничный лоток"),
        _entry(u"Синхронизация цепей"),
        _entry(u"Счёт"),
    ]
    titles = lambda q: [e[u"title"] for e in ribbon_catalog.search(entries, q)]
    assert titles(u"") == [e[u"title"] for e in entries]
    # начало подписи → подпись → (панель) → подсказка
    assert titles(u"ЦЕПИ") == [u"Цепи СКС", u"Синхронизация цепей", u"Длина линий"]
    assert titles(u"сб лестн") == [u"Лоток СБ"]
    assert titles(u"счет") == [u"Счёт"]
    assert titles(u"wtgb crc") == [u"Цепи СКС"]  # набрано в английской раскладке
    assert titles(u"нет такого") == []
