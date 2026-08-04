# -*- coding: utf-8 -*-
"""
Окно настроек параметров СКС + их хранение между запусками.

Хранится в обычном JSON-файле в %APPDATA%\\pyRevit\\LowLifeSCS_settings.json
(см. _settings_file_path) — простой и однозначно проверяемый способ,
без зависимости от внутреннего API pyrevit.script.get_config()/save_config()
(на практике не гарантированно расшаривавшего секцию между разными
script.py одного расширения).

Значения общие для всех кнопок SCS.panel — сохраняются в одном файле,
поэтому достаточно настроить один раз.
"""

import os
import io
import json

import clr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('RevitAPI')

from Autodesk.Revit.DB import ElementId, FilteredElementCollector, Family, BuiltInCategory, Element

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

from lowlife import scs as scs_defaults

SETTINGS_FILE_NAME = "LowLifeSCS_settings.json"

# (ключ, подпись в окне, значение по умолчанию, список ли это через запятую, обязательное ли поле)
TEXT_FIELDS = [
    ("family_filter", u"Фильтр семейства сегментов трассы",
        scs_defaults.FAMILY_FILTER, False, True),
    ("cable_param_name", u"Параметр «Тип прокладки кабеля»",
        scs_defaults.CABLE_PARAM_NAME, False, True),
    ("route_param_name", u"Параметр «Тип трассы»",
        scs_defaults.ROUTE_PARAM_NAME, False, True),
    ("route_param_value", u"Значение параметра «Тип трассы» (не для стояков)",
        scs_defaults.ROUTE_PARAM_VALUE, False, True),
    ("route_param_value_riser", u"Значение параметра «Тип трассы» для стояков",
        scs_defaults.ROUTE_PARAM_VALUE_RISER, False, True),
    ("device_cable_type_value", u"Тип прокладки кабеля для панелей и стояков",
        scs_defaults.DEVICE_CABLE_TYPE_VALUE, False, True),
    ("panel_keywords", u"Ключевые слова панелей (через запятую)",
        u", ".join(scs_defaults.PANEL_KEYWORDS), True, False),
    ("panel_exclude_keywords", u"Слова-исключения панелей (через запятую)",
        u", ".join(scs_defaults.PANEL_EXCLUDE_KEYWORDS), True, False),
    ("riser_keywords", u"Ключевые слова стояков (через запятую)",
        u", ".join(scs_defaults.RISER_KEYWORDS), True, False),
    ("riser_exclude_keywords", u"Слова-исключения стояков (через запятую)",
        u", ".join(scs_defaults.RISER_EXCLUDE_KEYWORDS), True, False),
    ("riser_annotation_keywords", u"Ключевые слова аннотации стояка (через запятую)",
        u", ".join(scs_defaults.RISER_ANNOTATION_KEYWORDS), True, False),
    ("offset_param_names", u"Возможные имена параметра отметки (через запятую)",
        u", ".join(scs_defaults.OFFSET_PARAM_NAMES), True, True),

    # --- адресация узлов (RenumberAddresses) ---
    ("addr_param_name", u"[Адресация] Параметр «Адрес узла»",
        u"", False, True),
    ("addr_prev_param_name", u"[Адресация] Параметр «Предыдущий адрес»",
        u"", False, True),

    # --- расчёт цепей и длин (SyncCircuitsAndLengths) ---
    ("workset_param_name", u"[Цепи] Параметр рабочего набора элемента",
        u"Рабочий набор", False, True),
    ("workset_filter_key", u"[Цепи] Ключевое слово рабочего набора целевых панелей",
        u"", False, True),
    ("excluded_device_keywords", u"[Цепи] Ключевые слова резервных портов, исключаемых из расчёта (через запятую)",
        u"", True, False),
    ("circuit_panel_param", u"[Цепи] Параметр цепи «Панель»",
        u"", False, True),
    ("nearest_segment_param", u"[Цепи] Параметр «Ближайший узел маршрута» (у панелей и устройств)",
        u"", False, True),
    ("device_address_param", u"[Цепи] Параметр устройства «Адрес устройства»",
        u"", False, True),
    ("type_code_param", u"[Цепи] Параметр типа устройства «Обозначение»",
        u"", False, True),
    ("circuit_name_type_param", u"[Цепи] Параметр цепи «Наименование» (для определения типа цепи)",
        u"", False, True),
    ("circuit_number_param", u"[Цепи] Параметр цепи «Номер цепи»",
        u"", False, True),
    ("circuit_route_param", u"[Цепи] Параметр цепи «Маршрут цепи»",
        u"", False, True),
    ("wire_length_param", u"[Цепи] Параметр цепи «Длина проводника»",
        u"", False, True),
    ("tray_length_param", u"[Цепи] Параметр цепи «Длина проводника в лотке»",
        u"", False, True),
    ("pipe_length_param", u"[Цепи] Параметр цепи «Длина проводника в трубе»",
        u"", False, True),
    ("route_method_param", u"[Цепи] Параметр цепи «Способ прокладки»",
        u"", False, True),
    ("load_name_param", u"[Цепи] Параметр цепи «Имя нагрузки»",
        u"", False, True),
    ("segment_loads_param", u"[Цепи] Параметр узла маршрута «Список цепей»",
        u"", False, True),
    ("install_tray_key", u"[Цепи] Значение «Тип прокладки» = лоток",
        u"Лоток", False, True),
    ("install_pipe_key", u"[Цепи] Значение «Тип прокладки» = труба",
        u"Труба", False, True),
    ("install_pipe_open_key", u"[Цепи] Значение «Тип прокладки» = труба открыто",
        u"Труба открыто", False, True),
    ("route_label_pipe_format", u"[Цепи] Формат метки трубы (используйте {} для метров)",
        u"", False, True),
    ("route_label_tray_format", u"[Цепи] Формат метки лотка (используйте {} для метров)",
        u"", False, True),
    ("route_label_pipe_open_format", u"[Цепи] Формат метки трубы открыто (используйте {} для метров)",
        u"", False, True),
    ("circuit_key_fo", u"[Цепи] Ключевое слово типа цепи «оптическая»",
        u"оптический", False, True),
    ("circuit_key_utp", u"[Цепи] Ключевое слово типа цепи «UTP/витая пара»",
        u"парной скрутки", False, True),
    ("circuit_key_power", u"[Цепи] Ключевое слово типа цепи «силовая»",
        u"силовой", False, True),
    ("horiz_tray_coef", u"[Цепи] Коэффициент запаса длины в лотке",
        u"1.10", False, True),
    ("horiz_pipe_coef", u"[Цепи] Коэффициент запаса длины в трубе (горизонталь)",
        u"1.15", False, True),
    ("vertical_coef", u"[Цепи] Коэффициент запаса длины по вертикали",
        u"1.10", False, True),
]

