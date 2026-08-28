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

from Autodesk.Revit.DB import (
    ElementId, FilteredElementCollector, Family, BuiltInCategory, Element, GroupType
)

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
from lowlife.skud import parse_category_names

SETTINGS_FILE_NAME = "LowLifeSCS_settings.json"

# (ключ, подпись в окне, значение по умолчанию, список ли это через запятую,
#  обязательное ли поле, многострочное ли поле)
TEXT_FIELDS = [
    ("family_filter", u"Фильтр семейства сегментов трассы",
        scs_defaults.FAMILY_FILTER, False, True, False),
    ("cable_param_name", u"Параметр «Тип прокладки кабеля»",
        scs_defaults.CABLE_PARAM_NAME, False, True, False),
    ("route_param_name", u"Параметр «Тип трассы»",
        scs_defaults.ROUTE_PARAM_NAME, False, True, False),
    ("route_param_value", u"Значение параметра «Тип трассы» (не для стояков)",
        scs_defaults.ROUTE_PARAM_VALUE, False, True, False),
    ("route_param_value_riser", u"Значение параметра «Тип трассы» для стояков",
        scs_defaults.ROUTE_PARAM_VALUE_RISER, False, True, False),
    ("device_cable_type_value", u"Тип прокладки кабеля для панелей и стояков",
        scs_defaults.DEVICE_CABLE_TYPE_VALUE, False, True, False),
    ("riser_keywords", u"Ключевые слова стояков (через запятую)",
        u", ".join(scs_defaults.RISER_KEYWORDS), True, False, False),
    ("riser_exclude_keywords", u"Слова-исключения стояков (через запятую)",
        u", ".join(scs_defaults.RISER_EXCLUDE_KEYWORDS), True, False, False),
    ("riser_annotation_keywords", u"Ключевые слова аннотации стояка (через запятую)",
        u", ".join(scs_defaults.RISER_ANNOTATION_KEYWORDS), True, False, False),
    ("offset_param_names", u"Возможные имена параметра отметки (через запятую)",
        u", ".join(scs_defaults.OFFSET_PARAM_NAMES), True, True, False),

    # --- адресация узлов (RenumberAddresses) ---
    ("addr_param_name", u"[Адресация] Параметр «Адрес узла»",
        u"", False, True, False),
    ("addr_prev_param_name", u"[Адресация] Параметр «Предыдущий адрес»",
        u"", False, True, False),

    # --- критерии определения панели/шкафа — используются РАЗНЫМИ кнопками
    # для РАЗНЫХ целей (см. пояснение в окне настроек): ключевые слова —
    # для расстановки узлов и корней адресации (PlaceRouteNodes/
    # RenumberAddresses), рабочий набор — для выбора целевых панелей,
    # для которых считаются цепи (SyncCircuitsAndLengths). Элемент должен
    # подходить под оба критерия, чтобы полноценно участвовать во всех
    # трёх кнопках — если что-то из этого не работает, проверьте оба поля.
    ("panel_keywords", u"[Критерии панели] Ключевые слова панелей (через запятую)",
        u", ".join(scs_defaults.PANEL_KEYWORDS), True, False, False),
    ("panel_exclude_keywords", u"[Критерии панели] Слова-исключения панелей (через запятую)",
        u", ".join(scs_defaults.PANEL_EXCLUDE_KEYWORDS), True, False, False),
    ("workset_param_name", u"[Критерии панели] Параметр рабочего набора элемента",
        u"Рабочий набор", False, True, False),
    ("workset_filter_key", u"[Критерии панели] Ключевое слово рабочего набора целевых панелей",
        u"", False, True, False),

    # --- расчёт цепей и длин (SyncCircuitsAndLengths) ---
    ("excluded_device_keywords", u"[Цепи] Ключевые слова резервных портов, исключаемых из расчёта (через запятую)",
        u"", True, False, False),
    ("circuit_panel_param", u"[Цепи] Параметр цепи «Панель»",
        u"", False, True, False),
    ("nearest_segment_param", u"[Цепи] Параметр «Ближайший узел маршрута» (у панелей и устройств)",
        u"", False, True, False),
    ("device_address_param", u"[Цепи] Параметр устройства «Адрес устройства»",
        u"", False, True, False),
    ("type_code_param", u"[Цепи] Параметр типа устройства «Обозначение»",
        u"", False, True, False),
    ("circuit_name_type_param", u"[Цепи] Параметр цепи «Наименование» (для определения типа цепи)",
        u"", False, True, False),
    ("circuit_number_param", u"[Цепи] Параметр цепи «Номер цепи»",
        u"", False, True, False),
    ("circuit_route_param", u"[Цепи] Параметр цепи «Маршрут цепи»",
        u"", False, True, False),
    ("wire_length_param", u"[Цепи] Параметр цепи «Длина проводника»",
        u"", False, True, False),
    ("tray_length_param", u"[Цепи] Параметр цепи «Длина проводника в лотке»",
        u"", False, True, False),
    ("pipe_length_param", u"[Цепи] Параметр цепи «Длина проводника в трубе»",
        u"", False, True, False),
    ("route_method_param", u"[Цепи] Параметр цепи «Способ прокладки»",
        u"", False, True, False),
    ("load_name_param", u"[Цепи] Параметр цепи «Имя нагрузки»",
        u"", False, True, False),
    ("wire_catalog_marker_param", u"[Цепи] Параметр-признак строки справочника кабелей "
        u"(нужен для подбора проводника для цепей СКС кнопкой ниже)",
        u"", False, False, False),
    ("segment_loads_param", u"[Цепи] Параметр узла маршрута «Список цепей»",
        u"", False, True, False),
    ("install_tray_key", u"[Цепи] Значение «Тип прокладки» = лоток",
        u"Лоток", False, True, False),
    ("install_pipe_key", u"[Цепи] Значение «Тип прокладки» = труба",
        u"Труба", False, True, False),
    ("install_pipe_open_key", u"[Цепи] Значение «Тип прокладки» = труба открыто",
        u"Труба открыто", False, True, False),
    ("route_label_pipe_format", u"[Цепи] Формат метки трубы (используйте {} для метров)",
        u"", False, True, False),
    ("route_label_tray_format", u"[Цепи] Формат метки лотка (используйте {} для метров)",
        u"", False, True, False),
    ("route_label_pipe_open_format", u"[Цепи] Формат метки трубы открыто (используйте {} для метров)",
        u"", False, True, False),
    ("circuit_key_fo", u"[Цепи] Ключевое слово типа цепи «оптическая»",
        u"оптический", False, True, False),
    ("circuit_key_utp", u"[Цепи] Ключевое слово типа цепи «UTP/витая пара»",
        u"парной скрутки", False, True, False),
    ("circuit_key_power", u"[Цепи] Ключевое слово типа цепи «силовая»",
        u"силовой", False, True, False),
    ("horiz_tray_coef", u"[Цепи] Коэффициент запаса длины в лотке",
        u"1.10", False, True, False),
    ("horiz_pipe_coef", u"[Цепи] Коэффициент запаса длины в трубе (горизонталь)",
        u"1.15", False, True, False),
    ("vertical_coef", u"[Цепи] Коэффициент запаса длины по вертикали",
        u"1.10", False, True, False),

    # --- структурная схема (BuildScsSchematic) ---
    ("schematic_view_name", u"[Схема] Имя чертёжного вида структурной схемы (создаётся с этим "
        u"именем; при повторных запусках обновляется только вид с этим именем)",
        u"Структурная схема СКС", False, True, False),
    ("layout_param_name", u"[Схема] Служебный параметр вида для хранения раскладки схемы "
        u"(текстовый, привязан к категории «Виды», JSON — не редактируется вручную)",
        u"", False, True, False),
    ("room_param_name", u"[Схема] Параметр помещения (на устройстве, панели и на схемном "
        u"семействе)",
        u"", False, True, False),
    ("room_number_param_name", u"[Схема] Параметр номера помещения в связанной модели "
        u"(используется, если параметр помещения на устройстве ещё пуст)",
        u"", False, True, False),
    ("device_uid_param_name", u"[Схема] Служебный параметр схемного семейства для UniqueId "
        u"исходного устройства (текстовый, привязан к схемным семействам)",
        u"", False, True, False),
    ("node_label_offset_mm", u"[Схема] Смещение марки узла вверх от точки вставки, мм",
        u"5", False, True, False),
    ("schematic_device_categories_text", u"[Схема] Категории устройств схемы (по одной на строку "
        u"— например «Розетка», «Шкаф»; для каждой ниже отдельно выбирается схемное семейство "
        u"и реальные типы устройств/панелей этой категории)",
        u"", False, True, True),
]

