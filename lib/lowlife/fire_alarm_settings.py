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
from lowlife.fire_alarm_circuits import DEVICE_CATEGORIES, category_title
from lowlife.scs_settings import (
    list_generic_model_symbols, _safe_element_name, TypeOption,
    list_wire_catalog_items, WireTypeOption, _type_display_name
)

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
    ("wire_catalog_marker_param", u"[Цепи] Параметр-признак строки справочника кабелей "
        u"(нужен для подбора типа проводника по категории устройства ниже)",
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

# {int(BuiltInCategory): "id_строки_справочника_кабелей"} — тип проводника
# по категории устройства (DEVICE_CATEGORIES), отдельный ключ в JSON
# настроек системы, не в TEXT_FIELDS (выбирается пикером, не текстом).
CATEGORY_WIRE_TYPES_KEY = "category_wire_type_ids"

LIST_FIELDS = set(key for key, _, _, is_list, _req in TEXT_FIELDS if is_list)
MULTILINE_FIELDS = set()


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


def load_category_wire_type_ids():
    """{int(BuiltInCategory): "id_строки_справочника_кабелей"}."""
    saved = _read_all()
    raw = saved.get(CATEGORY_WIRE_TYPES_KEY, {})
    result = {}
    for key, value in raw.items():
        try:
            result[int(key)] = value
        except:
            continue
    return result


def save_category_wire_type_ids(wire_type_ids):
    data = _read_all()
    # Ключи JSON всегда строки — приводим при записи, load обратно приводит к int.
    data[CATEGORY_WIRE_TYPES_KEY] = dict((str(k), v) for k, v in wire_type_ids.items())
    _write_all(data)


def get_category_wire_type_elem_ids(doc):
    """
    {int(BuiltInCategory): ElementId} для категорий DEVICE_CATEGORIES, у
    которых в настройках выбран существующий в проекте тип проводника
    (строка справочника кабелей — см. scs_settings.list_wire_catalog_items).
    Категории без выбранного/валидного значения в словарь не попадают.
    """
    wire_type_ids = load_category_wire_type_ids()
    result = {}

    for cat in DEVICE_CATEGORIES:
        id_str = wire_type_ids.get(int(cat))
        if not id_str:
            continue
        try:
            element_id = ElementId(int(id_str))
        except:
            continue
        if doc.GetElement(element_id) is not None:
            result[int(cat)] = element_id

    return result


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

    # --- тип проводника по категории устройства (для параметра «Проводник») ---

    category_section_title = TextBlock()
    category_section_title.Text = u"Типы проводника по категории устройства"
    category_section_title.FontWeight = FontWeights.Bold
    category_section_title.Margin = Thickness(0, 16, 0, 4)
    root.Children.Add(category_section_title)

    category_hint = TextBlock()
    category_hint.Text = (
        u"Опционально: если задан параметр цепи «Проводник» выше, для каждой "
        u"категории устройств можно выбрать тип кабеля из справочника — "
        u"он будет проставлен цепи шлейфа по категории первого устройства."
    )
    category_hint.FontSize = 11
    category_hint.Foreground = Brushes.Gray
    category_hint.TextWrapping = TextWrapping.Wrap
    category_hint.Margin = Thickness(0, 0, 0, 8)
    root.Children.Add(category_hint)

    category_wire_type_ids = load_category_wire_type_ids()
    category_wire_labels = {}

    for cat in DEVICE_CATEGORIES:
        cat_key = int(cat)

        row = StackPanel()
        row.Orientation = Orientation.Horizontal
        row.Margin = Thickness(0, 4, 0, 0)

        name_label = TextBlock()
        name_label.Text = category_title(cat)
        name_label.VerticalAlignment = VerticalAlignment.Center
        name_label.Width = 220
        name_label.TextWrapping = TextWrapping.Wrap
        row.Children.Add(name_label)

        wire_value_label = TextBlock()
        wire_value_label.Text = _type_display_name(doc, category_wire_type_ids.get(cat_key, ""))
        wire_value_label.VerticalAlignment = VerticalAlignment.Center
        wire_value_label.Width = 220
        wire_value_label.TextWrapping = TextWrapping.Wrap
        category_wire_labels[cat_key] = wire_value_label
        row.Children.Add(wire_value_label)

        pick_btn = Button()
        pick_btn.Content = u"Выбрать..."
        pick_btn.Padding = Thickness(8, 2, 8, 2)
        pick_btn.Margin = Thickness(8, 0, 0, 0)

        def on_pick_wire(sender, args, cat_key=cat_key, cat_title=category_title(cat)):
            marker_param_name = boxes["wire_catalog_marker_param"].Text.strip()
            if not marker_param_name:
                forms.alert(
                    u"Сначала заполните поле «Параметр-признак строки справочника "
                    u"кабелей» в разделе «Цепи»."
                )
                return

            wire_items = list_wire_catalog_items(doc, marker_param_name)
            if not wire_items:
                forms.alert(
                    u"Не найдено строк справочника кабелей (ни один элемент документа "
                    u"не содержит одновременно «Ключевое имя» и параметр «{}»).".format(
                        marker_param_name
                    )
                )
                return

            options = sorted([WireTypeOption(w) for w in wire_items], key=lambda o: o.name)
            selected = forms.SelectFromList.show(
                options,
                title=u"Тип проводника для категории «{}»".format(cat_title),
                button_name=u"Выбрать",
                multiselect=False
            )

            if selected:
                category_wire_type_ids[cat_key] = str(selected.wire_type.Id.IntegerValue)
                category_wire_labels[cat_key].Text = selected.name

        pick_btn.Click += on_pick_wire
        row.Children.Add(pick_btn)

        root.Children.Add(row)

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
        save_category_wire_type_ids(category_wire_type_ids)
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
