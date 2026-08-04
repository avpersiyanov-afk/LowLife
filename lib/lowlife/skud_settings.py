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

from Autodesk.Revit.DB import ElementId, Element, BuiltInCategory

from pyrevit import forms

from System.Windows import (
    Window, WindowStartupLocation, Thickness,
    FontWeights, HorizontalAlignment, VerticalAlignment, TextWrapping
)
from System.Windows.Controls import (
    StackPanel, TextBlock, TextBox, Button, Orientation, DockPanel, Dock, ScrollViewer,
    ScrollBarVisibility, Canvas
)
from System.Windows.Media import Brushes, SolidColorBrush, Colors
from System.Windows.Shapes import Ellipse

from lowlife import skud as skud_defaults
from lowlife.skud import parse_category_names
from lowlife.scs_settings import (
    list_generic_model_symbols, list_symbols_by_categories, list_wire_types,
    _safe_element_name, TypeOption, WireTypeOption
)

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

    # --- узлы трассы СКУД (PlaceRouteNodes) ---
    # Узлы СКУД — свои, отдельные от СКС: узлы СКС ведут до шкафа СКС,
    # узлы СКУД — от устройств до контроллера. Различаются рабочим
    # набором (workset_filter_key, например «СКУД») и своими типами
    # семейств панель/маршрут/стояк.
    ("workset_filter_key", u"[Узлы трассы] Ключевое слово рабочего набора элементов СКУД",
        u"", False, True, False),
    ("family_filter", u"[Узлы трассы] Фильтр семейства сегментов трассы",
        u"", False, True, False),
    ("route_param_name", u"[Узлы трассы] Параметр «Тип трассы»",
        u"", False, True, False),
    ("route_param_value", u"[Узлы трассы] Значение «Тип трассы» (не для стояков)",
        u"", False, True, False),
    ("route_param_value_riser", u"[Узлы трассы] Значение «Тип трассы» для стояков",
        u"", False, True, False),
    ("device_cable_type_value", u"[Узлы трассы] Тип прокладки кабеля для панелей и стояков",
        u"", False, True, False),
    ("panel_keywords", u"[Узлы трассы] Ключевые слова панелей/контроллеров (через запятую)",
        u"контроллер, панель, шкаф", True, False, False),
    ("panel_exclude_keywords", u"[Узлы трассы] Слова-исключения панелей (через запятую)",
        u"", True, False, False),
    ("riser_keywords", u"[Узлы трассы] Ключевые слова стояков (через запятую)",
        u"стояк", True, False, False),
    ("riser_exclude_keywords", u"[Узлы трассы] Слова-исключения стояков (через запятую)",
        u"", True, False, False),
    ("offset_param_names", u"[Узлы трассы] Возможные имена параметра отметки (через запятую)",
        u"", True, True, False),

    # --- адресация узлов трассы СКУД (RenumberAddresses) ---
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
    ("schematic_address_param", u"[Схема] Параметр адреса на схемном семействе",
        u"", False, True, False),
    ("schematic_layout_gap_m", u"[Схема] Отступ между контроллерами при автораскладке, м",
        u"5", False, True, False),
    ("schematic_layout_per_row", u"[Схема] Число контроллеров в ряду при автораскладке",
        u"5", False, True, False),
    ("schematic_layout_step_mm", u"[Схема] Шаг между устройствами одной категории у одного контроллера, мм",
        u"10", False, True, False),
    ("schematic_device_categories_text", u"[Схема] Категории устройств схемы (по одной на строку)",
        u"", False, True, True),
]

# (ключ, подпись) — типы, выбираемые из проекта (категория "Обобщённые модели")
TYPE_FIELDS = [
    ("panel_type_id", u"Тип для точек панелей/контроллеров СКУД"),
    ("route_type_id", u"Тип для узлов маршрута СКУД"),
    ("riser_type_id", u"Тип для точек стояков СКУД"),
]

# Отдельный ключ в JSON-файле настроек: {имя_категории_схемы: "id_типа"} —
# по типу семейства на каждую категорию устройств из
# schematic_device_categories_text (список категорий динамический, поэтому
# не помещается в статический TYPE_FIELDS).
SCHEMATIC_CATEGORY_TYPES_KEY = "schematic_category_type_ids"

# {имя_категории: ["id_типа1", "id_типа2", ...]} — реальные типы устройств
# модели, которые относятся к этой категории (замена сопоставлению по
# ключевым словам: категория реального устройства определяется точным
# совпадением типа с одним из выбранных здесь).
SCHEMATIC_CATEGORY_DEVICE_TYPES_KEY = "schematic_category_device_type_ids"