# (ключ, подпись, категории для пикера) — типы, выбираемые из проекта.
TYPE_FIELDS = [
    ("panel_type_id", u"Тип для точек панелей", (BuiltInCategory.OST_GenericModel,)),
    ("route_type_id", u"Тип для узлов маршрута", (BuiltInCategory.OST_GenericModel,)),
    ("riser_type_id", u"Тип для точек стояков", (BuiltInCategory.OST_GenericModel,)),
    ("node_annotation_type_id", u"[Схема] Марка узла на схеме (тип «Обозначение, Адрес», "
        u"ставится над каждым схемным семейством)",
        (BuiltInCategory.OST_DetailComponentTags,)),
]

# Категории реальных устройств/панелей СКС для схемы — только устройства
# связи и электрооборудование (панели/шкафы), а не весь набор
# CAT_DEVICES_AND_PANELS из scs_parameters.py (тот шире — используется
# для привязки параметров, где лишняя категория не мешает; здесь же это
# список выбора в пикере "реальные типы этой категории", и лишние
# категории только засоряли бы его типами, не относящимися к СКС).
# Источник списка — в таблице категорий структурной схемы
# (rebuild_category_type_pickers).
SCHEMATIC_SOURCE_CATEGORIES = (
    BuiltInCategory.OST_CommunicationDevices,
    BuiltInCategory.OST_ElectricalEquipment,
)