# (ключ, подпись) — типы, выбираемые из проекта (категория "Обобщённые модели")
TYPE_FIELDS = [
    ("panel_type_id", u"Тип для точек панелей"),
    ("route_type_id", u"Тип для узлов маршрута"),
    ("riser_type_id", u"Тип для точек стояков"),
]

LIST_FIELDS = set(key for key, _, _, is_list, _req in TEXT_FIELDS if is_list)


def _split_section(label_text):
    """"[Раздел] Подпись" -> ("Раздел", "Подпись"); просто "Подпись" -> (None, "Подпись")."""
    if label_text.startswith(u"[") and u"]" in label_text:
        end = label_text.index(u"]")
        return label_text[1:end], label_text[end + 1:].strip()
    return None, label_text


# Подписи без префикса "[Раздел]" — используются в сообщениях об отсутствующих полях
PLAIN_LABELS = {}
for _key, _label, _default, _is_list, _required in TEXT_FIELDS:
    PLAIN_LABELS[_key] = _split_section(_label)[1]
for _key, _label in TYPE_FIELDS:
    PLAIN_LABELS[_key] = _split_section(_label)[1]


def _safe_element_name(el):
    """
    Имя элемента через Element.Name.GetValue(el) — прямой доступ el.Name
    в IronPython у некоторых типов Revit-элементов (в т.ч. FamilySymbol)
    падает с ошибкой неоднозначного связывания и незаметно уходит в
    except, поэтому используем статическое свойство через рефлексию.
    """
    try:
        return Element.Name.GetValue(el)
    except:
        try:
            return el.Name
        except:
            return None


