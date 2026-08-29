# -*- coding: utf-8 -*-
"""
Окно настроек параметров СОТ + их хранение между запусками.

Хранится в отдельном JSON-файле %APPDATA%\\pyRevit\\LowLifeSOT_settings.json
(тот же подход, что scs_settings.py/skud_settings.py — своя дисциплина,
свой файл, ничего общего с настройками СКС/СКУД).

В отличие от СКУД: сопоставление "категория устройства -> схемное
семейство" здесь без кабеля и без координат смещения (dx/dy) — раскладка
на схеме СОТ полностью автоматическая, сеткой по этажам/помещениям
(см. sot_schematic.py), а не "звездой" от контроллера.
"""

import os
import io
import json

import clr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('RevitAPI')

from Autodesk.Revit.DB import ElementId, BuiltInCategory, FilteredElementCollector, View, ViewType

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

from lowlife.params import get_string_param
from lowlife.skud import parse_category_names
from lowlife.scs_settings import list_symbols_by_categories, _safe_element_name, TypeOption

SETTINGS_FILE_NAME = "LowLifeSOT_settings.json"

# Категории реальных устройств СОТ, предлагаемых к выбору как "модель"
# (камеры — обычно OST_SecurityDevices; шкафы/АРМ — OST_ElectricalEquipment/
# OST_DataDevices, как в исходном FAMILY_MAP Dynamo-скрипта).
SOURCE_CATEGORIES = ("OST_SecurityDevices", "OST_ElectricalEquipment", "OST_DataDevices")

# Категория схемных семейств (детализация) — та же, что у СКУД.
SCHEMATIC_CATEGORIES = ("OST_DetailComponents",)

# Категория марки узла (аннотация "Обозначение, Адрес" над схемным семейством).
NODE_ANNOTATION_CATEGORIES = ("OST_DetailComponentTags",)

# (ключ, подпись) — тип, выбираемый из проекта (одиночный выбор, вне таблицы категорий).
TYPE_FIELDS = [
    ("node_annotation_type_id", u"Марка узла на схеме (тип «Обозначение, Адрес», ставится "
        u"над каждым схемным семейством)"),
    ("view_template_id", u"Шаблон вида для структурной схемы (необязательно — "
        u"применяется к виду при каждом запуске, «(не выбран)» — вид без шаблона)"),
]

# (ключ, подпись в окне, значение по умолчанию, обязательное ли поле, многострочное ли поле)
TEXT_FIELDS = [
    ("level_param_name", u"[Уровень] Параметр «Уровень» на устройстве (необязательно; "
        u"если пусто — берётся реальный уровень элемента). Имя уровня должно "
        u"содержать «Этаж N» и отметку вида «X,YYY» (может быть отрицательной "
        u"для подземных этажей) — по ним строится подпись и порядок этажей на схеме.",
        u"", False, False),
    ("room_param_name", u"[Параметры] Параметр, в который записываем помещение "
        u"(на устройстве и на схемном семействе)",
        u"", True, False),
    ("room_number_param_name", u"[Параметры] Параметр номера помещения в связанной модели "
        u"(используется, если параметр помещения на устройстве ещё пуст)",
        u"", True, False),
    ("address_param_name", u"[Параметры] Параметр, в который записываем адрес устройства "
        u"(на устройстве и на схемном семействе)",
        u"", True, False),
    ("building_param_name", u"[Схема] Параметр корпуса/секции на устройстве (необязательно — "
        u"нужен только вместе с полем «Значение корпуса/секции для фильтрации» ниже)",
        u"", False, False),
    ("building_filter_value", u"[Схема] Значение корпуса/секции для фильтрации (необязательно — "
        u"если параметр корпуса выше задан, а это поле пусто, схема строится по всем корпусам "
        u"сразу; чтобы ограничиться одним корпусом, впишите сюда его точное значение и задайте "
        u"для него своё имя вида выше — так у каждого корпуса будет свой отдельный вид)",
        u"", False, False),
    ("schematic_view_name", u"[Схема] Имя чертёжного вида структурной схемы (создаётся с этим "
        u"именем; при повторных запусках обновляется только вид с этим именем — чтобы вести "
        u"несколько схем параллельно, например по одной на корпус, задавайте разные имена)",
        u"Структурная схема СОТ", True, False),
    ("node_label_offset_mm", u"[Схема] Смещение марки узла вверх от точки вставки, мм",
        u"5", True, False),
    ("max_row_width_mm", u"[Схема] Максимальная ширина строки помещений на этаже, мм — "
        u"следующее помещение, которое уже не помещается в строку, переносится на новую "
        u"строку ниже (как перенос текста по словам, порядок помещений не меняется); "
        u"пусто или 0 — не ограничивать (одна строка на этаж, как раньше)",
        u"", False, False),
    ("layout_param_name", u"[Схема] Служебный параметр вида для хранения раскладки схемы "
        u"(текстовый, привязан к категории «Виды», JSON — не редактируется вручную)",
        u"", True, False),
    ("device_uid_param_name", u"[Схема] Служебный параметр схемного семейства для UniqueId "
        u"исходного устройства (текстовый, привязан к категории схемных семейств — нужен, "
        u"чтобы при повторном запуске узнавать «то же самое устройство»)",
        u"", True, False),
    ("schematic_device_categories_text", u"[Схема] Категории устройств схемы (по одной на строку)",
        u"", True, True),
    ("cabinet_category_name", u"[Схема] Категория «Шкаф» — устройство, к которому линиями "
        u"подключаются все остальные (необязательно; должно точно совпадать с одним из имён "
        u"в категориях устройств схемы выше; если пусто — линии не рисуются)",
        u"", False, False),
]

