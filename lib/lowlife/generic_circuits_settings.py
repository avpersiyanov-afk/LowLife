# -*- coding: utf-8 -*-
"""
Окно настроек кнопки «Цепь (общее)» (CircuitsGeneric.panel) + их хранение
между запусками.

Хранится в отдельном JSON-файле %APPDATA%\\pyRevit\\LowLifeGeneric_settings.json
(см. _settings_file_path) — по образцу scs_settings.py, но набор полей свой
и намеренно маленький: тип цепи, кабель, и правило заполнения параметра
цепи «Имя нагрузки».

В отличие от кнопок «Цепи СКС/СКУД/СПА» здесь ничего не зашито в код —
всё берётся отсюда:
    circuit_system_type      — имя типа электрической цепи Revit
                               (ElectricalSystemType: "Data", "Security"…);
    wire_catalog_marker_param — параметр-признак строки справочника кабелей
                               (нужен, чтобы показать список кабелей для
                               выбора ниже — то же соглашение, что в СКС);
    conductor_type_id         — выбранная строка справочника кабелей
                               (ElementId строкой), необязательно;
    conductor_param_name      — параметр цепи, куда пишется кабель
                               (по умолчанию «Проводник»);
    load_name_param           — параметр цепи «Имя нагрузки»;
    load_name_source_params   — список параметров подключаемого устройства
                               (через запятую, по порядку), из которых
                               собирается имя нагрузки; один параметр в
                               списке = одиночный источник;
    load_name_separator       — разделитель между значениями параметров;
    circuit_mode              — "per_device" (отдельная цепь на каждое
                               устройство) или "single" (все устройства в
                               одну цепь; имя нагрузки не заполняется).
"""

import os
import io
import json

import clr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('RevitAPI')

from Autodesk.Revit.DB import ElementId
from Autodesk.Revit.DB.Electrical import ElectricalSystemType

from pyrevit import forms

from System.Windows import (
    Window, WindowStartupLocation, Thickness,
    FontWeights, HorizontalAlignment, VerticalAlignment, TextWrapping
)
from System.Windows.Controls import (
    StackPanel, TextBlock, TextBox, Button, Orientation, DockPanel, Dock,
    ScrollViewer, ScrollBarVisibility, RadioButton
)
from System.Windows.Media import Brushes

from lowlife import settings_transfer
from lowlife.scs_settings import list_wire_catalog_items, WireTypeOption, _type_display_name

SETTINGS_FILE_NAME = "LowLifeGeneric_settings.json"

# (ключ, подпись, значение по умолчанию, список ли это через запятую,
#  обязательное ли поле, многострочное ли поле)
TEXT_FIELDS = [
    ("circuit_system_type", u"Тип электрической цепи (имя ElectricalSystemType Revit — «Выбрать…» справа)",
        u"Data", False, True, False),
    ("wire_catalog_marker_param", u"Параметр-признак строки справочника кабелей (нужен для выбора кабеля ниже)",
        u"", False, False, False),
    ("conductor_param_name", u"Параметр цепи для кабеля (проводник)",
        u"Проводник", False, True, False),
    ("load_name_param", u"Параметр цепи «Имя нагрузки»",
        u"Имя нагрузки", False, True, False),
    ("load_name_source_params", u"Параметры устройства для имени нагрузки (через запятую, по порядку; "
        u"для каждого сначала берётся параметр экземпляра, затем — типа)",
        u"", True, False, False),
    ("load_name_separator", u"Разделитель между значениями параметров имени нагрузки",
        u".", False, False, False),
]

# (ключ, подпись) — строка справочника кабелей (см. list_wire_catalog_items),
# выбирается пикером; хранится строкой ElementId, как conductor_type_id в СКС.
CONDUCTOR_FIELDS = [
    ("conductor_type_id", u"Кабель (строка справочника) для цепей — необязательно"),
]

MODE_KEY = "circuit_mode"
MODE_PER_DEVICE = "per_device"
MODE_SINGLE = "single"
MODE_DEFAULT = MODE_PER_DEVICE

