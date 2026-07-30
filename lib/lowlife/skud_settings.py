# -*- coding: utf-8 -*-
"""
Окно настроек параметров СКУД + их хранение между запусками.

Хранится в отдельном JSON-файле %APPDATA%\\pyRevit\\LowLifeSKUD_settings.json
(тот же подход, что scs_settings.py, но независимо — СКУД не должна зависеть
от того, настроена ли СКС в этом же проекте, и наоборот).

Значения общие для всех кнопок SKUD.panel.
"""

import os
import io
import json

import clr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('RevitAPI')

from Autodesk.Revit.DB import ElementId, Element

from pyrevit import forms

from System.Windows import (
    Window, WindowStartupLocation, Thickness,
    FontWeights, HorizontalAlignment, VerticalAlignment, TextWrapping
)
from System.Windows.Controls import (
    StackPanel, TextBlock, TextBox, Button, Orientation, DockPanel, Dock, ScrollViewer,
    ScrollBarVisibility
)
from System.Windows.Media import Brushes

from lowlife import skud as skud_defaults
from lowlife.scs_settings import list_generic_model_symbols, _safe_element_name, TypeOption

SETTINGS_FILE_NAME = "LowLifeSKUD_settings.json"

# (ключ, подпись в окне, значение по умолчанию, список ли это через запятую,
#  обязательное ли поле, многострочное ли поле)
TEXT_FIELDS = [
    # --- контроллеры и цепи (AssignCircuitsAndCables) ---
    ("controller_workset_keyword", u"[Контроллеры] Ключевое слово рабочего набора контроллеров",
        skud_defaults.CONTROLLER_WORKSET_KEYWORD, False, True, False),
    ("controller_type_keyword", u"[Контроллеры] Ключевое слово в имени типа контроллера",
        skud_defaults.CONTROLLER_TYPE_KEYWORD, False, True, False),
    ("workset_param_name", u"[Контроллеры] Параметр рабочего набора элемента",
        u"Рабочий набор", False, True, False),
    ("excluded_device_keywords", u"[Контроллеры] Ключевые слова резервных портов, исключаемых из расчёта (через запятую)",
        u"", True, False, False),
    ("circuit_panel_param", u"[Контроллеры] Параметр цепи «Панель» (контроллер)",
        u"", False, True, False),
    ("circuit_name_type_param", u"[Контроллеры] Параметр цепи «Наименование»",
        u"", False, False, False),
    ("device_address_param", u"[Контроллеры] Параметр устройства «Адрес устройства»",
        u"", False, True, False),
    ("type_code_param", u"[Контроллеры] Параметр типа устройства «Обозначение»",
        u"", False, True, False),
    ("load_name_param", u"[Контроллеры] Параметр цепи «Имя нагрузки»",
        u"", False, True, False),
    ("controller_marking_param", u"[Контроллеры] Параметр «Маркировка контроллера»",
        u"", False, True, False),
    ("cable_type_param", u"[Контроллеры] Параметр цепи «Проводник» (тип кабеля)",
        u"", False, True, False),
    ("device_cable_map_text", u"[Контроллеры] Словарь «тип устройства : тип кабеля» (по одному на строку, формат ключ:значение)",
        u"", False, True, True),

    # --- адресация узлов трассы (тот же граф, что и СКС, свой набор типов) ---
    ("addr_param_name", u"[Адресация] Параметр «Адрес узла»",
        u"", False, True, False),
    ("addr_prev_param_name", u"[Адресация] Параметр «Предыдущий адрес»",
        u"", False, True, False),
    ("nearest_segment_param", u"[Адресация] Параметр «Ближайший узел маршрута»",
        u"", False, True, False),
    ("cable_param_name", u"[Адресация] Параметр «Тип прокладки кабеля» (узлы трассы)",
        u"", False, True, False),

    # --- длины (CalcSkudLengths) ---
    ("near_controller_threshold_m", u"[Длины] Порог «рядом с контроллером», м",
        u"3", False, True, False),
    ("hypotenuse_coef", u"[Длины] Коэффициент запаса для расчёта по катетам",
        u"1.10", False, True, False),
    ("horiz_tray_coef", u"[Длины] Коэффициент запаса длины в лотке",
        u"1.10", False, True, False),
    ("horiz_pipe_coef", u"[Длины] Коэффициент запаса длины в трубе (горизонталь)",
        u"1.15", False, True, False),
    ("vertical_coef", u"[Длины] Коэффициент запаса длины по вертикали",
        u"1.10", False, True, False),
    ("install_tray_key", u"[Длины] Значение «Тип прокладки» = лоток",
        u"Лоток", False, True, False),
    ("install_pipe_key", u"[Длины] Значение «Тип прокладки» = труба",
        u"Труба", False, True, False),
    ("install_pipe_open_key", u"[Длины] Значение «Тип прокладки» = труба открыто",
        u"Труба открыто", False, True, False),
    ("wire_length_param", u"[Длины] Параметр цепи «Длина проводника»",
        u"", False, True, False),
    ("tray_length_param", u"[Длины] Параметр цепи «Длина проводника в лотке»",
        u"", False, True, False),
    ("pipe_length_param", u"[Длины] Параметр цепи «Длина проводника в трубе»",
        u"", False, True, False),
    ("route_method_param", u"[Длины] Параметр цепи «Способ прокладки»",
        u"", False, True, False),
    ("circuit_route_param", u"[Длины] Параметр цепи «Маршрут цепи»",
        u"", False, True, False),
    ("route_label_pipe_format", u"[Длины] Формат метки трубы (используйте {} для метров)",
        u"", False, True, False),
    ("route_label_tray_format", u"[Длины] Формат метки лотка (используйте {} для метров)",
        u"", False, True, False),

    # --- маркировка (CalcSkudLengths, вместе с длинами) ---
    ("device_marking_param", u"[Маркировка] Параметр «Марка устройства»",
        u"", False, True, False),
    ("segment_loads_param", u"[Маркировка] Параметр узла маршрута «Список цепей»",
        u"", False, True, False),

    # --- структурная схема (BuildSkudSchematic) ---
    ("schematic_template_group_name", u"[Схема] Имя типовой группы-эталона",
        u"", False, True, False),
    ("schematic_address_param", u"[Схема] Параметр адреса на схемном семействе",
        u"", False, True, False),
    ("schematic_layout_gap_m", u"[Схема] Отступ между узлами схемы при автораскладке, м",
        u"5", False, True, False),
    ("schematic_layout_per_row", u"[Схема] Число узлов схемы в ряду при автораскладке",
        u"5", False, True, False),
    ("schematic_device_categories_text", u"[Схема] Категории устройств для сопоставления схема-модель (по одной на строку, формат имя:ключевые_слова через запятую)",
        u"", False, True, True),
]

