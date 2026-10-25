# -*- coding: utf-8 -*-
"""Exercise real ribbon translation with wrappers rebuilt after each rename."""
import sys
import types

import pytest

from lowlife import i18n, ribbon_catalog, ribbon_language as ribbon


class Store(dict):
    def ContainsKey(self, key):
        return key in self


class Item(object):
    def __init__(self, name, api):
        self.name = name
        self.api = api

    def get_rvtapi_object(self):
        return self.api


class Panel(Item):
    def __init__(self, api, child, dynamic):
        Item.__init__(self, api.Title if dynamic else u'Справка', api)
        self.child = child

    def __iter__(self):
        return iter([self.child])


@pytest.mark.parametrize('dynamic', [False, True])
def test_panel_and_button_roundtrip_with_fresh_wrappers(monkeypatch, dynamic):
    store = Store()
    panel_api = types.SimpleNamespace(Title=u'Справка')
    button_api = types.SimpleNamespace(ItemText=u'Обратная связь', ToolTip=u'Подсказка')
    button = Item('Feedback', button_api)
    ui = types.SimpleNamespace(get_pyrevit_tabs=lambda: [[Panel(panel_api, button, dynamic)]])
    module = types.ModuleType('pyrevit.coreutils.ribbon')
    module.get_current_ui = lambda: ui
    monkeypatch.setitem(sys.modules, 'pyrevit', types.ModuleType('pyrevit'))
    monkeypatch.setitem(sys.modules, 'pyrevit.coreutils', types.ModuleType('pyrevit.coreutils'))
    monkeypatch.setitem(sys.modules, 'pyrevit.coreutils.ribbon', module)
    monkeypatch.setattr(ribbon, '_originals', lambda: store)
    monkeypatch.setattr(ribbon, 'panel_index', lambda: {u'Справка': ('panel', {'Feedback': 'button'})})
    monkeypatch.setattr(ribbon_catalog, 'item_title', lambda folder: u'Справка')
    monkeypatch.setattr(ribbon_catalog, 'raw_bundle_text', lambda folder: {
        'title_en': 'Help' if folder == 'panel' else 'Feedback', 'tooltip_en': 'Tooltip'})

    for _ in range(2):
        ribbon.apply_language(i18n.EN)
        assert panel_api.Title == 'Help'
        assert button_api.ItemText == 'Feedback' and button_api.ToolTip == 'Tooltip'
        ribbon.apply_language(i18n.RU)
        assert panel_api.Title == u'Справка'
        assert button_api.ItemText == u'Обратная связь' and button_api.ToolTip == u'Подсказка'
    # A stale capture of an English title must not prevent recovery either.
    store[u'panel|Справка'] = 'Help'
    panel_api.Title = 'Help'
    ribbon.apply_language(i18n.RU)
    assert panel_api.Title == u'Справка'
    assert u'panel|Help' not in store