# {имя_категории: [dx_mm, dy_mm]} — смещение точки вставки категории от
# точки контроллера (0,0), используется структурной схемой и превью в
# окне настроек.
SCHEMATIC_CATEGORY_LAYOUT_KEY = "schematic_category_layout_mm"

# {имя_категории: "id_WireType"} — тип проводника (параметр цепи «Проводник»)
# для устройств этой категории (AssignCircuitsAndCables). Категории — те же
# имена, что и schematic_device_categories_text (одна общая таблица
# категорий на схему и на подбор кабеля).
SCHEMATIC_CATEGORY_WIRE_TYPES_KEY = "schematic_category_wire_type_ids"

# Категории BuiltInCategory, из которых предлагается выбор типов реальных
# устройств СКУД для сопоставления схема-модель (контроллер — электро-
# оборудование, остальные устройства — охранная сигнализация).
SCHEMATIC_DEVICE_SOURCE_CATEGORIES = ("OST_SecurityDevices", "OST_ElectricalEquipment")

# Категория BuiltInCategory схемных семейств («элементы узлов» структурной
# схемы) — Detail Items, отдельная от «Обобщённых моделей» узлов трассы
# (panel_type_id/route_type_id/riser_type_id).
SCHEMATIC_FAMILY_SOURCE_CATEGORIES = ("OST_DetailComponents",)

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


def load_schematic_category_type_ids():
    """{имя_категории: "id_типа"} — сохранённые типы схемных семейств по категории."""
    saved = _read_all()
    return dict(saved.get(SCHEMATIC_CATEGORY_TYPES_KEY, {}))


def load_schematic_category_device_type_ids():
    """{имя_категории: ["id_типа", ...]} — реальные типы устройств модели по категории."""
    saved = _read_all()
    return dict(saved.get(SCHEMATIC_CATEGORY_DEVICE_TYPES_KEY, {}))


def load_schematic_category_layout_mm():
    """{имя_категории: [dx_mm, dy_mm]} — смещение категории от точки контроллера."""
    saved = _read_all()
    return dict(saved.get(SCHEMATIC_CATEGORY_LAYOUT_KEY, {}))


def load_schematic_category_wire_type_ids():
    """{имя_категории: "id_WireType"} — тип проводника по категории устройства."""
    saved = _read_all()
    return dict(saved.get(SCHEMATIC_CATEGORY_WIRE_TYPES_KEY, {}))


def get_schematic_category_symbols(doc, settings):
    """
    {имя_категории: FamilySymbol} для категорий из
    schematic_device_categories_text, у которых в настройках выбран
    существующий в проекте тип схемного семейства. Категории без
    выбранного/валидного типа в словарь не попадают — вызывающий код
    должен сам решить, что делать с устройствами таких категорий
    (например, отчитаться как unmatched).
    """
    categories = parse_category_names(settings.get("schematic_device_categories_text", u""))
    type_ids = load_schematic_category_type_ids()

    symbols = {}
    for name in categories:
        id_str = type_ids.get(name)
        if not id_str:
            continue
        try:
            symbol = doc.GetElement(ElementId(int(id_str)))
        except:
            symbol = None
        if symbol is not None:
            symbols[name] = symbol

    return symbols


def get_schematic_category_device_type_ids(settings):
    """
    {имя_категории: set(int)} — целочисленные ElementId реальных типов
    устройств модели, отнесённых к каждой категории (для
    skud.category_by_type_id). Категории без выбранных типов в словарь
    не попадают.
    """
    categories = parse_category_names(settings.get("schematic_device_categories_text", u""))
    saved = load_schematic_category_device_type_ids()

    result = {}
    for name in categories:
        id_strs = saved.get(name) or []
        ids = set()
        for id_str in id_strs:
            try:
                ids.add(int(id_str))
            except:
                continue
        if ids:
            result[name] = ids

    return result


def get_schematic_category_layout_ft(settings):
    """
    {имя_категории: (dx_ft, dy_ft)} — смещение категории от точки
    контроллера, для skud_schematic.device_layout_point. Категории без
    заданного смещения получают (0.0, 0.0) при использовании (см.
    device_layout_point) и в этот словарь не попадают.
    """
    categories = parse_category_names(settings.get("schematic_device_categories_text", u""))
    saved = load_schematic_category_layout_mm()

    MM_TO_FT = 1.0 / (0.3048 * 1000.0)

    result = {}
    for name in categories:
        pair = saved.get(name)
        if not pair or len(pair) != 2:
            continue
        try:
            dx_mm, dy_mm = float(pair[0]), float(pair[1])
        except:
            continue
        result[name] = (dx_mm * MM_TO_FT, dy_mm * MM_TO_FT)

    return result


