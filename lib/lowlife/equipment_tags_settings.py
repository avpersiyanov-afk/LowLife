# -*- coding: utf-8 -*-
"""
Настройки кнопки «Марки оборудования» + их хранение между запусками.

Хранится в JSON-файле %APPDATA%\\pyRevit\\LowLifeEquipmentTags_settings.json —
тот же подход, что room_info_settings.py/scs_settings.py (простой файл
вместо pyrevit.script.get_config(), см. их докстринги про причину).

Все расстояния — в миллиметрах НА ЛИСТЕ: при раскладке умножаются на
масштаб вида, поэтому на 1:50 и 1:100 марки выглядят одинаково.
"""

import os
import io
import json

import clr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')

from pyrevit import forms

from lowlife import settings_transfer

from System.Windows import (
    Window, WindowStartupLocation, Thickness,
    FontWeights, HorizontalAlignment, TextWrapping
)
from System.Windows.Controls import (
    StackPanel, TextBlock, TextBox, Button, Orientation, DockPanel, Dock
)
from System.Windows.Media import Brushes

SETTINGS_FILE_NAME = "LowLifeEquipmentTags_settings.json"

# (ключ, подпись поля, пояснение, значение по умолчанию, мм на листе)
FIELDS = [
    (
        "offset_mm",
        u"Отступ марок от оборудования, мм",
        u"На каком расстоянии от габарита оборудования встаёт колонка/"
        u"стопка марок. Если места нет, кнопка сама пробует 2× и 3× отступ.",
        3.0
    ),
    (
        "gap_mm",
        u"Зазор между марками, мм",
        u"Минимальный промежуток между соседними марками в колонке/стопке.",
        1.0
    ),
    (
        "shelf_mm",
        u"Длина полки выноски, мм",
        u"Короткий горизонтальный отрезок линии-выноски у самой марки "
        u"(«полочка»), от которого наклонная часть идёт к оборудованию.",
        3.0
    ),
    (
        "cluster_mm",
        u"«Рядом» — если оборудование ближе, мм",
        u"Оборудование, стоящее друг от друга ближе этого расстояния, "
        u"получает марки одним блоком: рядом по горизонтали — стопкой "
        u"друг над другом, одно над другим — колонкой сбоку на одном "
        u"отступе.",
        8.0
    ),
]

LABELS = dict((key, label) for key, label, _hint, _default in FIELDS)


def _settings_file_path():
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    folder = os.path.join(appdata, "pyRevit")
    if not os.path.isdir(folder):
        try:
            os.makedirs(folder)
        except:
            pass
    return os.path.join(folder, SETTINGS_FILE_NAME)


def _read_all():
    path = _settings_file_path()
    if not os.path.isfile(path):
        return {}
    try:
        with io.open(path, "r", encoding="utf-8") as f:
            text = f.read()
        if not text.strip():
            return {}
        return json.loads(text)
    except:
        return {}


def _write_all(data):
    path = _settings_file_path()
    try:
        with io.open(path, "w", encoding="utf-8") as f:
            f.write(unicode(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)))
    except:
        forms.alert(u"Не удалось сохранить настройки в файл:\n{}".format(path))


def _to_float(value):
    try:
        return float(unicode(value).strip().replace(u",", u"."))
    except Exception:
        return None


def load_settings():
    """Числовые настройки: сохранённые, иначе по умолчанию (битые/
    отрицательные значения тоже заменяются значениями по умолчанию)."""
    saved = _read_all()
    result = {}
    for key, _label, _hint, default in FIELDS:
        v = _to_float(saved.get(key, default))
        result[key] = v if v is not None and v >= 0 else default
    return result


def show_settings_form(values):
    """Модальное окно. Возвращает словарь строк, None (отмена) или
    settings_transfer.RELOAD."""
    result = {"values": None}

    win = Window()
    win.Title = u"Настройки: Марки оборудования"
    win.Width = 620
    win.Height = 520
    win.WindowStartupLocation = WindowStartupLocation.CenterScreen

    outer = DockPanel()
    outer.LastChildFill = True

    root = StackPanel()
    root.Margin = Thickness(16)

    title = TextBlock()
    title.Text = u"Раскладка марок оборудования"
    title.FontSize = 16
    title.FontWeight = FontWeights.Bold
    title.Margin = Thickness(0, 0, 0, 4)
    root.Children.Add(title)

    hint = TextBlock()
    hint.Text = (u"Все расстояния — в мм на листе, как на распечатке: при масштабе "
                 u"вида 1:100 отступ 3 мм — это 300 мм в модели. "
                 u"Значения сохраняются между запусками.")
    hint.FontSize = 11
    hint.Foreground = Brushes.Gray
    hint.TextWrapping = TextWrapping.Wrap
    hint.Margin = Thickness(0, 0, 0, 6)
    root.Children.Add(hint)

    boxes = {}
    for key, label_text, hint_text, _default in FIELDS:
        label = TextBlock()
        label.Text = label_text
        label.FontWeight = FontWeights.Bold
        label.Margin = Thickness(0, 12, 0, 2)
        root.Children.Add(label)

        box = TextBox()
        box.Text = unicode(values.get(key, u""))
        box.Padding = Thickness(4)
        root.Children.Add(box)
        boxes[key] = box

        h = TextBlock()
        h.Text = hint_text
        h.FontSize = 11
        h.Foreground = Brushes.Gray
        h.TextWrapping = TextWrapping.Wrap
        h.Margin = Thickness(0, 2, 0, 0)
        root.Children.Add(h)

    buttons = StackPanel()
    buttons.Orientation = Orientation.Horizontal
    buttons.HorizontalAlignment = HorizontalAlignment.Right
    buttons.Margin = Thickness(16, 8, 16, 12)
    DockPanel.SetDock(buttons, Dock.Bottom)

    cancel_btn = Button()
    cancel_btn.Content = u"Отмена"
    cancel_btn.Padding = Thickness(10, 4, 10, 4)
    cancel_btn.Margin = Thickness(0, 0, 8, 0)

    ok_btn = Button()
    ok_btn.Content = u"Сохранить"
    ok_btn.Padding = Thickness(10, 4, 10, 4)
    ok_btn.FontWeight = FontWeights.Bold

    def on_ok(sender, args):
        bad = [LABELS[k] for k, b in boxes.items()
               if _to_float(b.Text) is None or _to_float(b.Text) < 0]
        if bad:
            forms.alert(u"Нужно неотрицательное число:\n\n" + u"\n".join(bad))
            return
        result["values"] = dict((k, _to_float(b.Text)) for k, b in boxes.items())
        win.Close()

    def on_cancel(sender, args):
        win.Close()

    ok_btn.Click += on_ok
    cancel_btn.Click += on_cancel

    buttons.Children.Add(cancel_btn)
    buttons.Children.Add(ok_btn)

    def _on_settings_imported():
        result["values"] = settings_transfer.RELOAD
        win.Close()

    settings_transfer.add_transfer_buttons(
        buttons, _read_all, _write_all, u"марок оборудования", _on_settings_imported
    )

    outer.Children.Add(buttons)
    outer.Children.Add(root)

    win.Content = outer
    win.ShowDialog()

    return result["values"]


def get_settings_interactive():
    """Окно настроек (Shift+клик по кнопке). None — если «Отмена»."""
    while True:
        edited = show_settings_form(load_settings())
        if edited == settings_transfer.RELOAD:
            continue
        if edited is None:
            return None
        data = _read_all()
        data.update(edited)
        _write_all(data)
        return load_settings()
