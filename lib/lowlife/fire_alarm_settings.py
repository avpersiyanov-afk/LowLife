# -*- coding: utf-8 -*-
"""
Окно настроек СПС и СОУЭ + хранение между запусками.

Один модуль на обе системы, но РАЗНЫЕ файлы настроек: у СПС и СОУЭ свои
панели, свои рабочие наборы и свои параметры длин, поэтому каждая система
настраивается независимо. Файл выбирается через set_system() при импорте
в скрипте кнопки:

    from lowlife import fire_alarm_settings
    fire_alarm_settings.set_system("SPS")   # или "SOUE"

Хранится в %APPDATA%\\pyRevit\\LowLifeSPS_settings.json (соотв. SOUE).
"""

import os
import io
import json

import clr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('RevitAPI')

from Autodesk.Revit.DB import ElementId

from pyrevit import forms

from System.Windows import (
    Window, WindowStartupLocation, Thickness,
    FontWeights, HorizontalAlignment, VerticalAlignment, TextWrapping
)
from System.Windows.Controls import (
    StackPanel, TextBlock, TextBox, Button, Orientation, DockPanel, Dock,
    ScrollViewer, ScrollBarVisibility
)
from System.Windows.Media import Brushes

from lowlife.fire_alarm import ISOLATOR_KEYWORD
from lowlife.scs_settings import list_generic_model_symbols, _safe_element_name, TypeOption

SYSTEMS = {
    "SPS": {
        "file": "LowLifeSPS_settings.json",
        "title": u"СПС",
        # Шлейф СПС — цепь пожарной сигнализации, а не слаботочная Data.
        "defaults": {"circuit_system_type": u"FireAlarm"},
    },
    "SOUE": {
        "file": "LowLifeSOUE_settings.json",
        "title": u"СОУЭ",
        # У СОУЭ тип зависит от того, как заведены семейства в проекте:
        # оповещатели бывают и в пожарной цепи, и в силовой. Дефолт —
        # тот же FireAlarm, при необходимости меняется в настройках.
        "defaults": {"circuit_system_type": u"FireAlarm"},
    },
}

_current_system = "SPS"


def set_system(system_key):
    """Выбирает, с какой системой работать: "SPS" или "SOUE"."""
    global _current_system
    if system_key not in SYSTEMS:
        raise ValueError("Unknown system: %s" % system_key)
    _current_system = system_key


def current_title():
    return SYSTEMS[_current_system]["title"]


# (ключ, подпись, значение по умолчанию, список ли через запятую, обязательное)
TEXT_FIELDS = [
    # --- поиск панели и устройств ---
    ("workset_param_name", u"[Оборудование] Параметр рабочего набора элемента",
        u"Рабочий набор", False, True),
    ("workset_filter_key", u"[Оборудование] Ключевое слово рабочего набора",
        u"", False, True),
    ("designation_param", u"[Оборудование] Параметр «Обозначение» (у панели и устройств)",
        u"", False, True),
    ("device_address_param", u"[Оборудование] Параметр «Адрес устройства» (панель: «3», устройство: «3.1.2»)",
        u"", False, True),
    ("panel_designation_key", u"[Оборудование] Обозначение панели (например ARK)",
        u"", False, True),
    ("excluded_device_keywords", u"[Оборудование] Ключевые слова исключаемых устройств (через запятую)",
        u"", True, False),
    ("isolator_keyword", u"[Оборудование] Ключевое слово изолятора/ответвителя в имени семейства",
        ISOLATOR_KEYWORD, False, False),

    # --- цепи ---
    ("circuit_panel_param", u"[Цепи] Параметр цепи «Панель»",
        u"", False, True),
    ("circuit_number_param", u"[Цепи] Параметр цепи «Номер цепи»",
        u"", False, True),
    ("circuit_number_format", u"[Цепи] Формат номера цепи (используйте {} для номера шлейфа)",
        u"ШС-{}", False, True),
    ("circuit_system_type", u"[Цепи] Тип электрической цепи Revit (FireAlarm, Data, Communication, Security, Power)",
        u"FireAlarm", False, True),
    ("load_name_param", u"[Цепи] Параметр цепи «Имя нагрузки»",
        u"", False, True),
    ("cable_type_param", u"[Цепи] Параметр цепи «Проводник» (тип кабеля)",
        u"", False, False),
    ("device_cable_map_text", u"[Цепи] Словарь «тип устройства : тип кабеля» (по одному на строку, ключ:значение)",
        u"", False, False),

    # --- длины ---
    ("length_coef", u"[Длины] Коэффициент запаса длины",
        u"1.10", False, True),
    ("wire_length_param", u"[Длины] Параметр цепи «Длина проводника»",
        u"", False, True),
    ("pipe_length_param", u"[Длины] Параметр цепи «Длина проводника в трубе»",
        u"", False, False),
    ("tray_length_param", u"[Длины] Параметр цепи «Длина проводника в лотке»",
        u"", False, False),
    ("route_method_param", u"[Длины] Параметр цепи «Способ прокладки»",
        u"", False, False),
    ("route_label_pipe_format", u"[Длины] Формат метки трубы (используйте {} для метров)",
        u"", False, False),
    ("circuit_route_param", u"[Длины] Параметр цепи «Маршрут цепи»",
        u"", False, False),

    # --- маркировка ---
    ("device_marking_param", u"[Маркировка] Параметр «Марка устройства»",
        u"", False, False),
    ("addr_prev_param_name", u"[Маркировка] Параметр устройства «Предыдущий адрес»",
        u"", False, False),
]