def get_schematic_category_wire_names(doc, settings):
    """
    {имя_категории: имя_WireType} для категорий из
    schematic_device_categories_text, у которых в настройках выбран
    существующий в проекте тип проводника. Имя (не id) — потому что
    значение записывается в текстовый параметр цепи «Проводник» через
    set_param_any, как и раньше со свободным текстовым словарём.
    """
    categories = parse_category_names(settings.get("schematic_device_categories_text", u""))
    wire_type_ids = load_schematic_category_wire_type_ids()

    names = {}
    for name in categories:
        id_str = wire_type_ids.get(name)
        if not id_str:
            continue
        try:
            wire_type = doc.GetElement(ElementId(int(id_str)))
        except:
            wire_type = None
        if wire_type is not None:
            wire_name = _safe_element_name(wire_type)
            if wire_name:
                names[name] = wire_name

    return names


def save_values(values):
    data = _read_all()
    data.update(values)
    _write_all(data)


def save_schematic_category_type_ids(type_ids):
    data = _read_all()
    data[SCHEMATIC_CATEGORY_TYPES_KEY] = dict(type_ids)
    _write_all(data)


def save_schematic_category_device_type_ids(type_ids):
    data = _read_all()
    data[SCHEMATIC_CATEGORY_DEVICE_TYPES_KEY] = dict(type_ids)
    _write_all(data)


def save_schematic_category_layout_mm(layout):
    data = _read_all()
    data[SCHEMATIC_CATEGORY_LAYOUT_KEY] = dict(layout)
    _write_all(data)