# {имя_категории: "id_типа"} — схемное семейство (OST_DetailComponents) для категории.
SCHEMATIC_CATEGORY_TYPES_KEY = "schematic_category_type_ids"

# {имя_категории: ["id_типа1", ...]} — реальные типы устройств модели этой категории.
SCHEMATIC_CATEGORY_DEVICE_TYPES_KEY = "schematic_category_device_type_ids"

MULTILINE_FIELDS = set(key for key, _, _, _req, multiline in TEXT_FIELDS if multiline)

PLAIN_LABELS = {}


def _split_section(label_text):
    """"[Раздел] Подпись" -> ("Раздел", "Подпись"); просто "Подпись" -> (None, "Подпись")."""
    if label_text.startswith(u"[") and u"]" in label_text:
        end = label_text.index(u"]")
        return label_text[1:end], label_text[end + 1:].strip()
    return None, label_text


for _key, _label, _default, _required, _multiline in TEXT_FIELDS:
    PLAIN_LABELS[_key] = _split_section(_label)[1]


def list_drafting_view_templates(doc):
    """Шаблоны видов, применимые к чертёжным видам (ViewType.DraftingView, IsTemplate)."""
    templates = []

    try:
        views = FilteredElementCollector(doc).OfClass(View).ToElements()
    except:
        return templates

    for view in views:
        try:
            if view.IsTemplate and view.ViewType == ViewType.DraftingView:
                templates.append(view)
        except:
            continue

    return templates


class ViewTemplateOption(object):
    """Обёртка над View-шаблоном для отображения в списке выбора (аналог TypeOption для семейств)."""

    def __init__(self, view):
        self.view = view
        self.name = _safe_element_name(view) or u"?"


def list_distinct_param_values(doc, builtin_categories, param_name):
    """
    Отсортированный список различных непустых значений параметра
    param_name среди размещённых экземпляров категорий — для пикера
    "Значение корпуса/секции для фильтрации" в окне настроек (чтобы не
    вписывать значение руками и не ошибиться в написании).
    """
    if not param_name:
        return []

    values = set()

    for bic in builtin_categories:
        try:
            instances = FilteredElementCollector(doc).OfCategory(bic).WhereElementIsNotElementType().ToElements()
        except:
            continue

        for el in instances:
            value = get_string_param(el, param_name)
            if value and value.strip():
                values.add(value.strip())

    return sorted(values)