# (ключ, подпись) — типы, выбираемые из проекта (категория "Обобщённые модели")
TYPE_FIELDS = [
    ("route_type_id", u"Тип для узлов маршрута СКУД"),
    ("riser_type_id", u"Тип для точек стояков СКУД"),
]

LIST_FIELDS = set(key for key, _, _, is_list, _req, _multiline in TEXT_FIELDS if is_list)
MULTILINE_FIELDS = set(key for key, _, _, _is_list, _req, multiline in TEXT_FIELDS if multiline)


def _split_section(label_text):
    """"[Раздел] Подпись" -> ("Раздел", "Подпись"); просто "Подпись" -> (None, "Подпись")."""
    if label_text.startswith(u"[") and u"]" in label_text:
        end = label_text.index(u"]")
        return label_text[1:end], label_text[end + 1:].strip()
    return None, label_text


PLAIN_LABELS = {}
for _key, _label, _default, _is_list, _required, _multiline in TEXT_FIELDS:
    PLAIN_LABELS[_key] = _split_section(_label)[1]
for _key, _label in TYPE_FIELDS:
    PLAIN_LABELS[_key] = _split_section(_label)[1]


def _type_display_name(doc, id_str):
    if not id_str:
        return u"(не выбран)"

    try:
        el = doc.GetElement(ElementId(int(id_str)))
    except:
        return u"(не выбран)"

    if el is None:
        return u"(не выбран)"

    fam_name = None
    try:
        fam_name = _safe_element_name(el.Family)
    except:
        pass

    type_name = _safe_element_name(el)

    if fam_name and type_name:
        return u"{} : {}".format(fam_name, type_name)

    return type_name or id_str


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
            u"Не удалось сохранить настройки СКУД в файл:\n{}".format(path)
        )


