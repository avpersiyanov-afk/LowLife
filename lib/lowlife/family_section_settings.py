# -*- coding: utf-8 -*-
"""
Окно настроек кнопки «Разрез по семейству» (Tools.panel/FamilySection) +
их хранение между запусками.

JSON-файл %APPDATA%\\pyRevit\\LowLifeFamilySection_settings.json — тот же
подход, что floor_settings.py/scs_settings.py (простой файл вместо
pyrevit.script.get_config()).

Шаблон вида и типоразмер разреза хранятся ПО ИМЕНИ, а не по ElementId —
тот же довод, что в floor_settings.py: имя обычно одинаково между
проектами (из общего шаблона проекта), а Id — нет.
"""

import os
import io
import json

import clr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')

from pyrevit import forms

from lowlife import settings_transfer
from lowlife import family_section

from System.Windows import (
    Window, WindowStartupLocation, Thickness, FontWeights,
    HorizontalAlignment, TextWrapping, SizeToContent, ResizeMode
)
from System.Windows.Controls import (
    StackPanel, TextBlock, TextBox, Button, Orientation, ComboBox, CheckBox,
    RadioButton
)
from System.Windows.Media import Brushes

SETTINGS_FILE_NAME = "LowLifeFamilySection_settings.json"

TEMPLATE_KEY = "view_template_name"
TYPE_KEY = "section_type_name"
NAME_MASK_KEY = "name_mask"
SIDE_KEY = "side_offset_mm"
FRONT_KEY = "front_offset_mm"
BACK_KEY = "back_offset_mm"
OPEN_VIEW_KEY = "open_view"
FLIP_KEY = "flip_side"
HIDE_OTHER_BUILDINGS_KEY = "hide_other_building_levels"
# Ответы окна-вопроса перед построением (ask_run_options) — запоминаются как
# значения по умолчанию для следующего запуска.
COMBINE_KEY = "combine_multiple"
BOTTOM_KEY = "bottom_offset_mm"

DEFAULTS = {
    TEMPLATE_KEY: u"",
    TYPE_KEY: u"",
    NAME_MASK_KEY: u"Разрез {Семейство} {Id}",
    SIDE_KEY: 2000.0,
    FRONT_KEY: 100.0,
    BACK_KEY: 1000.0,
    OPEN_VIEW_KEY: True,
    FLIP_KEY: False,
    HIDE_OTHER_BUILDINGS_KEY: True,
    COMBINE_KEY: False,
    BOTTOM_KEY: 0.0,
}

NO_TEMPLATE = u"<Без шаблона>"
DEFAULT_TYPE = u"<Тип по умолчанию в проекте>"


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


def is_configured():
    """True, если настройки уже хоть раз сохранялись (файл непустой)."""
    return bool(_read_all())


def load_saved_values():
    saved = _read_all()
    values = dict(DEFAULTS)
    for key in DEFAULTS:
        if key in saved:
            values[key] = saved[key]
    for key in (SIDE_KEY, FRONT_KEY, BACK_KEY, BOTTOM_KEY):
        try:
            values[key] = float(values[key])
        except (TypeError, ValueError):
            values[key] = DEFAULTS[key]
    values[OPEN_VIEW_KEY] = bool(values[OPEN_VIEW_KEY])
    values[FLIP_KEY] = bool(values[FLIP_KEY])
    values[HIDE_OTHER_BUILDINGS_KEY] = bool(values[HIDE_OTHER_BUILDINGS_KEY])
    values[COMBINE_KEY] = bool(values[COMBINE_KEY])
    return values


def save_values(values):
    data = _read_all()
    data.update(values)
    _write_all(data)


def _parse_mm(text, label, errors):
    try:
        val = float(unicode(text).strip().replace(u",", u"."))
    except (TypeError, ValueError):
        errors.append(u"«{}» — не число".format(label))
        return None
    if val < 0:
        errors.append(u"«{}» — не может быть отрицательным".format(label))
        return None
    return val


def _label(parent, text, bold=False, top=10):
    tb = TextBlock()
    tb.Text = text
    tb.TextWrapping = TextWrapping.Wrap
    tb.Margin = Thickness(0, top, 0, 2)
    if bold:
        tb.FontWeight = FontWeights.Bold
    parent.Children.Add(tb)
    return tb


def _hint(parent, text):
    tb = TextBlock()
    tb.Text = text
    tb.FontSize = 11
    tb.Foreground = Brushes.Gray
    tb.TextWrapping = TextWrapping.Wrap
    tb.Margin = Thickness(0, 2, 0, 0)
    parent.Children.Add(tb)
    return tb


def _combo(parent, items, selected):
    cb = ComboBox()
    for item in items:
        cb.Items.Add(item)
    cb.SelectedIndex = items.index(selected) if selected in items else 0
    parent.Children.Add(cb)
    return cb


def _textbox(parent, text):
    tb = TextBox()
    tb.Text = text
    tb.Padding = Thickness(4)
    parent.Children.Add(tb)
    return tb


def _fmt_mm(val):
    return u"{:g}".format(float(val))