# Категория схемных семейств (элементы узлов/детализация) — та же, что у СОТ/СКУД.
SCHEMATIC_CATEGORIES = (BuiltInCategory.OST_DetailComponents,)

# {имя_категории: "id_типа"} — схемное семейство для категории.
SCHEMATIC_CATEGORY_TYPES_KEY = "schematic_category_type_ids"

# {имя_категории: ["id_типа1", ...]} — реальные типы устройств/панелей этой категории.
SCHEMATIC_CATEGORY_DEVICE_TYPES_KEY = "schematic_category_device_type_ids"

# (ключ, подпись) — строка справочника кабелей (см. list_wire_catalog_items),
# выбирается отдельным пикером, а не текстом; хранится и читается так же,
# как TYPE_FIELDS, но источник списка для выбора другой.
CONDUCTOR_FIELDS = [
    ("conductor_type_id", u"Проводник (тип кабеля) для цепей СКС"),
]

LIST_FIELDS = set(key for key, _, _, is_list, _req, _ml in TEXT_FIELDS if is_list)


def _split_section(label_text):
    """"[Раздел] Подпись" -> ("Раздел", "Подпись"); просто "Подпись" -> (None, "Подпись")."""
    if label_text.startswith(u"[") and u"]" in label_text:
        end = label_text.index(u"]")
        return label_text[1:end], label_text[end + 1:].strip()
    return None, label_text


# Подписи без префикса "[Раздел]" — используются в сообщениях об отсутствующих полях
PLAIN_LABELS = {}
for _key, _label, _default, _is_list, _required, _multiline in TEXT_FIELDS:
    PLAIN_LABELS[_key] = _split_section(_label)[1]
for _key, _label, _categories in TYPE_FIELDS:
    PLAIN_LABELS[_key] = _split_section(_label)[1]
for _key, _label in CONDUCTOR_FIELDS:
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
        base_name = _safe_element_name(wire_type) or str(wire_type.Id.IntegerValue)
        self.name = u"{} (ID {})".format(base_name, wire_type.Id.IntegerValue)

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