def load_saved_values():
    """Строковые значения настроек: из JSON-файла, иначе — значения по умолчанию."""
    saved = _read_all()
    values = {}

    for key, _, default, _, _, _ in TEXT_FIELDS:
        values[key] = saved.get(key, default)

    for key, _ in TYPE_FIELDS:
        values[key] = saved.get(key, "")

    return values


def save_values(values):
    data = _read_all()
    data.update(values)
    _write_all(data)


def _split_list(text):
    return [x.strip() for x in text.split(",") if x.strip()]


def to_runtime_settings(values):
    """Преобразует строковые значения формы в типы, готовые для skud.py (id типов остаются строками)."""
    settings = dict(values)
    for key in LIST_FIELDS:
        settings[key] = _split_list(values[key])
    return settings


def require(settings, keys):
    """
    Проверяет, что перечисленные ключи заполнены в settings (после
    to_runtime_settings). Останавливает скрипт через forms.alert(exitscript=True),
    если чего-то не хватает.
    """
    missing = []

    for key in keys:
        value = settings.get(key)

        if isinstance(value, list):
            ok = len(value) > 0
        else:
            ok = bool(value and str(value).strip())

        if not ok:
            missing.append(PLAIN_LABELS.get(key, key))

    if missing:
        forms.alert(
            u"В настройках СКУД не заполнены обязательные для этой кнопки поля:\n\n{}\n\n"
            u"Запустите кнопку «Параметры СКУД» и заполните их там.".format(u"\n".join(missing)),
            exitscript=True
        )