TYPE_FIELDS = []

LIST_FIELDS = set(key for key, _, _, is_list, _req in TEXT_FIELDS if is_list)
MULTILINE_FIELDS = set(["device_cable_map_text"])


def _split_section(label_text):
    if label_text.startswith(u"[") and u"]" in label_text:
        end = label_text.index(u"]")
        return label_text[1:end], label_text[end + 1:].strip()
    return None, label_text


PLAIN_LABELS = {}
for _key, _label, _default, _is_list, _required in TEXT_FIELDS:
    PLAIN_LABELS[_key] = _split_section(_label)[1]


def _settings_file_path():
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    folder = os.path.join(appdata, "pyRevit")

    if not os.path.isdir(folder):
        try:
            os.makedirs(folder)
        except:
            pass

    return os.path.join(folder, SYSTEMS[_current_system]["file"])


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
        forms.alert(u"Не удалось сохранить настройки {} в файл:\n{}".format(current_title(), path))


def load_saved_values():
    saved = _read_all()
    system_defaults = SYSTEMS[_current_system].get("defaults", {})
    values = {}

    for key, _, default, _, _ in TEXT_FIELDS:
        # Дефолт может отличаться между системами (например тип цепи),
        # поэтому пер-системное значение перекрывает общее из TEXT_FIELDS.
        values[key] = saved.get(key, system_defaults.get(key, default))

    return values


def save_values(values):
    data = _read_all()
    data.update(values)
    _write_all(data)


def _split_list(text):
    return [x.strip() for x in text.split(",") if x.strip()]


def to_runtime_settings(values):
    settings = dict(values)
    for key in LIST_FIELDS:
        settings[key] = _split_list(values[key])
    return settings


def require(settings, keys):
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
            u"В настройках {} не заполнены обязательные для этой кнопки поля:\n\n{}\n\n"
            u"Запустите кнопку «Параметры {}» и заполните их там.".format(
                current_title(), u"\n".join(missing), current_title()
            ),
            exitscript=True
        )


def show_settings_form(doc, values):
    result = {"values": None}

    win = Window()
    win.Title = u"Настройки {}".format(current_title())
    win.Width = 600
    win.Height = 720
    win.WindowStartupLocation = WindowStartupLocation.CenterScreen
    # Topmost не ставим — см. комментарий в scs_settings.py.

    outer = DockPanel()
    outer.LastChildFill = True

    root = StackPanel()
    root.Margin = Thickness(16)

    title = TextBlock()
    title.Text = u"Настройки параметров {}".format(current_title())
    title.FontSize = 16
    title.FontWeight = FontWeights.Bold
    title.Margin = Thickness(0, 0, 0, 4)
    root.Children.Add(title)

    hint = TextBlock()
    hint.Text = (
        u"Адресация: у панели «Обозначение» = ARK и «Адрес устройства» = 3; "
        u"у устройства «Адрес устройства» = 3.1.2 (панель 3, шлейф 1, номер 2)."
    )
    hint.FontSize = 11
    hint.Foreground = Brushes.Gray
    hint.TextWrapping = TextWrapping.Wrap
    hint.Margin = Thickness(0, 0, 0, 10)
    root.Children.Add(hint)

    boxes = {}
    current_section = None

    for key, label_text, _, _, required in TEXT_FIELDS:
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

        if key in MULTILINE_FIELDS:
            box.AcceptsReturn = True
            box.TextWrapping = TextWrapping.Wrap
            box.Height = 80
            box.VerticalScrollBarVisibility = ScrollBarVisibility.Auto

        root.Children.Add(box)
        boxes[key] = box

    required_hint = TextBlock()
    required_hint.Text = u"* обязательные поля"
    required_hint.FontSize = 11
    required_hint.Foreground = Brushes.Gray
    required_hint.Margin = Thickness(0, 10, 0, 0)
    root.Children.Add(required_hint)

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
    ok_btn.Content = u"Сохранить"
    ok_btn.Padding = Thickness(10, 4, 10, 4)
    ok_btn.FontWeight = FontWeights.Bold

    def on_reset(sender, args):
        system_defaults = SYSTEMS[_current_system].get("defaults", {})
        for key, _, default, _, _ in TEXT_FIELDS:
            boxes[key].Text = system_defaults.get(key, default)

    def on_ok(sender, args):
        result["values"] = {key: box.Text for key, box in boxes.items()}
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
    saved = load_saved_values()
    edited = show_settings_form(doc, saved)

    if edited is None:
        return None

    save_values(edited)
    return to_runtime_settings(edited)


def get_settings_silent():
    return to_runtime_settings(load_saved_values())