class GroupTypeOption(object):
    """Обёртка над GroupType (тип группы) для отображения в списке выбора."""

    def __init__(self, group_type):
        self.group_type = group_type
        self.name = _safe_element_name(group_type) or str(group_type.Id.IntegerValue)

    def __str__(self):
        return self.name


def list_detail_group_types(doc):
    """
    Типы групп деталей проекта (GroupType категории OST_IOSDetailGroups),
    включая ещё не размещённые. Для выбора типовых групп структурной схемы
    СКУД (см. skud_settings).
    """
    result = []

    for group_type in FilteredElementCollector(doc).OfClass(GroupType):
        try:
            category = group_type.Category
        except:
            category = None
        if category is None:
            continue
        if category.Id.IntegerValue == int(BuiltInCategory.OST_IOSDetailGroups):
            result.append(group_type)

    return result


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


def _type_names_display(doc, id_strs):
    """Отображаемое имя списка выбранных типов (id-строки) через "; ", либо "(не выбрано)"."""
    if not id_strs:
        return u"(не выбрано)"
    return u"; ".join(_type_display_name(doc, s) for s in id_strs)


def list_used_symbols_by_categories(doc, builtin_categories):
    """
    Только типы, у которых в проекте есть хотя бы один размещённый
    экземпляр — в отличие от list_symbols_by_categories (все загруженные
    типы, включая никогда не использованные), чтобы список выбора
    реальных устройств/панелей категории структурной схемы не
    засорялся типами, которых нет на модели. Для схемных семейств
    (ещё не вставленных на схему) по-прежнему используется
    list_symbols_by_categories.
    """
    seen_ids = set()
    symbols = []

    for bic in builtin_categories:
        try:
            instances = FilteredElementCollector(doc).OfCategory(bic).WhereElementIsNotElementType().ToElements()
        except:
            continue

        for el in instances:
            try:
                type_id = el.GetTypeId()
            except:
                continue

            if type_id is None or type_id == ElementId.InvalidElementId:
                continue

            if type_id.IntegerValue in seen_ids:
                continue

            symbol = doc.GetElement(type_id)
            if symbol is not None:
                seen_ids.add(type_id.IntegerValue)
                symbols.append(symbol)

    return symbols


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

    for key, _, default, _, _, _ in TEXT_FIELDS:
        values[key] = saved.get(key, default)

    for key, _, _ in TYPE_FIELDS:
        values[key] = saved.get(key, "")

    for key, _ in CONDUCTOR_FIELDS:
        values[key] = saved.get(key, "")

    return values


def save_values(values):
    data = _read_all()
    data.update(values)
    _write_all(data)


def load_schematic_category_type_ids():
    saved = _read_all()
    return dict(saved.get(SCHEMATIC_CATEGORY_TYPES_KEY, {}))


def load_schematic_category_device_type_ids():
    saved = _read_all()
    return dict(saved.get(SCHEMATIC_CATEGORY_DEVICE_TYPES_KEY, {}))


def save_schematic_category_type_ids(type_ids):
    data = _read_all()
    data[SCHEMATIC_CATEGORY_TYPES_KEY] = dict(type_ids)
    _write_all(data)


def save_schematic_category_device_type_ids(type_ids):
    data = _read_all()
    data[SCHEMATIC_CATEGORY_DEVICE_TYPES_KEY] = dict(type_ids)
    _write_all(data)


