# -*- coding: utf-8 -*-
"""Окно «Приветствие» (Tools.panel/Greeting): приветствие большими буквами
по времени суток и имени пользователя Revit. Текст — greeting.greeting_lines.

show(uiapp) — показать сейчас (кнопка). show_on_startup(uiapp) — показать
при запуске Revit (hooks/app-init.py): на первом Idling, когда интерфейс
уже загружен, и один раз за сеанс Revit (флаг в AppDomain — перезагрузка
pyRevit приветствие не повторяет).
"""

import clr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')

from System import DateTime, Environment
from System.Windows import (CornerRadius, FontWeights, HorizontalAlignment, SizeToContent,
                            TextAlignment, Thickness, Window, WindowStartupLocation,
                            WindowStyle)
from System.Windows.Controls import Border, StackPanel, TextBlock
from System.Windows.Input import Key
from System.Windows.Media import Brushes, Color, FontFamily, SolidColorBrush

from lowlife import greeting

ORANGE = SolidColorBrush(Color.FromRgb(0xF0, 0x8C, 0x28))

_STARTUP_KEY = "lowlife_greeting_shown"


def _user_name(uiapp):
    try:
        name = uiapp.Application.Username
    except Exception:
        name = None
    return name or Environment.UserName


def _text(value, size, brush):
    tb = TextBlock()
    tb.Text = value
    tb.FontSize = size
    tb.FontWeight = FontWeights.Bold
    tb.FontFamily = FontFamily(u"Century Gothic, Segoe UI")
    tb.Foreground = brush
    tb.TextAlignment = TextAlignment.Center
    tb.HorizontalAlignment = HorizontalAlignment.Center
    return tb


def show(uiapp=None):
    head, tail = greeting.greeting_lines(DateTime.Now.Hour, _user_name(uiapp))

    stack = StackPanel()
    stack.Children.Add(_text(head, 72, Brushes.White))
    if tail:
        stack.Children.Add(_text(tail, 96, ORANGE))

    border = Border()
    border.Background = Brushes.Black
    border.CornerRadius = CornerRadius(24)
    border.Padding = Thickness(56, 40, 56, 40)
    border.Child = stack

    win = Window()
    win.Title = u"LowLife"
    # WindowStyle.None — синтаксическая ошибка в Python 2, берём через getattr.
    win.WindowStyle = getattr(WindowStyle, 'None')
    win.AllowsTransparency = True
    win.Background = Brushes.Transparent
    win.SizeToContent = SizeToContent.WidthAndHeight
    win.WindowStartupLocation = WindowStartupLocation.CenterScreen
    win.ShowInTaskbar = False
    win.Content = border

    def _close(sender, args):
        win.Close()

    def _keys(sender, args):
        if args.Key in (Key.Escape, Key.Enter, Key.Space):
            win.Close()

    win.MouseLeftButtonUp += _close
    win.KeyDown += _keys
    win.ShowDialog()


def _first_time_this_session():
    try:
        from System import AppDomain
        dom = AppDomain.CurrentDomain
        if dom.GetData(_STARTUP_KEY):
            return False
        dom.SetData(_STARTUP_KEY, True)
    except Exception:
        pass
    return True


def show_on_startup(uiapp):
    if not _first_time_this_session():
        return
    if uiapp is None:
        show(None)
        return

    def _on_idling(sender, args):
        try:
            sender.Idling -= _on_idling
        except Exception:
            pass
        try:
            show(sender)
        except Exception:
            pass

    try:
        uiapp.Idling += _on_idling
    except Exception:
        show(uiapp)