def show_settings_form(doc, values):
    """
    Модальное окно настроек. Возвращает словарь значений или None при
    отмене (или settings_transfer.RELOAD после загрузки из файла).
    """
    templates = [family_section.safe_name(v) for v in family_section.list_section_templates(doc)]
    types = [family_section.safe_name(t) for t in family_section.list_section_types(doc)]

    result = {"values": None}

    win = Window()
    win.Title = u"Настройки: Разрез по семейству"
    win.Width = 520
    win.SizeToContent = SizeToContent.Height
    win.WindowStartupLocation = WindowStartupLocation.CenterScreen

    root = StackPanel()
    root.Margin = Thickness(16, 12, 16, 12)

    title = TextBlock()
    title.Text = u"Разрез по семейству"
    title.FontSize = 16
    title.FontWeight = FontWeights.Bold
    root.Children.Add(title)
    _hint(root, u"Значения сохраняются и применяются при каждом запуске кнопки.")

    _label(root, u"Шаблон вида", bold=True, top=14)
    template_items = [NO_TEMPLATE] + templates
    template_cb = _combo(root, template_items, values.get(TEMPLATE_KEY) or NO_TEMPLATE)
    if not templates:
        _hint(root, u"В проекте нет шаблонов видов для разрезов.")

    _label(root, u"Типоразмер разреза", bold=True)
    type_items = [DEFAULT_TYPE] + types
    type_cb = _combo(root, type_items, values.get(TYPE_KEY) or DEFAULT_TYPE)

    _label(root, u"Имя разреза", bold=True)
    mask_box = _textbox(root, values.get(NAME_MASK_KEY) or u"")
    _hint(root, u"Подстановки: " + u"; ".join(
        u"{} — {}".format(k, d) for k, d in family_section.NAME_PLACEHOLDERS
    ) + u". Если имя уже занято, добавляется « (2)», « (3)», ...")

    _label(root, u"Подрезка, мм", bold=True, top=14)
    _hint(root, u"По высоте — от базового уровня семейства до следующего этажа "
                u"того же корпуса. Имя уровня разбирается по шаблону "
                u"Дисциплина_Корпус_Отметка_Этаж_Комментарий: берётся ближайший "
                u"по отметке уровень выше с тем же корпусом и другим этажом.")

    _label(root, u"Слева и справа от семейства")
    side_box = _textbox(root, _fmt_mm(values[SIDE_KEY]))
    _label(root, u"Перед геометрией семейства (плоскость сечения)")
    front_box = _textbox(root, _fmt_mm(values[FRONT_KEY]))
    _label(root, u"За геометрией семейства (дальняя граница)")
    back_box = _textbox(root, _fmt_mm(values[BACK_KEY]))

    flip_cb = CheckBox()
    flip_cb.Content = u"Смотреть с обратной стороны"
    flip_cb.IsChecked = bool(values.get(FLIP_KEY))
    flip_cb.Margin = Thickness(0, 14, 0, 0)
    root.Children.Add(flip_cb)
    _hint(root, u"Обычно не нужно: разрез смотрит на лицевую сторону семейства "
                u"(для устройств на стене — со стороны помещения). Включите, "
                u"если у ваших семейств лицевая сторона задана наоборот.")

    hide_cb = CheckBox()
    hide_cb.Content = u"Скрывать на разрезе уровни других корпусов"
    hide_cb.IsChecked = bool(values.get(HIDE_OTHER_BUILDINGS_KEY))
    hide_cb.Margin = Thickness(0, 14, 0, 0)
    root.Children.Add(hide_cb)

    open_cb = CheckBox()
    open_cb.Content = u"Открыть разрез после создания"
    open_cb.IsChecked = bool(values.get(OPEN_VIEW_KEY))
    open_cb.Margin = Thickness(0, 14, 0, 0)
    root.Children.Add(open_cb)

    buttons = StackPanel()
    buttons.Orientation = Orientation.Horizontal
    buttons.HorizontalAlignment = HorizontalAlignment.Right
    buttons.Margin = Thickness(0, 16, 0, 0)

    cancel_btn = Button()
    cancel_btn.Content = u"Отмена"
    cancel_btn.Padding = Thickness(10, 4, 10, 4)
    cancel_btn.Margin = Thickness(0, 0, 8, 0)

    ok_btn = Button()
    ok_btn.Content = u"Сохранить"
    ok_btn.Padding = Thickness(10, 4, 10, 4)
    ok_btn.FontWeight = FontWeights.Bold

    def on_ok(sender, args):
        errors = []
        side = _parse_mm(side_box.Text, u"Слева и справа", errors)
        front = _parse_mm(front_box.Text, u"Перед геометрией", errors)
        back = _parse_mm(back_box.Text, u"За геометрией", errors)
        if errors:
            forms.alert(u"\n".join(errors), title=u"Разрез по семейству")
            return

        template = template_cb.SelectedItem
        section_type = type_cb.SelectedItem
        result["values"] = {
            TEMPLATE_KEY: u"" if template in (None, NO_TEMPLATE) else unicode(template),
            TYPE_KEY: u"" if section_type in (None, DEFAULT_TYPE) else unicode(section_type),
            NAME_MASK_KEY: mask_box.Text,
            SIDE_KEY: side,
            FRONT_KEY: front,
            BACK_KEY: back,
            OPEN_VIEW_KEY: bool(open_cb.IsChecked),
            FLIP_KEY: bool(flip_cb.IsChecked),
            HIDE_OTHER_BUILDINGS_KEY: bool(hide_cb.IsChecked),
        }
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
        buttons, _read_all, _write_all, u"разреза по семейству", _on_settings_imported
    )

    root.Children.Add(buttons)

    win.Content = root
    win.ShowDialog()

    return result["values"]