# Не разделять и не стрипить: разделитель имени нагрузки может намеренно
# содержать пробелы (", "), поэтому load_name_separator в LIST_FIELDS не
# входит и через _split_list не проходит.
LIST_FIELDS = set(key for key, _, _, is_list, _req, _ml in TEXT_FIELDS if is_list)

PLAIN_LABELS = {}
for _key, _label, _default, _is_list, _required, _multiline in TEXT_FIELDS:
    PLAIN_LABELS[_key] = _label
for _key, _label in CONDUCTOR_FIELDS:
    PLAIN_LABELS[_key] = _label


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
        forms.alert(u"Не удалось сохранить настройки в файл:\n{}".format(path))


def load_saved_values():
    """Строковые значения настроек: из JSON-файла, иначе — значения по умолчанию."""
    saved = _read_all()
    values = {}

    for key, _, default, _, _, _ in TEXT_FIELDS:
        values[key] = saved.get(key, default)

    for key, _ in CONDUCTOR_FIELDS:
        values[key] = saved.get(key, "")

    values[MODE_KEY] = saved.get(MODE_KEY, MODE_DEFAULT)

    return values


def save_values(values):
    data = _read_all()
    data.update(values)
    _write_all(data)


def _split_list(text):
    return [x.strip() for x in text.split(",") if x.strip()]


def to_runtime_settings(values):
    """Преобразует строковые значения формы в готовые к использованию (списки разобраны из строк)."""
    settings = dict(values)
    for key in LIST_FIELDS:
        settings[key] = _split_list(values.get(key, u""))
    return settings


def require(settings, keys):
    """
    Проверяет, что перечисленные ключи заполнены (после to_runtime_settings).
    Останавливает скрипт через forms.alert(exitscript=True), если чего-то
    не хватает.
    """
    missing = []

    for key in keys:
        value = settings.get(key)

        if isinstance(value, list):
            ok = len(value) > 0
        else:
            ok = bool(value and unicode(value).strip())

        if not ok:
            missing.append(PLAIN_LABELS.get(key, key))

    if missing:
        forms.alert(
            u"В настройках «Параметры цепей (общее)» не заполнены обязательные поля:\n\n{}\n\n"
            u"Запустите кнопку «Параметры цепей (общее)» и заполните их там.".format(u"\n".join(missing)),
            exitscript=True
        )


# Русские пояснения к значениям ElectricalSystemType Revit — только для
# показа в списке выбора («Data (данные)»). В настройках и в API Revit
# (resolve_system_type -> getattr(ElectricalSystemType, ...)) хранится и
# используется по-прежнему исходное английское имя.
SYSTEM_TYPE_RU = {
    u"UndefinedSystemType": u"не определён",
    u"Data": u"данные",
    u"Communication": u"связь",
    u"Controls": u"управление",
    u"FireAlarm": u"пожарная сигнализация",
    u"NurseCall": u"вызов персонала",
    u"Security": u"охранная",
    u"Telephone": u"телефон",
    u"PowerCircuit": u"силовая",
    u"PowerBalanced": u"силовая сбалансированная",
    u"PowerUnBalanced": u"силовая несбалансированная",
}


class SystemTypeOption(object):
    """
    Обёртка над именем ElectricalSystemType для списка выбора: .name —
    отображаемая строка с русским пояснением («Data (данные)»),
    .system_type_name — исходное английское имя, которое и попадёт в
    настройки.
    """

    def __init__(self, name):
        self.system_type_name = name
        ru = SYSTEM_TYPE_RU.get(name)
        self.name = u"{} ({})".format(name, ru) if ru else name

    def __str__(self):
        return self.name