def get_schematic_category_symbols(doc, settings):
    """
    {имя_категории: FamilySymbol} для категорий из
    schematic_device_categories_text с выбранным существующим в проекте
    схемным типом. Категории без выбранного/валидного типа в словарь не
    попадают.
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
    """{имя_категории: set(int)} — id реальных типов устройств/панелей категории."""
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

    type_values = {key: values.get(key, "") for key, _, _ in TYPE_FIELDS}
    type_labels = {}

    type_current_section = [None]

    def make_type_picker(key, label_text, categories):
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

        def on_pick(sender, args, key=key, label_text=label_text, categories=categories):
            symbols = list_symbols_by_categories(doc, categories)
            if not symbols:
                forms.alert(u"В проекте нет типов нужной категории.")
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

    for key, label_text, categories in TYPE_FIELDS:
        make_type_picker(key, label_text, categories)

    # --- текстовые параметры (сгруппированы по разделу, если подпись начинается с "[Раздел]") ---

    boxes = {}
    current_section = None
    panel_criteria_hint_shown = [False]

    category_type_ids = load_schematic_category_type_ids()
    category_device_type_ids = load_schematic_category_device_type_ids()
    category_type_labels = {}
    category_device_labels = {}
    category_types_panel = StackPanel()

    def rebuild_category_type_pickers(sender=None, args=None):
        category_types_panel.Children.Clear()
        category_type_labels.clear()
        category_device_labels.clear()

        categories = parse_category_names(boxes["schematic_device_categories_text"].Text)

        if not categories:
            hint2 = TextBlock()
            hint2.Text = u"(нет категорий — заполните поле выше и нажмите «Обновить список»)"
            hint2.FontSize = 11
            hint2.Foreground = Brushes.Gray
            category_types_panel.Children.Add(hint2)
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
            value_label.Width = 300
            value_label.TextWrapping = TextWrapping.Wrap
            category_type_labels[name] = value_label

            pick_btn = Button()
            pick_btn.Content = u"Выбрать..."
            pick_btn.Padding = Thickness(8, 2, 8, 2)
            pick_btn.Margin = Thickness(8, 0, 0, 0)

            def on_pick_schematic(sender, args, name=name):
                schematic_categories = list(SCHEMATIC_CATEGORIES)
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

            # --- реальные типы устройств/панелей модели, относящиеся к категории ---

            label2 = TextBlock()
            label2.Text = u"Реальные типы устройств/панелей этой категории (в модели)"
            label2.Margin = Thickness(0, 6, 0, 2)
            category_types_panel.Children.Add(label2)

            row2 = StackPanel()
            row2.Orientation = Orientation.Horizontal

            device_ids = category_device_type_ids.get(name, [])
            device_label = TextBlock()
            device_label.Text = _type_names_display(doc, device_ids)
            device_label.VerticalAlignment = VerticalAlignment.Center
            device_label.Width = 300
            device_label.TextWrapping = TextWrapping.Wrap
            category_device_labels[name] = device_label

            pick_btn2 = Button()
            pick_btn2.Content = u"Выбрать..."
            pick_btn2.Padding = Thickness(8, 2, 8, 2)
            pick_btn2.Margin = Thickness(8, 0, 0, 0)

            def on_pick_devices(sender, args, name=name):
                source_categories = list(SCHEMATIC_SOURCE_CATEGORIES)
                symbols = list_used_symbols_by_categories(doc, source_categories)
                if not symbols:
                    forms.alert(u"В проекте нет размещённых экземпляров в категориях устройств/панелей СКС.")
                    return

                options = sorted([TypeOption(s) for s in symbols], key=lambda o: o.name)
                selected = forms.SelectFromList.show(
                    options,
                    title=u"Типы устройств/панелей для категории «{}»".format(name),
                    button_name=u"Выбрать",
                    multiselect=True
                )

                if selected is not None:
                    category_device_type_ids[name] = [str(o.symbol.Id.IntegerValue) for o in selected]
                    category_device_labels[name].Text = _type_names_display(doc, category_device_type_ids[name])

            pick_btn2.Click += on_pick_devices

            row2.Children.Add(device_label)
            row2.Children.Add(pick_btn2)
            category_types_panel.Children.Add(row2)

    for key, label_text, _, _, required, multiline in TEXT_FIELDS:
        section, plain_label = _split_section(label_text)

        if section != current_section:
            current_section = section
            section_title = TextBlock()
            section_title.Text = section if section else u"Параметры"
            section_title.FontWeight = FontWeights.Bold
            section_title.Margin = Thickness(0, 16, 0, 4)
            root.Children.Add(section_title)

            if section == u"Критерии панели" and not panel_criteria_hint_shown[0]:
                panel_criteria_hint_shown[0] = True
                panel_hint = TextBlock()
                panel_hint.Text = (
                    u"Это два независимых критерия одной и той же панели/шкафа. "
                    u"«Ключевые слова панелей» определяют, что считается панелью на "
                    u"плане — для расстановки узлов и как корень адресации (кнопки "
                    u"«Узлы трассы» и «Адреса узлов»). «Рабочий набор» отдельно "
                    u"определяет целевые панели категории «Электрооборудование», для "
                    u"которых строятся и считаются цепи (кнопка «Расчёт длины цепи»). "
                    u"Элемент должен подходить под ОБА критерия, иначе он может "
                    u"появиться на схеме узлом, но выпасть из расчёта цепей — или "
                    u"наоборот."
                )
                panel_hint.FontSize = 11
                panel_hint.Foreground = Brushes.Gray
                panel_hint.TextWrapping = TextWrapping.Wrap
                panel_hint.Margin = Thickness(0, 0, 0, 8)
                root.Children.Add(panel_hint)

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
            category_types_title.Text = u"Категории структурной схемы: семейства и устройства"
            category_types_title.FontWeight = FontWeights.Bold
            category_types_title.Margin = Thickness(0, 12, 0, 4)
            category_types_title.TextWrapping = TextWrapping.Wrap
            root.Children.Add(category_types_title)

            root.Children.Add(category_types_panel)
            rebuild_category_type_pickers()

    # --- проводник для цепей СКС (кнопка «Цепи СКС») ---

    conductor_section_title = TextBlock()
    conductor_section_title.Text = u"Проводник для цепей СКС"
    conductor_section_title.FontWeight = FontWeights.Bold
    conductor_section_title.Margin = Thickness(0, 16, 0, 4)
    root.Children.Add(conductor_section_title)

    conductor_hint = TextBlock()
    conductor_hint.Text = (
        u"Опционально: если задан «Параметр-признак строки справочника кабелей» "
        u"выше, здесь можно выбрать проводник из справочника — он будет "
        u"проставлен всем цепям, создаваемым кнопкой «Цепи СКС», без запроса "
        u"при каждом запуске."
    )
    conductor_hint.FontSize = 11
    conductor_hint.Foreground = Brushes.Gray
    conductor_hint.TextWrapping = TextWrapping.Wrap
    conductor_hint.Margin = Thickness(0, 0, 0, 8)
    root.Children.Add(conductor_hint)

    conductor_values = {key: values.get(key, "") for key, _ in CONDUCTOR_FIELDS}
    conductor_key, conductor_label_text = CONDUCTOR_FIELDS[0]

    conductor_row = StackPanel()
    conductor_row.Orientation = Orientation.Horizontal

    conductor_value_label = TextBlock()
    conductor_value_label.Text = _type_display_name(doc, conductor_values[conductor_key])
    conductor_value_label.VerticalAlignment = VerticalAlignment.Center
    conductor_value_label.Width = 300
    conductor_value_label.TextWrapping = TextWrapping.Wrap
    conductor_row.Children.Add(conductor_value_label)

    conductor_pick_btn = Button()
    conductor_pick_btn.Content = u"Выбрать..."
    conductor_pick_btn.Padding = Thickness(8, 2, 8, 2)
    conductor_pick_btn.Margin = Thickness(8, 0, 0, 0)

    def on_pick_conductor(sender, args):
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
            title=conductor_label_text,
            button_name=u"Выбрать",
            multiselect=False
        )

        if selected:
            conductor_values[conductor_key] = str(selected.wire_type.Id.IntegerValue)
            conductor_value_label.Text = selected.name

    conductor_pick_btn.Click += on_pick_conductor

    conductor_row.Children.Add(conductor_pick_btn)
    root.Children.Add(conductor_row)

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
        # Настройки общие на все кнопки SCS.panel — какие поля обязательны,
        # решает каждая кнопка сама через scs_settings.require() после
        # получения settings. Здесь просто сохраняем то, что введено.
        combined = {key: box.Text for key, box in boxes.items()}
        combined.update(type_values)
        combined.update(conductor_values)
        result["values"] = combined
        save_schematic_category_type_ids(category_type_ids)
        save_schematic_category_device_type_ids(category_device_type_ids)
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
