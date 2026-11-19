# -*- coding: utf-8 -*-
"""Theme selection without importing WPF; native rendering is checked in Revit."""
import sys
from types import ModuleType

import pytest

from lowlife import ui_theme


@pytest.mark.parametrize('revit_theme', ['Dark', 'Light'])
def test_revit_theme_has_priority_over_windows(monkeypatch, revit_theme):
    for name in ('pyrevit', 'pyrevit.revit', 'pyrevit.revit.ui'):
        monkeypatch.setitem(sys.modules, name, ModuleType(name))
    sys.modules['pyrevit.revit.ui'].get_current_theme = lambda: revit_theme
    registry = ModuleType('winreg')

    def unexpected_registry_access(*args):
        pytest.fail('Windows preference must not override Revit')

    registry.OpenKey = unexpected_registry_access
    monkeypatch.setitem(sys.modules, 'winreg', registry)
    assert ui_theme.current_theme() == revit_theme.lower()


@pytest.mark.parametrize('windows_light, expected', [(0, 'dark'), (1, 'light')])
def test_standalone_uses_windows_app_theme_and_closes_registry(monkeypatch, windows_light, expected):
    monkeypatch.setitem(sys.modules, 'pyrevit', None)
    registry = ModuleType('winreg')
    registry.HKEY_CURRENT_USER = object()
    handle, closed = object(), []
    registry.OpenKey = lambda root, path: handle
    registry.QueryValueEx = lambda key, name: (windows_light, 4)
    registry.CloseKey = closed.append
    monkeypatch.setitem(sys.modules, 'winreg', registry)
    assert ui_theme.current_theme() == expected
    assert closed == [handle]


def test_missing_windows_preference_has_safe_light_fallback(monkeypatch):
    monkeypatch.setitem(sys.modules, 'pyrevit', None)
    registry = ModuleType('winreg')
    registry.HKEY_CURRENT_USER = object()

    def missing_key(*args):
        raise OSError('not available')

    registry.OpenKey = missing_key
    monkeypatch.setitem(sys.modules, 'winreg', registry)
    assert ui_theme.current_theme() == 'light'
