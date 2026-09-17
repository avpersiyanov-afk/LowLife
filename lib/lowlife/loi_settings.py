# -*- coding: utf-8 -*-
"""
Окно настроек для кнопки «Заполнение LOI» (LOI.panel) + их хранение между
запусками.

Хранится в JSON-файле %APPDATA%\\pyRevit\\LowLifeLOI_settings.json — тот же
подход, что room_finder_settings.py/room_info_settings.py/scs_settings.py
(простой файл вместо pyrevit.script.get_config(), см. их докстринги про
причину).

Имя категории «Формы» и список клонируемых параметров — соглашение
конкретного проекта/ФОП, поэтому не зашиты константами в коде, только через
это окно (Shift+клик по кнопке).
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
    StackPanel, TextBlock, TextBox, Button, Orientation, DockPanel, Dock,
    ScrollBarVisibility
)
from System.Windows.Media import Brushes

SETTINGS_FILE_NAME = "LowLifeLOI_settings.json"

# (ключ, заголовок раздела, подпись поля, пояснение под полем,
#  значение по умолчанию, многострочное поле, обязательное поле)
TEXT_FIELDS = [
    (
        "form_category_name",
        u"① Категория элементов «Форма»",
        u"Имя категории семейства",
        u"Категория, к которой должны принадлежать элементы «Форма» — их "
        u"параметры клонируются в элементы, физически находящиеся внутри их "
        u"солида. Обычно это отдельная категория семейства, заведённая под "
        u"эту задачу.",
        u"Форма", False, True
    ),
    (
        "param_names_text",
        u"② Параметры для клонирования",
        u"Имена параметров (по одному на строке)",
        u"Значения этих параметров переносятся из «Формы» в содержащиеся в "
        u"ней элементы — по имени параметра, оно должно совпадать у «Формы» "
        u"и у целевого элемента. Один параметр — одна строка.",
        u"", True, True
    ),
]

PLAIN_LABELS = {key: label for key, _section, label, _hint, _default, _multiline, _required in TEXT_FIELDS}


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
        forms.alert(
            u"Не удалось сохранить настройки в файл:\n{}".format(path)
        )


def load_saved_values():
    """Строковые значения настроек: из JSON-файла, иначе — значения по умолчанию."""
    saved = _read_all()
    return {key: saved.get(key, default)
            for key, _section, _label, _hint, default, _multiline, _required in TEXT_FIELDS}


def save_values(values):
    data = _read_all()
    data.update(values)
    _write_all(data)


def get_param_names(settings):
    """Список имён параметров из param_names_text — по одному на строке, без пустых/дублей."""
    text = settings.get("param_names_text", u"") or u""
    names = []
    seen = set()
    for line in text.splitlines():
        name = line.strip()
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names


def require(settings, keys):
    """
    Проверяет, что перечисленные ключи заполнены. Останавливает скрипт
    через forms.alert(exitscript=True), если чего-то не хватает.
    """
    missing = []

    for key in keys:
        if key == "param_names_text":
            if not get_param_names(settings):
                missing.append(PLAIN_LABELS.get(key, key))
            continue
        value = settings.get(key)
        if not (value and unicode(value).strip()):
            missing.append(PLAIN_LABELS.get(key, key))

    if missing:
        forms.alert(
            u"Не заполнены обязательные настройки:\n\n{}\n\n"
            u"Откройте настройки: Shift+клик по кнопке «Заполнение LOI».".format(
                u"\n".join(missing)
            ),
            exitscript=True
        )


def show_settings_form(values):
    """Модальное окно редактирования настроек. Возвращает словарь строковых
    значений или None, если пользователь отменил."""
    result = {"values": None}

    win = Window()
    win.Title = u"Настройки: Заполнение LOI"
    win.Width = 720
    win.Height = 520
    win.WindowStartupLocation = WindowStartupLocation.CenterScreen

    outer = DockPanel()
    outer.LastChildFill = True

    root = StackPanel()
    root.Margin = Thickness(16)

    title = TextBlock()
    title.Text = u"Категория «Формы» и параметры для клонирования"
    title.FontSize = 16
    title.FontWeight = FontWeights.Bold
    title.Margin = Thickness(0, 0, 0, 4)
    root.Children.Add(title)

    hint = TextBlock()
    hint.Text = u"Значения сохраняются и подставляются при следующих запусках."
    hint.FontSize = 11
    hint.Foreground = Brushes.Gray
    hint.Margin = Thickness(0, 0, 0, 10)
    root.Children.Add(hint)

    boxes = {}

    for key, section_title, label_text, hint_text, _, multiline, required in TEXT_FIELDS:
        section = TextBlock()
        section.Text = section_title
        section.FontWeight = FontWeights.Bold
        section.Margin = Thickness(0, 16, 0, 2)
        root.Children.Add(section)

        label = TextBlock()
        label.Text = label_text + (u" *" if required else u"")
        label.Margin = Thickness(0, 2, 0, 2)
        label.TextWrapping = TextWrapping.Wrap
        root.Children.Add(label)

        box = TextBox()
        box.Text = values.get(key, "")
        box.Padding = Thickness(4)

        if multiline:
            box.AcceptsReturn = True
            box.TextWrapping = TextWrapping.Wrap
            box.Height = 100
            box.VerticalScrollBarVisibility = ScrollBarVisibility.Auto

        root.Children.Add(box)
        boxes[key] = box

        field_hint = TextBlock()
        field_hint.Text = hint_text
        field_hint.FontSize = 11
        field_hint.Foreground = Brushes.Gray
        field_hint.TextWrapping = TextWrapping.Wrap
        field_hint.Margin = Thickness(0, 2, 0, 0)
        root.Children.Add(field_hint)

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
        result["values"] = {key: box.Text for key, box in boxes.items()}
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
        buttons, _read_all, _write_all, u"заполнения LOI", _on_settings_imported
    )

    outer.Children.Add(buttons)
    outer.Children.Add(root)

    win.Content = outer
    win.ShowDialog()

    return result["values"]


def get_settings_interactive():
    """
    Показывает окно настроек, сохраняет введённые значения и возвращает
    их. Возвращает None, если пользователь нажал «Отмена». Открывается
    по Shift+клику на кнопке «Заполнение LOI».
    """
    while True:
        saved = load_saved_values()
        edited = show_settings_form(saved)

        if edited == settings_transfer.RELOAD:
            continue

        if edited is None:
            return None

        save_values(edited)
        return edited


def get_settings_silent():
    """Настройки без показа окна — уже сохранённые значения (или значения
    по умолчанию, если ещё не настроено). Используется кнопкой «Заполнение LOI»."""
    return load_saved_values()