class TypeOption(object):
    """Обёртка над FamilySymbol для отображения в списке выбора."""

    def __init__(self, symbol):
        self.symbol = symbol

        fam_name = None
        try:
            fam_name = _safe_element_name(symbol.Family)
        except:
            pass

        type_name = _safe_element_name(symbol)

        self.name = u"{} : {}".format(
            fam_name or u"?",
            type_name or str(symbol.Id.IntegerValue)
        )

    def __str__(self):
        return self.name


def list_generic_model_symbols(doc):
    """
    Все загруженные в проект типоразмеры категории «Обобщённые модели» —
    включая те, у которых ещё нет ни одного вставленного экземпляра.

    FilteredElementCollector(...).OfClass(FamilySymbol) в некоторых
    случаях пропускает типы без экземпляров, поэтому обходим сами
    семейства (Family) категории и берём их типоразмеры через
    GetFamilySymbolIds() — так гарантированно попадают все загруженные.
    """
    symbols = []

    families = FilteredElementCollector(doc).OfClass(Family)

    for family in families:
        try:
            if family.FamilyCategory is None:
                continue
            if family.FamilyCategory.Id != ElementId(BuiltInCategory.OST_GenericModel):
                continue
        except:
            continue

        for symbol_id in family.GetFamilySymbolIds():
            symbol = doc.GetElement(symbol_id)
            if symbol:
                symbols.append(symbol)

    return symbols


class WireTypeOption(object):
    """
    Обёртка над строкой ключевой спецификации кабелей для отображения в
    списке выбора (не WireType — см. list_wire_catalog_items).
    """

    def __init__(self, wire_type):
        self.wire_type = wire_type
        self.name = _safe_element_name(wire_type) or str(wire_type.Id.IntegerValue)

    def __str__(self):
        return self.name


def list_wire_catalog_items(doc, marker_param_name):
    """
    Строки ключевой спецификации кабелей, используемой параметром цепи
    «Проводник» (StorageType.ElementId — Revit хранит там ссылку на
    строку ключевой спецификации, а не на Autodesk.Revit.DB.Electrical.WireType).

    Ключевое имя строки хранится в BuiltInParameter.REF_TABLE_ELEM_NAME,
    общем для ВСЕХ ключевых спецификаций документа — поэтому дополнительно
    фильтруем по наличию marker_param_name (произвольный параметр,
    присутствующий только у строк нужного справочника кабелей, например
    "SMNX_Марка" — задаётся пользователем в настройках, т.к. это
    соглашение конкретного проекта).
    """
    from Autodesk.Revit.DB import BuiltInParameter

    if not marker_param_name:
        return []

    items = []
    for el in FilteredElementCollector(doc).WhereElementIsNotElementType().ToElements():
        try:
            key_param = el.get_Parameter(BuiltInParameter.REF_TABLE_ELEM_NAME)
            if not key_param or not key_param.HasValue:
                continue
            if el.LookupParameter(marker_param_name) is None:
                continue
        except:
            continue
        items.append(el)

    return items