def _available_system_type_names():
    """
    Имена доступных в этой версии Revit значений ElectricalSystemType
    (Data, Security, Communication…) — те же, что предлагает
    manual_circuits.pick_system_type. Унаследованные от Enum методы
    (CompareTo, Parse…) отсекаются через isinstance.
    """
    return sorted(
        a for a in dir(ElectricalSystemType)
        if not a.startswith("_")
        and isinstance(getattr(ElectricalSystemType, a, None), ElectricalSystemType)
    )


def show_settings_form(doc, values):
    """
    Модальное окно редактирования настроек кнопки «Цепь (общее)».
    Возвращает словарь строковых значений, None (Отмена) или
    settings_transfer.RELOAD (после загрузки настроек из файла).
    """
    result = {"values": None}

    win = Window()
    win.Title = u"Настройки «Цепь (общее)»"
    win.Width = 760
    win.Height = 600
    win.WindowStartupLocation = WindowStartupLocation.CenterScreen

    outer = DockPanel()
    outer.LastChildFill = True

    root = StackPanel()
    root.Margin = Thickness(16)

    title = TextBlock()
    title.Text = u"Настройки кнопки «Цепь (общее)»"
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

    def add_text_field(key, label_text, default):
        label = TextBlock()
        label.Text = label_text
        label.TextWrapping = TextWrapping.Wrap
        label.Margin = Thickness(0, 10, 0, 2)
        root.Children.Add(label)

        row = StackPanel()
        row.Orientation = Orientation.Horizontal

        box = TextBox()
        box.Text = values.get(key, default)
        box.Width = 560
        box.Padding = Thickness(4, 2, 4, 2)
        boxes[key] = box
        row.Children.Add(box)

        if key == "circuit_system_type":
            pick_btn = Button()
            pick_btn.Content = u"Выбрать…"
            pick_btn.Padding = Thickness(8, 2, 8, 2)
            pick_btn.Margin = Thickness(8, 0, 0, 0)

            def on_pick_type(sender, args):
                names = _available_system_type_names()
                if not names:
                    forms.alert(u"В этой версии Revit не нашлось значений ElectricalSystemType.")
                    return
                options = [SystemTypeOption(n) for n in names]
                selected = forms.SelectFromList.show(
                    options,
                    title=u"Тип электрической цепи (в скобках — пояснение)",
                    button_name=u"Выбрать",
                    multiselect=False
                )
                if selected:
                    boxes["circuit_system_type"].Text = selected.system_type_name

            pick_btn.Click += on_pick_type
            row.Children.Add(pick_btn)

        root.Children.Add(row)

    for key, label_text, default, _is_list, _required, _multiline in TEXT_FIELDS:
        add_text_field(key, label_text, default)

    # --- кабель (строка справочника) ---

    conductor_title = TextBlock()
    conductor_title.Text = u"Кабель для цепей"
    conductor_title.FontWeight = FontWeights.Bold
    conductor_title.Margin = Thickness(0, 16, 0, 4)
    root.Children.Add(conductor_title)

    conductor_hint = TextBlock()
    conductor_hint.Text = (
        u"Необязательно: если выше задан «Параметр-признак строки справочника "
        u"кабелей», здесь можно выбрать кабель — он будет проставлен в параметр "
        u"цепи (по умолчанию «Проводник») всем цепям, создаваемым кнопкой, без "
        u"запроса при каждом запуске."
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
    conductor_value_label.Width = 400
    conductor_value_label.TextWrapping = TextWrapping.Wrap
    conductor_row.Children.Add(conductor_value_label)

    conductor_pick_btn = Button()
    conductor_pick_btn.Content = u"Выбрать…"
    conductor_pick_btn.Padding = Thickness(8, 2, 8, 2)
    conductor_pick_btn.Margin = Thickness(8, 0, 0, 0)

    def on_pick_conductor(sender, args):
        marker_param_name = boxes["wire_catalog_marker_param"].Text.strip()
        if not marker_param_name:
            forms.alert(u"Сначала заполните поле «Параметр-признак строки справочника кабелей».")
            return

        wire_items = list_wire_catalog_items(doc, marker_param_name)
        if not wire_items:
            forms.alert(
                u"Не найдено строк справочника кабелей (ни один элемент документа "
                u"не содержит одновременно «Ключевое имя» и параметр «{}»).".format(marker_param_name)
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

    conductor_clear_btn = Button()
    conductor_clear_btn.Content = u"Очистить"
    conductor_clear_btn.Padding = Thickness(8, 2, 8, 2)
    conductor_clear_btn.Margin = Thickness(8, 0, 0, 0)

    def on_clear_conductor(sender, args):
        conductor_values[conductor_key] = ""
        conductor_value_label.Text = _type_display_name(doc, "")

    conductor_clear_btn.Click += on_clear_conductor
    conductor_row.Children.Add(conductor_clear_btn)

    root.Children.Add(conductor_row)

    # --- режим: одна цепь на всех / отдельная цепь на устройство ---

    mode_title = TextBlock()
    mode_title.Text = u"Как строить цепи"
    mode_title.FontWeight = FontWeights.Bold
    mode_title.Margin = Thickness(0, 16, 0, 4)
    root.Children.Add(mode_title)

    current_mode = values.get(MODE_KEY, MODE_DEFAULT)

    rb_per_device = RadioButton()
    rb_per_device.Content = u"Отдельная электрическая цепь на каждое устройство (у каждой — своё имя нагрузки по маске)"
    rb_per_device.GroupName = u"generic_circuit_mode"
    rb_per_device.Margin = Thickness(0, 2, 0, 2)
    rb_per_device.IsChecked = (current_mode != MODE_SINGLE)
    root.Children.Add(rb_per_device)

    rb_single = RadioButton()
    rb_single.Content = u"Все устройства в одну общую электрическую цепь (имя нагрузки не заполняется)"
    rb_single.GroupName = u"generic_circuit_mode"
    rb_single.Margin = Thickness(0, 2, 0, 2)
    rb_single.IsChecked = (current_mode == MODE_SINGLE)
    root.Children.Add(rb_single)

    required_hint = TextBlock()
    required_hint.Text = (
        u"Тип цепи, параметр кабеля и параметр «Имя нагрузки» обязательны. "
        u"Список параметров устройства и кабель — по желанию: если список пуст, "
        u"«Имя нагрузки» не заполняется; если кабель не выбран — не проставляется."
    )
    required_hint.FontSize = 11
    required_hint.Foreground = Brushes.Gray
    required_hint.TextWrapping = TextWrapping.Wrap
    required_hint.Margin = Thickness(0, 12, 0, 0)
    root.Children.Add(required_hint)

    # --- нижний ряд кнопок ---

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
        for key, _, default, _, _, _ in TEXT_FIELDS:
            boxes[key].Text = default
        conductor_values[conductor_key] = ""
        conductor_value_label.Text = _type_display_name(doc, "")
        rb_per_device.IsChecked = True

    def on_ok(sender, args):
        combined = {key: box.Text for key, box in boxes.items()}
        combined.update(conductor_values)
        combined[MODE_KEY] = MODE_SINGLE if rb_single.IsChecked else MODE_PER_DEVICE
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

    def _on_settings_imported():
        result["values"] = settings_transfer.RELOAD
        win.Close()

    settings_transfer.add_transfer_buttons(
        buttons, _read_all, _write_all, u"Общие цепи", _on_settings_imported
    )

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
    готовый словарь (списки разобраны из строк). Возвращает None, если
    пользователь нажал «Отмена». Используется только кнопкой
    «Параметры цепей (общее)».
    """
    while True:
        saved = load_saved_values()
        edited = show_settings_form(doc, saved)

        if edited == settings_transfer.RELOAD:
            continue

        if edited is None:
            return None

        save_values(edited)
        return to_runtime_settings(edited)


def get_settings_silent():
    """
    Настройки без показа окна — уже сохранённые значения (или значения по
    умолчанию). Используется рабочей кнопкой «Цепь (общее)».
    """
    return to_runtime_settings(load_saved_values())