def get_settings_interactive(doc):
    """Окно настроек (Shift+клик); сохраняет и возвращает значения, None — отмена."""
    while True:
        saved = load_saved_values()
        edited = show_settings_form(doc, saved)

        if edited == settings_transfer.RELOAD:
            continue

        if edited is None:
            return None

        save_values(edited)
        return load_saved_values()


def get_settings_silent():
    return load_saved_values()


def ask_run_options(count):
    """
    Окно-вопрос перед построением. count — сколько элементов выбрано.
    Спрашивает:
      - при count > 1: один общий разрез на все элементы или свой на каждый;
      - насколько опустить низ разреза ниже базового уровня, мм.
    Возвращает {COMBINE_KEY: bool, BOTTOM_KEY: float} (и запоминает ответы
    как значения по умолчанию для следующего раза) или None при отмене.
    """
    saved = load_saved_values()
    result = {"values": None}

    win = Window()
    win.Title = u"Разрез по семейству"
    win.Width = 420
    win.SizeToContent = SizeToContent.Height
    win.WindowStartupLocation = WindowStartupLocation.CenterScreen
    win.ResizeMode = ResizeMode.NoResize

    root = StackPanel()
    root.Margin = Thickness(16, 12, 16, 12)

    title = TextBlock()
    title.Text = u"Выбрано элементов: {}".format(count)
    title.FontSize = 14
    title.FontWeight = FontWeights.Bold
    root.Children.Add(title)

    separate_rb = None
    combined_rb = None
    if count > 1:
        _label(root, u"Как строить разрез", bold=True, top=12)
        separate_rb = RadioButton()
        separate_rb.Content = u"Отдельный разрез для каждого элемента"
        separate_rb.GroupName = u"mode"
        separate_rb.Margin = Thickness(0, 4, 0, 0)
        root.Children.Add(separate_rb)

        combined_rb = RadioButton()
        combined_rb.Content = u"Один разрез для всех элементов"
        combined_rb.GroupName = u"mode"
        combined_rb.Margin = Thickness(0, 4, 0, 0)
        root.Children.Add(combined_rb)
        _hint(root, u"Общий разрез: ширина и глубина — по крайним элементам "
                    u"(+ отступы из настроек), направление взгляда — по "
                    u"первому выбранному, низ — самый нижний базовый уровень, "
                    u"верх — следующий этаж над самым верхним.")

        if saved[COMBINE_KEY]:
            combined_rb.IsChecked = True
        else:
            separate_rb.IsChecked = True

    _label(root, u"Низ разреза ниже базового уровня, мм", bold=True, top=12)
    bottom_box = _textbox(root, _fmt_mm(saved[BOTTOM_KEY]))
    _hint(root, u"0 — низ ровно по базовому уровню. Например, 500 — разрез "
                u"захватит 500 мм под уровнем (перекрытие, приямки).")

    buttons = StackPanel()
    buttons.Orientation = Orientation.Horizontal
    buttons.HorizontalAlignment = HorizontalAlignment.Right
    buttons.Margin = Thickness(0, 16, 0, 0)

    cancel_btn = Button()
    cancel_btn.Content = u"Отмена"
    cancel_btn.Padding = Thickness(10, 4, 10, 4)
    cancel_btn.Margin = Thickness(0, 0, 8, 0)
    cancel_btn.IsCancel = True

    ok_btn = Button()
    ok_btn.Content = u"Построить"
    ok_btn.Padding = Thickness(10, 4, 10, 4)
    ok_btn.FontWeight = FontWeights.Bold
    ok_btn.IsDefault = True

    def on_ok(sender, args):
        errors = []
        bottom = _parse_mm(bottom_box.Text, u"Низ разреза ниже уровня", errors)
        if errors:
            forms.alert(u"\n".join(errors), title=u"Разрез по семейству")
            return
        combined = bool(combined_rb.IsChecked) if combined_rb is not None else saved[COMBINE_KEY]
        result["values"] = {COMBINE_KEY: combined, BOTTOM_KEY: bottom}
        win.Close()

    def on_cancel(sender, args):
        win.Close()

    ok_btn.Click += on_ok
    cancel_btn.Click += on_cancel
    buttons.Children.Add(cancel_btn)
    buttons.Children.Add(ok_btn)
    root.Children.Add(buttons)

    win.Content = root
    win.ShowDialog()

    if result["values"] is not None:
        save_values(result["values"])
    return result["values"]