def list_symbols_by_categories(doc, builtin_categories):
    """
    Все загруженные в проект типоразмеры для перечисленных
    BuiltInCategory (включая типы без вставленных экземпляров, см.
    list_generic_model_symbols).
    """
    category_ids = set(ElementId(bic) for bic in builtin_categories)
    symbols = []

    families = FilteredElementCollector(doc).OfClass(Family)

    for family in families:
        try:
            if family.FamilyCategory is None:
                continue
            if family.FamilyCategory.Id not in category_ids:
                continue
        except:
            continue

        for symbol_id in family.GetFamilySymbolIds():
            symbol = doc.GetElement(symbol_id)
            if symbol:
                symbols.append(symbol)

    return symbols


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
            u"Не удалось сохранить настройки СКС в файл:\n{}".format(path)
        )


def load_saved_values():
    """Строковые значения настроек: из JSON-файла, иначе — значения по умолчанию."""
    saved = _read_all()
    values = {}

    for key, _, default, _, _ in TEXT_FIELDS:
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
    """Преобразует строковые значения формы в типы, готовые для scs.py (id типов остаются строками)."""
    settings = dict(values)
    for key in LIST_FIELDS:
        settings[key] = _split_list(values[key])
    return settings


def require(settings, keys):
    """
    Проверяет, что перечисленные ключи заполнены в settings (после
    to_runtime_settings). Настройки общие на все кнопки SCS.panel, поэтому
    каждая кнопка проверяет только те поля, которые использует сама —
    остальные могут быть пустыми, если эта кнопка ими не пользуется.
    Останавливает скрипт через forms.alert(exitscript=True), если чего-то не хватает.
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
            u"В настройках СКС не заполнены обязательные для этой кнопки поля:\n\n{}\n\n"
            u"Запустите кнопку «Параметры СКС» и заполните их там.".format(u"\n".join(missing)),
            exitscript=True
        )


def show_settings_form(doc, values):
    """
    Модальное окно редактирования настроек СКС: выбор типов для вставки
    (панель/устройство/маршрут) + текстовые параметры.
    Возвращает словарь строковых значений или None, если пользователь отменил.
    """
    result = {"values": None}

    win = Window()
    win.Title = u"Настройки СКС"
    win.Width = 560
    win.Height = 760
    win.WindowStartupLocation = WindowStartupLocation.CenterScreen
    # Topmost намеренно НЕ ставим: иначе окно выбора типа
    # (forms.SelectFromList, отдельное Window) открывается позади этого
    # окна и его невозможно ни увидеть, ни подвинуть на передний план.

    outer = DockPanel()
    outer.LastChildFill = True

    root = StackPanel()
    root.Margin = Thickness(16)

    title = TextBlock()
    title.Text = u"Настройки параметров СКС"
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

    # --- текстовые параметры (сгруппированы по разделу, если подпись начинается с "[Раздел]") ---

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
        for key, _, default, _, _ in TEXT_FIELDS:
            boxes[key].Text = default

    def on_ok(sender, args):
        # Настройки общие на все кнопки SCS.panel — какие поля обязательны,
        # решает каждая кнопка сама через scs_settings.require() после
        # получения settings. Здесь просто сохраняем то, что введено.
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
    готовый к использованию словарь (списки уже разобраны из строк,
    id типов остаются строками — их разбирает вызывающий скрипт).
    Возвращает None, если пользователь нажал "Отмена".

    Используется только кнопкой «Параметры СКС» (SetupParameters) — это
    единственное место, где настройки редактируются. Остальные кнопки
    СКС берут уже сохранённые значения через get_settings_silent(),
    без показа окна.
    """
    saved = load_saved_values()
    edited = show_settings_form(doc, saved)

    if edited is None:
        return None

    save_values(edited)
    return to_runtime_settings(edited)


def get_settings_silent():
    """
    Настройки без показа окна — уже сохранённые значения (или значения
    по умолчанию из scs.py, если ещё ничего не настроено). Используется
    рабочими кнопками СКС (не «Параметры СКС»): настраивать/менять
    значения — задача кнопки «Параметры СКС», остальные только читают.
    """
    return to_runtime_settings(load_saved_values())