def save_schematic_category_wire_type_ids(wire_type_ids):
    data = _read_all()
    data[SCHEMATIC_CATEGORY_WIRE_TYPES_KEY] = dict(wire_type_ids)
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

    category_type_ids = load_schematic_category_type_ids()
    category_device_type_ids = load_schematic_category_device_type_ids()
    category_layout_mm = load_schematic_category_layout_mm()
    category_wire_type_ids = load_schematic_category_wire_type_ids()

    category_type_labels = {}
    category_device_labels = {}
    category_layout_boxes = {}
    category_wire_labels = {}
    category_types_panel = StackPanel()
    layout_preview_canvas = Canvas()
    layout_preview_canvas.Height = 220
    layout_preview_canvas.Background = Brushes.Transparent

    PREVIEW_SCALE = 0.4  # пикселей на мм
    PREVIEW_CENTER = (300, 110)

    def redraw_layout_preview(sender=None, args=None):
        layout_preview_canvas.Children.Clear()

        cx, cy = PREVIEW_CENTER

        controller_dot = Ellipse()
        controller_dot.Width = 10
        controller_dot.Height = 10
        controller_dot.Fill = SolidColorBrush(Colors.OrangeRed)
        Canvas.SetLeft(controller_dot, cx - 5)
        Canvas.SetTop(controller_dot, cy - 5)
        layout_preview_canvas.Children.Add(controller_dot)

        controller_label = TextBlock()
        controller_label.Text = u"контроллер"
        controller_label.FontSize = 10
        Canvas.SetLeft(controller_label, cx + 8)
        Canvas.SetTop(controller_label, cy - 8)
        layout_preview_canvas.Children.Add(controller_label)

        for name, (dx_box, dy_box) in category_layout_boxes.items():
            try:
                dx_mm = float(dx_box.Text)
                dy_mm = float(dy_box.Text)
            except:
                continue

            dot = Ellipse()
            dot.Width = 8
            dot.Height = 8
            dot.Fill = SolidColorBrush(Colors.DodgerBlue)
            x = cx + dx_mm * PREVIEW_SCALE
            y = cy - dy_mm * PREVIEW_SCALE
            Canvas.SetLeft(dot, x - 4)
            Canvas.SetTop(dot, y - 4)
            layout_preview_canvas.Children.Add(dot)

            label = TextBlock()
            label.Text = name
            label.FontSize = 10
            Canvas.SetLeft(label, x + 6)
            Canvas.SetTop(label, y - 7)
            layout_preview_canvas.Children.Add(label)

    def rebuild_category_type_pickers(sender=None, args=None):
        category_types_panel.Children.Clear()
        category_type_labels.clear()
        category_device_labels.clear()
        category_layout_boxes.clear()
        category_wire_labels.clear()

        categories = parse_category_names(boxes["schematic_device_categories_text"].Text)

        if not categories:
            hint2 = TextBlock()
            hint2.Text = u"(нет категорий — заполните поле выше и нажмите «Обновить список»)"
            hint2.FontSize = 11
            hint2.Foreground = Brushes.Gray
            category_types_panel.Children.Add(hint2)
            redraw_layout_preview()
            return

        for name in categories:
            group_title = TextBlock()
            group_title.Text = u"Категория «{}»".format(name)
            group_title.FontWeight = FontWeights.Bold
            group_title.Margin = Thickness(0, 12, 0, 2)
            category_types_panel.Children.Add(group_title)

            # --- схемное семейство для вставки ---

            label = TextBlock()
            label.Text = u"Схемное семейство (для вставки)"
            label.Margin = Thickness(0, 4, 0, 2)
            category_types_panel.Children.Add(label)

            row = StackPanel()
            row.Orientation = Orientation.Horizontal

            value_label = TextBlock()
            value_label.Text = _type_display_name(doc, category_type_ids.get(name, ""))
            value_label.VerticalAlignment = VerticalAlignment.Center
            value_label.Width = 280
            value_label.TextWrapping = TextWrapping.Wrap
            category_type_labels[name] = value_label

            pick_btn = Button()
            pick_btn.Content = u"Выбрать..."
            pick_btn.Padding = Thickness(8, 2, 8, 2)
            pick_btn.Margin = Thickness(8, 0, 0, 0)

            def on_pick_schematic(sender, args, name=name):
                schematic_categories = [
                    getattr(BuiltInCategory, key)
                    for key in SCHEMATIC_FAMILY_SOURCE_CATEGORIES
                ]
                symbols = list_symbols_by_categories(doc, schematic_categories)
                if not symbols:
                    forms.alert(u"В проекте нет типов категории «Элементы узлов».")
                    return

                options = sorted([TypeOption(s) for s in symbols], key=lambda o: o.name)
                selected = forms.SelectFromList.show(
                    options,
                    title=u"Схемное семейство для категории «{}»".format(name),
                    button_name=u"Выбрать",
                    multiselect=False
                )

                if selected:
                    category_type_ids[name] = str(selected.symbol.Id.IntegerValue)
                    category_type_labels[name].Text = selected.name

            pick_btn.Click += on_pick_schematic

            row.Children.Add(value_label)
            row.Children.Add(pick_btn)
            category_types_panel.Children.Add(row)

            # --- реальные типы устройств модели, относящиеся к категории ---

            label2 = TextBlock()
            label2.Text = u"Реальные типы устройств этой категории (в модели)"
            label2.Margin = Thickness(0, 6, 0, 2)
            category_types_panel.Children.Add(label2)

            row2 = StackPanel()
            row2.Orientation = Orientation.Horizontal

            device_ids = category_device_type_ids.get(name, [])
            device_label = TextBlock()
            device_label.Text = u"выбрано типов: {}".format(len(device_ids))
            device_label.VerticalAlignment = VerticalAlignment.Center
            device_label.Width = 280
            device_label.TextWrapping = TextWrapping.Wrap
            category_device_labels[name] = device_label

            pick_btn2 = Button()
            pick_btn2.Content = u"Выбрать..."
            pick_btn2.Padding = Thickness(8, 2, 8, 2)
            pick_btn2.Margin = Thickness(8, 0, 0, 0)

            def on_pick_devices(sender, args, name=name):
                source_categories = [
                    getattr(BuiltInCategory, key)
                    for key in SCHEMATIC_DEVICE_SOURCE_CATEGORIES
                ]
                symbols = list_symbols_by_categories(doc, source_categories)
                if not symbols:
                    forms.alert(u"В проекте нет типов в категориях «Охранная сигнализация»/«Электрооборудование».")
                    return

                options = sorted([TypeOption(s) for s in symbols], key=lambda o: o.name)

                selected = forms.SelectFromList.show(
                    options,
                    title=u"Типы устройств для категории «{}»".format(name),
                    button_name=u"Выбрать",
                    multiselect=True
                )

                if selected is not None:
                    category_device_type_ids[name] = [
                        str(o.symbol.Id.IntegerValue) for o in selected
                    ]
                    category_device_labels[name].Text = u"выбрано типов: {}".format(len(selected))

            pick_btn2.Click += on_pick_devices

            row2.Children.Add(device_label)
            row2.Children.Add(pick_btn2)
            category_types_panel.Children.Add(row2)

            # --- тип проводника (WireType) для устройств категории ---

            label4 = TextBlock()
            label4.Text = u"Тип проводника (для параметра «Проводник» цепи)"
            label4.Margin = Thickness(0, 6, 0, 2)
            category_types_panel.Children.Add(label4)

            row4 = StackPanel()
            row4.Orientation = Orientation.Horizontal

            wire_value_label = TextBlock()
            wire_value_label.Text = _type_display_name(doc, category_wire_type_ids.get(name, ""))
            wire_value_label.VerticalAlignment = VerticalAlignment.Center
            wire_value_label.Width = 280
            wire_value_label.TextWrapping = TextWrapping.Wrap
            category_wire_labels[name] = wire_value_label

            pick_btn4 = Button()
            pick_btn4.Content = u"Выбрать..."
            pick_btn4.Padding = Thickness(8, 2, 8, 2)
            pick_btn4.Margin = Thickness(8, 0, 0, 0)

            def on_pick_wire(sender, args, name=name):
                wire_types = list_wire_types(doc)
                if not wire_types:
                    forms.alert(u"В проекте нет типов проводника (WireType).")
                    return

                options = sorted([WireTypeOption(w) for w in wire_types], key=lambda o: o.name)
                selected = forms.SelectFromList.show(
                    options,
                    title=u"Тип проводника для категории «{}»".format(name),
                    button_name=u"Выбрать",
                    multiselect=False
                )

                if selected:
                    category_wire_type_ids[name] = str(selected.wire_type.Id.IntegerValue)
                    category_wire_labels[name].Text = selected.name

            pick_btn4.Click += on_pick_wire

            row4.Children.Add(wire_value_label)
            row4.Children.Add(pick_btn4)
            category_types_panel.Children.Add(row4)

            # --- координаты (dx, dy от точки контроллера, мм) ---

            label3 = TextBlock()
            label3.Text = u"Координаты (dx, dy от контроллера, мм)"
            label3.Margin = Thickness(0, 6, 0, 2)
            category_types_panel.Children.Add(label3)

            row3 = StackPanel()
            row3.Orientation = Orientation.Horizontal

            saved_pair = category_layout_mm.get(name, [0, 0])

            dx_box = TextBox()
            dx_box.Text = str(saved_pair[0]) if len(saved_pair) > 0 else u"0"
            dx_box.Width = 80
            dx_box.Padding = Thickness(4)

            dy_box = TextBox()
            dy_box.Text = str(saved_pair[1]) if len(saved_pair) > 1 else u"0"
            dy_box.Width = 80
            dy_box.Padding = Thickness(4)
            dy_box.Margin = Thickness(8, 0, 0, 0)

            category_layout_boxes[name] = (dx_box, dy_box)

            dx_box.TextChanged += redraw_layout_preview
            dy_box.TextChanged += redraw_layout_preview

            row3.Children.Add(dx_box)
            row3.Children.Add(dy_box)
            category_types_panel.Children.Add(row3)

        redraw_layout_preview()

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

        if key == "schematic_device_categories_text":
            refresh_btn = Button()
            refresh_btn.Content = u"Обновить список категорий ниже"
            refresh_btn.Padding = Thickness(8, 2, 8, 2)
            refresh_btn.HorizontalAlignment = HorizontalAlignment.Left
            refresh_btn.Margin = Thickness(0, 4, 0, 0)
            refresh_btn.Click += rebuild_category_type_pickers
            root.Children.Add(refresh_btn)

            category_types_title = TextBlock()
            category_types_title.Text = u"Категории структурной схемы: семейства, устройства, координаты"
            category_types_title.FontWeight = FontWeights.Bold
            category_types_title.Margin = Thickness(0, 12, 0, 4)
            category_types_title.TextWrapping = TextWrapping.Wrap
            root.Children.Add(category_types_title)

            preview_title = TextBlock()
            preview_title.Text = u"Превью раскладки (от точки контроллера)"
            preview_title.FontWeight = FontWeights.Bold
            preview_title.Margin = Thickness(0, 8, 0, 2)
            root.Children.Add(preview_title)
            root.Children.Add(layout_preview_canvas)

            root.Children.Add(category_types_panel)
            rebuild_category_type_pickers()

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
        save_schematic_category_type_ids(category_type_ids)
        save_schematic_category_device_type_ids(category_device_type_ids)
        save_schematic_category_wire_type_ids(category_wire_type_ids)

        layout_to_save = {}
        for name, (dx_box, dy_box) in category_layout_boxes.items():
            try:
                layout_to_save[name] = [float(dx_box.Text), float(dy_box.Text)]
            except:
                continue
        save_schematic_category_layout_mm(layout_to_save)

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