def list_used_symbols_by_categories(doc, builtin_categories):
    """
    Только типы, у которых в проекте есть хотя бы один размещённый
    экземпляр — в отличие от scs_settings.list_symbols_by_categories
    (все загруженные типы, включая никогда не использованные), чтобы
    список выбора реальных устройств СОТ не засорялся типами, которых
    нет на модели. Для схемных семейств (ещё не вставленных на схему)
    по-прежнему используется list_symbols_by_categories.
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


def _type_names_display(doc, id_strs):
    """Отображаемое имя списка выбранных типов (id-строки) через "; ", либо "(не выбрано)"."""
    if not id_strs:
        return u"(не выбрано)"
    return u"; ".join(_type_display_name(doc, s) for s in id_strs)


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
        forms.alert(u"Не удалось сохранить настройки СОТ в файл:\n{}".format(path))


def load_saved_values():
    saved = _read_all()
    values = {}
    for key, _, default, _req, _multiline in TEXT_FIELDS:
        values[key] = saved.get(key, default)
    for key, _label in TYPE_FIELDS:
        values[key] = saved.get(key, "")
    return values


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


def load_schematic_category_type_ids():
    saved = _read_all()
    return dict(saved.get(SCHEMATIC_CATEGORY_TYPES_KEY, {}))


def load_schematic_category_device_type_ids():
    saved = _read_all()
    return dict(saved.get(SCHEMATIC_CATEGORY_DEVICE_TYPES_KEY, {}))


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


def to_runtime_settings(values):
    return dict(values)


def require(settings, keys):
    """
    Проверяет, что перечисленные ключи заполнены. Останавливает скрипт
    через forms.alert(exitscript=True), если чего-то не хватает.
    """
    missing = []

    for key in keys:
        value = settings.get(key)
        ok = bool(value and str(value).strip())
        if not ok:
            missing.append(PLAIN_LABELS.get(key, key))

    if missing:
        forms.alert(
            u"В настройках СОТ не заполнены обязательные для этой кнопки поля:\n\n{}\n\n"
            u"Запустите кнопку «Параметры СОТ» и заполните их там.".format(u"\n".join(missing)),
            exitscript=True
        )


def show_settings_form(doc, values):
    """
    Модальное окно редактирования настроек СОТ: текстовые параметры +
    таблица категорий (схемное семейство + реальные типы устройств,
    без кабеля и без координат). Возвращает словарь строковых значений
    или None, если пользователь отменил.
    """
    result = {"values": None}

    win = Window()
    win.Title = u"Настройки СОТ"
    win.Width = 600
    win.Height = 700
    win.WindowStartupLocation = WindowStartupLocation.CenterScreen

    outer = DockPanel()
    outer.LastChildFill = True

    root = StackPanel()
    root.Margin = Thickness(16)

    title = TextBlock()
    title.Text = u"Настройки параметров СОТ"
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

    # --- марка узла + шаблон вида (одиночный выбор каждое) ---

    type_values = {key: values.get(key, "") for key, _ in TYPE_FIELDS}
    type_labels = {}

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
                source_categories = [getattr(BuiltInCategory, key) for key in SOURCE_CATEGORIES]
                symbols = list_used_symbols_by_categories(doc, source_categories)
                if not symbols:
                    forms.alert(u"В проекте нет размещённых экземпляров в категориях устройств СОТ.")
                    return

                options = sorted([TypeOption(s) for s in symbols], key=lambda o: o.name)
                selected = forms.SelectFromList.show(
                    options,
                    title=u"Типы устройств для категории «{}»".format(name),
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

    for key, label_text, _default, required, multiline in TEXT_FIELDS:
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

        if key == "building_filter_value":
            pick_building_btn = Button()
            pick_building_btn.Content = u"Выбрать из модели..."
            pick_building_btn.Padding = Thickness(8, 2, 8, 2)
            pick_building_btn.HorizontalAlignment = HorizontalAlignment.Left
            pick_building_btn.Margin = Thickness(0, 4, 0, 0)

            def on_pick_building(sender, args):
                param_name = boxes["building_param_name"].Text.strip()
                if not param_name:
                    forms.alert(u"Сначала заполните поле «Параметр корпуса/секции на устройстве» выше.")
                    return

                source_categories = [getattr(BuiltInCategory, c) for c in SOURCE_CATEGORIES]
                values = list_distinct_param_values(doc, source_categories, param_name)
                if not values:
                    forms.alert(
                        u"В модели не нашлось ни одного устройства с заполненным "
                        u"параметром «{}».".format(param_name)
                    )
                    return

                selected = forms.SelectFromList.show(
                    values,
                    title=u"Значение корпуса/секции для фильтрации",
                    button_name=u"Выбрать",
                    multiselect=False
                )

                if selected:
                    boxes["building_filter_value"].Text = selected

            pick_building_btn.Click += on_pick_building
            root.Children.Add(pick_building_btn)

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

    required_hint = TextBlock()
    required_hint.Text = u"* обязательные поля — без них соответствующая кнопка не сможет найти элементы или записать параметры"
    required_hint.FontSize = 11
    required_hint.Foreground = Brushes.Gray
    required_hint.TextWrapping = TextWrapping.Wrap
    required_hint.Margin = Thickness(0, 10, 0, 0)
    root.Children.Add(required_hint)

    # --- кнопки ---

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
        for key, _label, default, _req, _multiline in TEXT_FIELDS:
            boxes[key].Text = default

    def on_ok(sender, args):
        combined = {key: box.Text for key, box in boxes.items()}
        combined.update(type_values)
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
    готовый к использованию словарь. Возвращает None, если пользователь
    нажал "Отмена".
    """
    saved = load_saved_values()
    edited = show_settings_form(doc, saved)

    if edited is None:
        return None

    save_values(edited)
    return to_runtime_settings(edited)


def get_settings_silent():
    """Настройки без показа окна — уже сохранённые значения (или значения по умолчанию)."""
    return to_runtime_settings(load_saved_values())
