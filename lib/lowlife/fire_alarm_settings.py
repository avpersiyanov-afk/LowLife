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

from Autodesk.Revit.DB import ElementId, BuiltInCategory

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
from lowlife.skud import parse_category_names
from lowlife.scs_settings import (
    list_generic_model_symbols, _safe_element_name, TypeOption,
    list_wire_catalog_items, WireTypeOption, _type_display_name,
    list_symbols_by_categories
)
from lowlife.sot_settings import (
    SCHEMATIC_CATEGORIES, NODE_ANNOTATION_CATEGORIES, list_used_symbols_by_categories,
    list_drafting_view_templates, ViewTemplateOption
)

SYSTEMS = {
    "SPS": {
        "file": "LowLifeSPS_settings.json",
        "title": u"СПС",
        # Шлейф СПС — цепь пожарной сигнализации, а не слаботочная Data.
        "defaults": {
            "circuit_system_type": u"FireAlarm",
            "schematic_view_name": u"Структурная схема СПС",
        },
    },
    "SOUE": {
        "file": "LowLifeSOUE_settings.json",
        "title": u"СОУЭ",
        # У СОУЭ тип зависит от того, как заведены семейства в проекте:
        # оповещатели бывают и в пожарной цепи, и в силовой. Дефолт —
        # тот же FireAlarm, при необходимости меняется в настройках.
        "defaults": {
            "circuit_system_type": u"FireAlarm",
            "schematic_view_name": u"Структурная схема СОУЭ",
        },
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


# Категории Revit, среди которых ищутся реальные устройства структурной
# схемы (для автосбора на схеме и для списка выбора в пикере реальных
# типов устройств ниже) — пожарная сигнализация и электрооборудование
# (панели, изоляторы), как и просил пользователь. Сами категории СХЕМЫ
# (логические группы вроде "извещатель"/"панель") при этом вводятся
# текстом в schematic_device_categories_text — как в СОТ/СКУД, а не
# зашиты кодом: одна категория схемы может объединять несколько типов
# устройств из разных Revit-категорий этого списка.
SCHEMATIC_SOURCE_CATEGORIES = ("OST_FireAlarmDevices", "OST_ElectricalEquipment")


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

    # --- линии проводки ---
    ("wire_line_family_filter", u"[Линии проводки] Ключевое слово в имени семейства линии "
        u"провода (line-based Generic Model, как в СКС)",
        u"", False, False),
    ("wire_mark_param", u"[Линии проводки] Параметр линии «Марка» (пишется номер/имя цепи)",
        u"", False, False),

    # --- структурная схема ---
    ("level_param_name", u"[Структурная схема] Параметр «Уровень» на устройстве (необязательно; "
        u"если пусто — берётся реальный уровень элемента). Имя уровня должно содержать "
        u"«Этаж N» и отметку вида «X,YYY» (может быть отрицательной для подземных этажей) — "
        u"по ним строится подпись и порядок этажей на схеме.",
        u"", False, False),
    ("room_param_name", u"[Структурная схема] Параметр, в который записываем помещение "
        u"(на устройстве и на схемном семействе)",
        u"", False, True),
    ("room_number_param_name", u"[Структурная схема] Параметр номера помещения в связанной "
        u"модели (используется, если параметр помещения на устройстве ещё пуст)",
        u"", False, True),
    ("schematic_view_name", u"[Структурная схема] Имя чертёжного вида структурной схемы "
        u"(создаётся с этим именем; при повторных запусках обновляется только вид с этим именем)",
        u"Структурная схема", False, True),
    ("node_label_offset_mm", u"[Структурная схема] Смещение марки узла вверх от точки вставки, мм",
        u"5", False, True),
    ("layout_param_name", u"[Структурная схема] Служебный параметр вида для хранения раскладки "
        u"схемы (текстовый, привязан к категории «Виды», JSON — не редактируется вручную)",
        u"", False, True),
    ("device_uid_param_name", u"[Структурная схема] Служебный параметр схемного семейства для "
        u"UniqueId исходного устройства (текстовый, привязан к категории схемных семейств — "
        u"нужен, чтобы при повторном запуске узнавать «то же самое устройство»)",
        u"", False, True),
    ("schematic_device_categories_text", u"[Структурная схема] Категории устройств схемы (по одной на строку)",
        u"", False, True),
]

TYPE_FIELDS = [
    ("node_annotation_type_id", u"Марка узла на структурной схеме (тип «Обозначение, Адрес», "
        u"ставится над каждым схемным семейством)"),
    ("view_template_id", u"Шаблон вида для структурной схемы (необязательно — применяется к "
        u"виду при каждом запуске, «(не выбран)» — вид без шаблона)"),
]

# {int(BuiltInCategory): "id_строки_справочника_кабелей"} — тип проводника
# по категории устройства (DEVICE_CATEGORIES), отдельный ключ в JSON
# настроек системы, не в TEXT_FIELDS (выбирается пикером, не текстом).
CATEGORY_WIRE_TYPES_KEY = "category_wire_type_ids"

# {имя_категории (из schematic_device_categories_text): "id_типа"} —
# схемное семейство (OST_DetailComponents) для категории структурной схемы.
SCHEMATIC_CATEGORY_TYPES_KEY = "schematic_category_type_ids"

# {имя_категории: ["id_типа1", ...]} — реальные типы устройств модели этой
# категории, попадающие на структурную схему.
SCHEMATIC_CATEGORY_DEVICE_TYPES_KEY = "schematic_category_device_type_ids"

LIST_FIELDS = set(key for key, _, _, is_list, _req in TEXT_FIELDS if is_list)
MULTILINE_FIELDS = set(["schematic_device_categories_text"])


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

    for key, _label in TYPE_FIELDS:
        values[key] = saved.get(key, "")

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


def get_node_annotation_symbol(doc, settings):
    """FamilySymbol марки узла (node_annotation_type_id из настроек) или None, если не выбран/не найден."""
    id_str = settings.get("node_annotation_type_id")
    if not id_str:
        return None

    try:
        return doc.GetElement(ElementId(int(id_str)))
    except:
        return None


def get_view_template(doc, settings):
    """Шаблон вида (view_template_id из настроек) или None, если не выбран/не найден."""
    id_str = settings.get("view_template_id")
    if not id_str:
        return None

    try:
        return doc.GetElement(ElementId(int(id_str)))
    except:
        return None


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
    """{имя_категории: set(int)} — id реальных типов устройств категории."""
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


def _type_names_display(doc, id_strs):
    """Отображаемое имя списка выбранных типов (id-строки) через "; ", либо "(не выбрано)"."""
    if not id_strs:
        return u"(не выбрано)"
    return u"; ".join(_type_display_name(doc, s) for s in id_strs)


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

    # --- тип марки узла структурной схемы (одиночный выбор) ---

    type_values = dict((key, values.get(key, "")) for key, _ in TYPE_FIELDS)
    type_labels = {}

    if TYPE_FIELDS:
        type_section_title = TextBlock()
        type_section_title.Text = u"Марка узла и шаблон вида"
        type_section_title.FontWeight = FontWeights.Bold
        type_section_title.Margin = Thickness(0, 0, 0, 4)
        root.Children.Add(type_section_title)

    for key, label_text in TYPE_FIELDS:
        label = TextBlock()
        label.Text = label_text
        label.Margin = Thickness(0, 8, 0, 2)
        label.TextWrapping = TextWrapping.Wrap
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

        def on_pick_type(sender, args, key=key):
            if key == "view_template_id":
                templates = list_drafting_view_templates(doc)
                if not templates:
                    forms.alert(u"В проекте нет шаблонов вида, применимых к чертёжным видам.")
                    return

                options = sorted([ViewTemplateOption(v) for v in templates], key=lambda o: o.name)
                selected = forms.SelectFromList.show(
                    options,
                    title=u"Шаблон вида для структурной схемы",
                    button_name=u"Выбрать",
                    multiselect=False
                )

                if selected:
                    type_values[key] = str(selected.view.Id.IntegerValue)
                    type_labels[key].Text = selected.name
                return

            annotation_categories = [getattr(BuiltInCategory, c) for c in NODE_ANNOTATION_CATEGORIES]
            symbols = list_symbols_by_categories(doc, annotation_categories)
            if not symbols:
                forms.alert(u"В проекте нет типов категории «Марки элементов узла».")
                return

            options = sorted([TypeOption(s) for s in symbols], key=lambda o: o.name)
            selected = forms.SelectFromList.show(
                options,
                title=u"Марка узла",
                button_name=u"Выбрать",
                multiselect=False
            )

            if selected:
                type_values[key] = str(selected.symbol.Id.IntegerValue)
                type_labels[key].Text = selected.name

        pick_btn.Click += on_pick_type

        row.Children.Add(value_label)
        row.Children.Add(pick_btn)
        root.Children.Add(row)

    boxes = {}
    current_section = None

    schematic_category_type_ids = load_schematic_category_type_ids()
    schematic_category_device_type_ids = load_schematic_category_device_type_ids()
    schematic_category_type_labels = {}
    schematic_category_device_labels = {}
    schematic_category_types_panel = StackPanel()

    def rebuild_schematic_category_pickers(sender=None, args=None):
        schematic_category_types_panel.Children.Clear()
        schematic_category_type_labels.clear()
        schematic_category_device_labels.clear()

        categories = parse_category_names(boxes["schematic_device_categories_text"].Text)

        if not categories:
            hint2 = TextBlock()
            hint2.Text = u"(нет категорий — заполните поле выше и нажмите «Обновить список»)"
            hint2.FontSize = 11
            hint2.Foreground = Brushes.Gray
            schematic_category_types_panel.Children.Add(hint2)
            return

        for name in categories:
            group_title = TextBlock()
            group_title.Text = u"Категория «{}»".format(name)
            group_title.FontWeight = FontWeights.Bold
            group_title.Margin = Thickness(0, 12, 0, 2)
            schematic_category_types_panel.Children.Add(group_title)

            # --- схемное семейство для вставки ---

            label = TextBlock()
            label.Text = u"Схемное семейство (для вставки)"
            label.Margin = Thickness(0, 4, 0, 2)
            schematic_category_types_panel.Children.Add(label)

            row = StackPanel()
            row.Orientation = Orientation.Horizontal

            value_label = TextBlock()
            value_label.Text = _type_display_name(doc, schematic_category_type_ids.get(name, ""))
            value_label.VerticalAlignment = VerticalAlignment.Center
            value_label.Width = 300
            value_label.TextWrapping = TextWrapping.Wrap
            schematic_category_type_labels[name] = value_label

            pick_btn = Button()
            pick_btn.Content = u"Выбрать..."
            pick_btn.Padding = Thickness(8, 2, 8, 2)
            pick_btn.Margin = Thickness(8, 0, 0, 0)

            def on_pick_schematic(sender, args, name=name):
                schematic_categories = [getattr(BuiltInCategory, key) for key in SCHEMATIC_CATEGORIES]
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
                    schematic_category_type_ids[name] = str(selected.symbol.Id.IntegerValue)
                    schematic_category_type_labels[name].Text = selected.name

            pick_btn.Click += on_pick_schematic

            row.Children.Add(value_label)
            row.Children.Add(pick_btn)
            schematic_category_types_panel.Children.Add(row)

            # --- реальные типы устройств модели, относящиеся к категории ---

            label2 = TextBlock()
            label2.Text = u"Реальные типы устройств этой категории (в модели)"
            label2.Margin = Thickness(0, 6, 0, 2)
            schematic_category_types_panel.Children.Add(label2)

            row2 = StackPanel()
            row2.Orientation = Orientation.Horizontal

            device_ids = schematic_category_device_type_ids.get(name, [])
            device_label = TextBlock()
            device_label.Text = _type_names_display(doc, device_ids)
            device_label.VerticalAlignment = VerticalAlignment.Center
            device_label.Width = 300
            device_label.TextWrapping = TextWrapping.Wrap
            schematic_category_device_labels[name] = device_label

            pick_btn2 = Button()
            pick_btn2.Content = u"Выбрать..."
            pick_btn2.Padding = Thickness(8, 2, 8, 2)
            pick_btn2.Margin = Thickness(8, 0, 0, 0)

            def on_pick_devices(sender, args, name=name):
                source_categories = [getattr(BuiltInCategory, key) for key in SCHEMATIC_SOURCE_CATEGORIES]
                symbols = list_used_symbols_by_categories(doc, source_categories)
                if not symbols:
                    forms.alert(u"В проекте нет размещённых экземпляров в категориях устройств структурной схемы.")
                    return

                options = sorted([TypeOption(s) for s in symbols], key=lambda o: o.name)
                selected = forms.SelectFromList.show(
                    options,
                    title=u"Типы устройств для категории «{}»".format(name),
                    button_name=u"Выбрать",
                    multiselect=True
                )

                if selected is not None:
                    schematic_category_device_type_ids[name] = [str(o.symbol.Id.IntegerValue) for o in selected]
                    schematic_category_device_labels[name].Text = _type_names_display(
                        doc, schematic_category_device_type_ids[name]
                    )

            pick_btn2.Click += on_pick_devices

            row2.Children.Add(device_label)
            row2.Children.Add(pick_btn2)
            schematic_category_types_panel.Children.Add(row2)

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

        if key == "schematic_device_categories_text":
            refresh_btn = Button()
            refresh_btn.Content = u"Обновить список категорий ниже"
            refresh_btn.Padding = Thickness(8, 2, 8, 2)
            refresh_btn.HorizontalAlignment = HorizontalAlignment.Left
            refresh_btn.Margin = Thickness(0, 4, 0, 0)
            refresh_btn.Click += rebuild_schematic_category_pickers
            root.Children.Add(refresh_btn)

            schematic_category_types_title = TextBlock()
            schematic_category_types_title.Text = u"Категории структурной схемы: семейства и устройства"
            schematic_category_types_title.FontWeight = FontWeights.Bold
            schematic_category_types_title.Margin = Thickness(0, 12, 0, 4)
            schematic_category_types_title.TextWrapping = TextWrapping.Wrap
            root.Children.Add(schematic_category_types_title)

            root.Children.Add(schematic_category_types_panel)
            rebuild_schematic_category_pickers()

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
        combined = {key: box.Text for key, box in boxes.items()}
        combined.update(type_values)
        result["values"] = combined
        save_category_wire_type_ids(category_wire_type_ids)
        save_schematic_category_type_ids(schematic_category_type_ids)
        save_schematic_category_device_type_ids(schematic_category_device_type_ids)
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