def show_settings_form(doc, values):
    """
    Модальное окно редактирования настроек СКУД: выбор типов для вставки
    (узел маршрута/стояк) + текстовые параметры.
    Возвращает словарь строковых значений или None, если пользователь отменил.
    """
    result = {"values": None}

    win = Window()
    win.Title = u"Настройки СКУД"
    win.Width = 600
    win.Height = 760
    win.WindowStartupLocation = WindowStartupLocation.CenterScreen
    # Topmost намеренно НЕ ставим — см. комментарий в scs_settings.py
    # (иначе окно выбора типа/SelectFromList открывается позади).

    outer = DockPanel()
    outer.LastChildFill = True

    root = StackPanel()
    root.Margin = Thickness(16)

    title = TextBlock()
    title.Text = u"Настройки параметров СКУД"
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

    # --- типы для вставки ---

    type_values = {key: values.get(key, "") for key, _ in TYPE_FIELDS}
    type_labels = {}

    type_current_section = [None]

    def make_type_picker(key, label_text):
        section, plain_label = _split_section(label_text)

        if section != type_current_section[0]:
            type_current_section[0] = section
            section_title = TextBlock()
            section_title.Text = section if section else u"Типы для вставки"
            section_title.FontWeight = FontWeights.Bold
            section_title.Margin = Thickness(0, 16, 0, 4)
            root.Children.Add(section_title)

        label = TextBlock()
        label.Text = plain_label
        label.Margin = Thickness(0, 8, 0, 2)
        root.Children.Add(label)

        row = StackPanel()
        row.Orientation = Orientation.Horizontal

        value_label = TextBlock()
        value_label.Text = _type_display_name(doc, type_values[key])
        value_label.VerticalAlignment = VerticalAlignment.Center
        value_label.Width = 300
        value_label.TextWrapping = TextWrapping.Wrap
        type_labels[key] = value_label

        pick_btn = Button()
        pick_btn.Content = u"Выбрать..."
        pick_btn.Padding = Thickness(8, 2, 8, 2)
        pick_btn.Margin = Thickness(8, 0, 0, 0)

        def on_pick(sender, args, key=key, label_text=label_text):
            symbols = list_generic_model_symbols(doc)
            if not symbols:
                forms.alert(u"В проекте нет типов категории «Обобщённые модели».")
                return

            options = sorted([TypeOption(s) for s in symbols], key=lambda o: o.name)
            selected = forms.SelectFromList.show(
                options,
                title=plain_label,
                button_name=u"Выбрать",
                multiselect=False
            )

            if selected:
                type_values[key] = str(selected.symbol.Id.IntegerValue)
                type_labels[key].Text = selected.name

        pick_btn.Click += on_pick

        row.Children.Add(value_label)
        row.Children.Add(pick_btn)
        root.Children.Add(row)

    for key, label_text in TYPE_FIELDS:
        make_type_picker(key, label_text)

    # --- текстовые параметры (сгруппированы по разделу через префикс "[Раздел]") ---

    boxes = {}
    current_section = None

    for key, label_text, _, _, required, multiline in TEXT_FIELDS:
        section, plain_label = _split_section(label_text)

        if section != current_section:
            current_section = section
            section_title = TextBlock()
            section_title.Text = section if section else u"Параметры"
            section_title.FontWeight = FontWeights.Bold
            section_title.Margin = Thickness(0, 16, 0, 4)
            root.Children.Add(section_title)

        label = TextBlock()
        label.Text = plain_label + (u" *" if required else u"")
        label.Margin = Thickness(0, 8, 0, 2)
        label.TextWrapping = TextWrapping.Wrap
        root.Children.Add(label)

        box = TextBox()
        box.Text = values.get(key, "")
        box.Padding = Thickness(4)

        if multiline:
            box.AcceptsReturn = True
            box.TextWrapping = TextWrapping.Wrap
            box.Height = 80
            box.VerticalScrollBarVisibility = ScrollBarVisibility.Auto

        root.Children.Add(box)
        boxes[key] = box

    required_hint = TextBlock()
    required_hint.Text = u"* обязательные поля — без них соответствующая кнопка не сможет найти элементы или записать параметры"
    required_hint.FontSize = 11
    required_hint.Foreground = Brushes.Gray
    required_hint.TextWrapping = TextWrapping.Wrap
    required_hint.Margin = Thickness(0, 10, 0, 0)
    root.Children.Add(required_hint)

    # --- кнопки (закреплены внизу окна, вне прокручиваемой области) ---

    buttons = StackPanel()
    buttons.Orientation = Orientation.Horizontal
    buttons.HorizontalAlignment = HorizontalAlignment.Right
    buttons.Margin = Thickness(16, 8, 16, 12)
    DockPanel.SetDock(buttons, Dock.Bottom)

    reset_btn = Button()
    reset_btn.Content = u"Сбросить параметры"
    reset_btn.Padding = Thickness(10, 4, 10, 4)
    reset_btn.Margin = Thickness(0, 0, 8, 0)

    cancel_btn = Button()
    cancel_btn.Content = u"Отмена"
    cancel_btn.Padding = Thickness(10, 4, 10, 4)
    cancel_btn.Margin = Thickness(0, 0, 8, 0)

    ok_btn = Button()
    ok_btn.Content = u"Сохранить и запустить"
    ok_btn.Padding = Thickness(10, 4, 10, 4)
    ok_btn.FontWeight = FontWeights.Bold

    def on_reset(sender, args):
        for key, _, default, _, _, _ in TEXT_FIELDS:
            boxes[key].Text = default

    def on_ok(sender, args):
        combined = {key: box.Text for key, box in boxes.items()}
        combined.update(type_values)
        result["values"] = combined
        win.Close()

    def on_cancel(sender, args):
        win.Close()

    reset_btn.Click += on_reset
    ok_btn.Click += on_ok
    cancel_btn.Click += on_cancel

    buttons.Children.Add(reset_btn)
    buttons.Children.Add(cancel_btn)
    buttons.Children.Add(ok_btn)

    scroll = ScrollViewer()
    scroll.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
    scroll.Content = root

    outer.Children.Add(buttons)
    outer.Children.Add(scroll)

    win.Content = outer
    win.ShowDialog()

    return result["values"]


def get_settings_interactive(doc):
    """
    Показывает окно настроек, сохраняет введённые значения и возвращает
    готовый к использованию словарь. Возвращает None, если пользователь
    нажал "Отмена". Используется только кнопкой «Параметры СКУД».
    """
    saved = load_saved_values()
    edited = show_settings_form(doc, saved)

    if edited is None:
        return None

    save_values(edited)
    return to_runtime_settings(edited)


def get_settings_silent():
    """
    Настройки без показа окна — уже сохранённые значения (или значения по
    умолчанию из skud.py). Используется рабочими кнопками СКУД.
    """
    return to_runtime_settings(load_saved_values())
