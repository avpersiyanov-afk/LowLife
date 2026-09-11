# -*- coding: utf-8 -*-
"""
Окно настроек кнопки «Расстановка РМ, АМ, МДУ» (SPA.panel/PlaceCompanionDevices)
+ их хранение между запусками.

Хранится в отдельном JSON-файле %APPDATA%\\pyRevit\\LowLifeCompanionPlacement_settings.json
(см. _settings_file_path) — по образцу scs_settings.py/skud_settings.py
(простой файл вместо pyrevit.script.get_config(), см. их докстринги).

Устроено по образцу категорий структурной схемы СКУД (skud_settings.py,
рекурсивный rebuild списка категорий): пользователь вписывает в одно поле
через запятую произвольные ИМЕНА пар расстановки (например «РМ у дверей,
МДУ у клапанов») и жмёт «Обновить список» — под полем появляется по
разделу на каждое имя, где пикерами выбираются:

    базовые типы   — рядом с чем ставить (можно несколько типов сразу,
                     любой категории — двери, оборудование и т.п.);
    тип компаньона — что ставить (один тип);
    смещение       — вперёд/вбок/вверх в мм, в местных координатах
                     базового объекта (не зависит от его поворота на плане);
    параметры      — какие параметры перенести с базового объекта на
                     компаньон, формат "Источник=Приёмник, ..." (без "="
                     — имя параметра совпадает по обе стороны).

Конфигурация каждой пары сохраняется по её имени и не пропадает, если имя
временно убрать из списка (как и в skud_settings) — восстанавливается при
повторном добавлении того же имени.

Опционально на пару — группировка (галочка "Группировать по 2-4"):
    компаньон на группу — отдельный тип семейства с несколькими входами
                     (например, на 4), ставится один на группу вместо
                     обычного компаньона на каждый базовый объект;
    радиус группировки — базовые объекты считаются одной группой, если
                     стоят в одном помещении (Room текущего документа в
                     точке объекта) и в пределах этого радиуса друг от
                     друга (мм). Объекты без определяемого помещения или
                     без пары в группировке идут по обычному пути — им
                     ставится обычный компаньон, по одному на объект.
Значения параметров на компаньоне группы — источники со всех объектов
группы склеиваются через ", " в один и тот же приёмник (см.
companion_placement._expected_values_for_group).

Опционально на пару — цепь (галочка "Строить электрическую цепь..."):
сразу после расстановки строится электрическая цепь между компаньоном
(источник/панель, как изолятор у «Цепи изолятор-устройства») и его
базовым объектом (при поштучной расстановке) либо объектами группы (при
групповой) — см. lowlife.companion_placement.build_companion_circuits.

У некоторых компаньонов нужны СРАЗУ ДВЕ цепи разной категории с одним и
тем же базовым объектом (например силовая + сигнальная) — поэтому цепь
задаётся не одним типом, а двумя независимыми слотами «Цепь 1»/«Цепь 2»;
второй слот необязателен (пусто — строится только первая цепь). У каждого
слота свой тип цепи Revit (ElectricalSystemType) и свой кабель из
справочника (см. ниже); параметр цепи «Панель» и параметр цепи для кабеля
(«Проводник») — общие для обоих слотов пары.

Кабель для цепи выбирается из справочника кабелей документа — тем же
способом, что и в «Параметры цепей (общее)»/СКС: строки справочника
находятся по общему для ВСЕХ пар параметру-признаку («Параметр-признак
строки справочника кабелей», задаётся один раз вверху окна, а не на
каждую пару).
"""

import os
import io
import json

import clr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('RevitAPI')

from Autodesk.Revit.DB import FilteredElementCollector, Family, ElementId

from pyrevit import forms

from System.Windows import (
    Window, WindowStartupLocation, Thickness,
    FontWeights, HorizontalAlignment, VerticalAlignment, TextWrapping
)
from System.Windows.Controls import (
    StackPanel, TextBlock, TextBox, Button, CheckBox, Orientation, DockPanel, Dock,
    ScrollViewer, ScrollBarVisibility
)
from System.Windows.Media import Brushes

from lowlife import settings_transfer
from lowlife.scs_settings import (
    TypeOption, _type_display_name, _type_names_display,
    list_wire_catalog_items, WireTypeOption
)
from lowlife.generic_circuits_settings import SystemTypeOption, _available_system_type_names

SETTINGS_FILE_NAME = "LowLifeCompanionPlacement_settings.json"

# (ключ, подпись, значение по умолчанию) — числовые поля смещения одной пары.
OFFSET_FIELDS = [
    ("offset_forward_mm", u"Вперёд, мм", u"0"),
    ("offset_side_mm", u"Вбок, мм", u"0"),
    ("offset_up_mm", u"Вверх, мм", u"0"),
]

PLAIN_LABELS = {
    "pair_names_text": u"Названия пар расстановки",
}


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


def _split_names(text):
    seen = set()
    names = []
    for chunk in (text or u"").split(","):
        name = chunk.strip()
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names


def _parse_param_map(text):
    """"Источник=Приёмник, Источник2=Приёмник2" -> [(Источник, Приёмник), ...]."""
    pairs = []
    for chunk in (text or u"").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "=" in chunk:
            source, _, target = chunk.partition("=")
            source = source.strip()
            target = target.strip()
        else:
            source = target = chunk
        if source and target:
            pairs.append((source, target))
    return pairs


def _default_pair_values():
    values = {
        "base_symbol_ids": [],
        "companion_symbol_id": "",
        "param_map_text": u"",
        "group_enabled": False,
        "group_companion_symbol_id": "",
        "group_radius_mm": u"2000",
        "circuit_enabled": False,
        "circuit_panel_param": u"",
        "circuit_conductor_param": u"",
        "circuit_1_system_type": u"",
        "circuit_1_conductor_type_id": u"",
        "circuit_2_system_type": u"",
        "circuit_2_conductor_type_id": u"",
    }
    for key, _label, default in OFFSET_FIELDS:
        values[key] = default
    return values


def load_saved_values():
    """Строковые/сырые значения настроек: из JSON-файла, иначе — пусто."""
    saved = _read_all()
    values = {
        "pair_names_text": saved.get("pair_names_text", u""),
        "wire_catalog_marker_param": saved.get("wire_catalog_marker_param", u""),
    }

    pairs = {}
    for name, raw in (saved.get("pairs") or {}).items():
        pair = _default_pair_values()
        pair.update(raw or {})
        pairs[name] = pair
    values["pairs"] = pairs

    return values


def save_values(values):
    data = _read_all()
    data["pair_names_text"] = values["pair_names_text"]
    data["wire_catalog_marker_param"] = values["wire_catalog_marker_param"]
    data["pairs"] = values["pairs"]
    _write_all(data)


def list_all_symbols(doc):
    """
    Все загруженные в проект типоразмеры ЛЮБЫХ категорий (включая ещё не
    вставленные) — базовым объектом или компаньоном может быть что угодно
    (двери, оборудование, обобщённые модели...), поэтому в отличие от
    scs_settings.list_symbols_by_categories список не сужается по категории.
    """
    symbols = []
    for family in FilteredElementCollector(doc).OfClass(Family):
        for symbol_id in family.GetFamilySymbolIds():
            symbol = doc.GetElement(symbol_id)
            if symbol:
                symbols.append(symbol)
    return symbols


def to_runtime_settings(doc, values):
    """
    Готовые к использованию пары (только перечисленные в pair_names_text,
    в этом порядке): типы разрешены в реальные FamilySymbol, смещения — в
    float, параметры разобраны в список кортежей.
    """
    names = _split_names(values["pair_names_text"])
    pairs = values["pairs"]
    runtime_pairs = []

    for name in names:
        raw = pairs.get(name) or _default_pair_values()

        base_symbols = []
        for id_str in raw.get("base_symbol_ids") or []:
            try:
                symbol = doc.GetElement(ElementId(int(id_str)))
            except:
                symbol = None
            if symbol:
                base_symbols.append(symbol)

        companion_symbol = None
        companion_id = raw.get("companion_symbol_id")
        if companion_id:
            try:
                companion_symbol = doc.GetElement(ElementId(int(companion_id)))
            except:
                companion_symbol = None

        def _to_float(key, default=0.0):
            try:
                return float(raw.get(key) or default)
            except:
                return default

        group_companion_symbol = None
        group_companion_id = raw.get("group_companion_symbol_id")
        if group_companion_id:
            try:
                group_companion_symbol = doc.GetElement(ElementId(int(group_companion_id)))
            except:
                group_companion_symbol = None

        circuits = []
        for slot in (1, 2):
            system_type_name = (raw.get("circuit_{}_system_type".format(slot)) or u"").strip()
            if not system_type_name:
                continue
            conductor_id = raw.get("circuit_{}_conductor_type_id".format(slot))
            conductor_type_id = None
            if conductor_id:
                try:
                    conductor_type_id = ElementId(int(conductor_id))
                except:
                    conductor_type_id = None
            circuits.append({
                "system_type": system_type_name,
                "conductor_type_id": conductor_type_id,
            })

        runtime_pairs.append({
            "name": name,
            "base_symbols": base_symbols,
            "companion_symbol": companion_symbol,
            "offset_forward_mm": _to_float("offset_forward_mm"),
            "offset_side_mm": _to_float("offset_side_mm"),
            "offset_up_mm": _to_float("offset_up_mm"),
            "param_map": _parse_param_map(raw.get("param_map_text")),
            "group_enabled": bool(raw.get("group_enabled")),
            "group_companion_symbol": group_companion_symbol,
            "group_radius_mm": _to_float("group_radius_mm", 2000.0),
            "circuit_enabled": bool(raw.get("circuit_enabled")),
            "circuit_panel_param": (raw.get("circuit_panel_param") or u"").strip(),
            "circuit_conductor_param": (raw.get("circuit_conductor_param") or u"").strip(),
            "circuits": circuits,
        })

    return {"pairs": runtime_pairs}


def require_valid_pairs(runtime_settings):
    """
    Останавливает скрипт через forms.alert(exitscript=True), если нет ни
    одной полностью настроенной пары (базовые типы + тип компаньона).
    Возвращает список полностью настроенных пар (неполные — пропускаются
    молча в самих настройках, но каждая пара с указанным именем и хотя бы
    одним заполненным полем, но без второго, перечисляется отдельно).
    """
    valid = []
    incomplete = []
    group_misconfigured = []
    circuit_misconfigured = []

    for pair in runtime_settings["pairs"]:
        has_base = bool(pair["base_symbols"])
        has_companion = pair["companion_symbol"] is not None
        if has_base and has_companion:
            if pair["group_enabled"] and pair["group_companion_symbol"] is None:
                group_misconfigured.append(pair["name"])
                pair["group_enabled"] = False
            if pair["circuit_enabled"] and not pair["circuits"]:
                circuit_misconfigured.append(pair["name"])
                pair["circuit_enabled"] = False
            valid.append(pair)
        elif has_base or has_companion:
            incomplete.append(pair["name"])

    if group_misconfigured:
        forms.alert(
            u"У этих пар включена группировка, но не выбран «Компаньон на "
            u"группу» — для них группировка отключена, объекты расставятся "
            u"обычным компаньоном по одному:\n\n{}".format(u"\n".join(group_misconfigured))
        )

    if circuit_misconfigured:
        forms.alert(
            u"У этих пар включено построение цепи, но не выбран тип "
            u"электрической цепи ни в «Цепь 1», ни в «Цепь 2» — для них "
            u"цепь строиться не будет:\n\n{}".format(
                u"\n".join(circuit_misconfigured)
            )
        )

    if not valid:
        forms.alert(
            u"Не настроено ни одной пары расстановки.\n\n"
            u"Откройте настройки: Shift+клик по кнопке «Расстановка РМ, АМ, МДУ», "
            u"впишите название пары, нажмите «Обновить список» и заполните "
            u"«рядом с чем ставить» и «что ставим».",
            exitscript=True
        )

    if incomplete:
        forms.alert(
            u"У этих пар заполнено не всё (нужны и «рядом с чем ставить», и "
            u"«что ставим») — они пропущены:\n\n{}".format(u"\n".join(incomplete))
        )

    return valid


def show_settings_form(doc, values):
    """Модальное окно редактирования настроек. Возвращает словарь значений,
    None (Отмена) или settings_transfer.RELOAD (после загрузки из файла)."""
    result = {"values": None}

    win = Window()
    win.Title = u"Настройки: Расстановка РМ, АМ, МДУ"
    win.Width = 820
    win.Height = 640
    win.WindowStartupLocation = WindowStartupLocation.CenterScreen

    outer = DockPanel()
    outer.LastChildFill = True

    root = StackPanel()
    root.Margin = Thickness(16)

    title = TextBlock()
    title.Text = u"Пары «рядом с чем ставить -> что ставим»"
    title.FontSize = 16
    title.FontWeight = FontWeights.Bold
    title.Margin = Thickness(0, 0, 0, 4)
    root.Children.Add(title)

    hint = TextBlock()
    hint.Text = (
        u"Значения сохраняются и подставляются при следующих запусках. "
        u"Каждая пара — правило: рядом с базовым объектом ставится компаньон "
        u"со смещением и с переносом выбранных параметров."
    )
    hint.FontSize = 11
    hint.Foreground = Brushes.Gray
    hint.TextWrapping = TextWrapping.Wrap
    hint.Margin = Thickness(0, 0, 0, 10)
    root.Children.Add(hint)

    # --- параметр-признак строки справочника кабелей (общий на все пары) ---

    marker_label = TextBlock()
    marker_label.Text = (
        u"Параметр-признак строки справочника кабелей (нужен для выбора "
        u"кабеля у цепей ниже — общий на все пары)"
    )
    marker_label.TextWrapping = TextWrapping.Wrap
    marker_label.Margin = Thickness(0, 0, 0, 2)
    root.Children.Add(marker_label)

    marker_box = TextBox()
    marker_box.Text = values.get("wire_catalog_marker_param", u"")
    marker_box.Width = 360
    marker_box.HorizontalAlignment = HorizontalAlignment.Left
    marker_box.Padding = Thickness(4, 2, 4, 2)
    marker_box.Margin = Thickness(0, 0, 0, 10)
    root.Children.Add(marker_box)

    # --- строка имён пар ---

    names_label = TextBlock()
    names_label.Text = u"Названия пар расстановки, через запятую (например «РМ у дверей, МДУ у клапанов»)"
    names_label.TextWrapping = TextWrapping.Wrap
    names_label.Margin = Thickness(0, 4, 0, 2)
    root.Children.Add(names_label)

    names_row = StackPanel()
    names_row.Orientation = Orientation.Horizontal

    names_box = TextBox()
    names_box.Text = values.get("pair_names_text", u"")
    names_box.Width = 560
    names_box.Padding = Thickness(4, 2, 4, 2)
    names_row.Children.Add(names_box)

    refresh_btn = Button()
    refresh_btn.Content = u"Обновить список"
    refresh_btn.Padding = Thickness(8, 2, 8, 2)
    refresh_btn.Margin = Thickness(8, 0, 0, 0)
    names_row.Children.Add(refresh_btn)

    root.Children.Add(names_row)

    # значения пар живут в этом словаре весь сеанс редактирования,
    # независимо от того, показана пара сейчас в списке имён или нет —
    # временное удаление имени из строки не стирает уже введённые пикеры.
    pairs_state = {name: dict(pair) for name, pair in values.get("pairs", {}).items()}

    pairs_panel = StackPanel()

    def rebuild_pairs_panel(sender=None, args=None):
        pairs_panel.Children.Clear()

        names = _split_names(names_box.Text)

        if not names:
            empty_hint = TextBlock()
            empty_hint.Text = u"(нет пар — впишите имена выше и нажмите «Обновить список»)"
            empty_hint.FontSize = 11
            empty_hint.Foreground = Brushes.Gray
            pairs_panel.Children.Add(empty_hint)
            return

        for name in names:
            pair_values = pairs_state.setdefault(name, _default_pair_values())
            _build_pair_section(doc, pairs_panel, name, pair_values)

    def _build_pair_section(doc, container, name, pair_values):
        group_title = TextBlock()
        group_title.Text = u"Пара «{}»".format(name)
        group_title.FontWeight = FontWeights.Bold
        group_title.Margin = Thickness(0, 16, 0, 2)
        container.Children.Add(group_title)

        # --- базовые типы (рядом с чем ставить) ---

        base_label = TextBlock()
        base_label.Text = u"Рядом с чем ставить (базовые объекты — можно несколько типов)"
        base_label.Margin = Thickness(0, 4, 0, 2)
        container.Children.Add(base_label)

        base_row = StackPanel()
        base_row.Orientation = Orientation.Horizontal

        base_value_label = TextBlock()
        base_value_label.Text = _type_names_display(doc, pair_values.get("base_symbol_ids") or [])
        base_value_label.VerticalAlignment = VerticalAlignment.Center
        base_value_label.Width = 460
        base_value_label.TextWrapping = TextWrapping.Wrap
        base_row.Children.Add(base_value_label)

        base_pick_btn = Button()
        base_pick_btn.Content = u"Выбрать..."
        base_pick_btn.Padding = Thickness(8, 2, 8, 2)
        base_pick_btn.Margin = Thickness(8, 0, 0, 0)

        def on_pick_base(sender, args, pair_values=pair_values, base_value_label=base_value_label):
            symbols = list_all_symbols(doc)
            if not symbols:
                forms.alert(u"В проекте нет ни одного загруженного типа семейства.")
                return
            options = sorted([TypeOption(s) for s in symbols], key=lambda o: o.name)
            selected = forms.SelectFromList.show(
                options,
                title=u"Рядом с чем ставить — пара «{}» (уже выбрано: {})".format(
                    name, _type_names_display(doc, pair_values.get("base_symbol_ids") or [])
                ),
                button_name=u"Выбрать",
                multiselect=True
            )
            if selected is not None:
                pair_values["base_symbol_ids"] = [str(o.symbol.Id.IntegerValue) for o in selected]
                base_value_label.Text = _type_names_display(doc, pair_values["base_symbol_ids"])

        base_pick_btn.Click += on_pick_base
        base_row.Children.Add(base_pick_btn)
        container.Children.Add(base_row)

        # --- тип компаньона (что ставим) ---

        companion_label = TextBlock()
        companion_label.Text = u"Что ставим (компаньон — один тип)"
        companion_label.Margin = Thickness(0, 6, 0, 2)
        container.Children.Add(companion_label)

        companion_row = StackPanel()
        companion_row.Orientation = Orientation.Horizontal

        companion_value_label = TextBlock()
        companion_value_label.Text = _type_display_name(doc, pair_values.get("companion_symbol_id") or u"")
        companion_value_label.VerticalAlignment = VerticalAlignment.Center
        companion_value_label.Width = 460
        companion_value_label.TextWrapping = TextWrapping.Wrap
        companion_row.Children.Add(companion_value_label)

        companion_pick_btn = Button()
        companion_pick_btn.Content = u"Выбрать..."
        companion_pick_btn.Padding = Thickness(8, 2, 8, 2)
        companion_pick_btn.Margin = Thickness(8, 0, 0, 0)

        def on_pick_companion(sender, args, pair_values=pair_values, companion_value_label=companion_value_label):
            symbols = list_all_symbols(doc)
            if not symbols:
                forms.alert(u"В проекте нет ни одного загруженного типа семейства.")
                return
            options = sorted([TypeOption(s) for s in symbols], key=lambda o: o.name)
            selected = forms.SelectFromList.show(
                options,
                title=u"Что ставим — пара «{}»".format(name),
                button_name=u"Выбрать",
                multiselect=False
            )
            if selected:
                pair_values["companion_symbol_id"] = str(selected.symbol.Id.IntegerValue)
                companion_value_label.Text = selected.name

        companion_pick_btn.Click += on_pick_companion
        companion_row.Children.Add(companion_pick_btn)
        container.Children.Add(companion_row)

        # --- смещение ---

        offset_label = TextBlock()
        offset_label.Text = u"Смещение компаньона относительно базового объекта (в его местных координатах)"
        offset_label.TextWrapping = TextWrapping.Wrap
        offset_label.Margin = Thickness(0, 6, 0, 2)
        container.Children.Add(offset_label)

        offset_row = StackPanel()
        offset_row.Orientation = Orientation.Horizontal

        for key, label_text, default in OFFSET_FIELDS:
            field_col = StackPanel()
            field_col.Margin = Thickness(0, 0, 16, 0)

            field_label = TextBlock()
            field_label.Text = label_text
            field_label.FontSize = 11
            field_label.Foreground = Brushes.Gray
            field_col.Children.Add(field_label)

            field_box = TextBox()
            field_box.Text = pair_values.get(key, default)
            field_box.Width = 100
            field_box.Padding = Thickness(4, 2, 4, 2)
            field_col.Children.Add(field_box)

            def on_offset_changed(sender, args, pair_values=pair_values, key=key, field_box=field_box):
                pair_values[key] = field_box.Text

            field_box.TextChanged += on_offset_changed

            offset_row.Children.Add(field_col)

        container.Children.Add(offset_row)

        # --- параметры для переноса ---

        param_label = TextBlock()
        param_label.Text = (
            u"Параметры для переноса с базового объекта на компаньон: "
            u"«Источник=Приёмник, ...» (без «=» — имя совпадает с обеих сторон). "
            u"Нужен хотя бы один — иначе повторный запуск переставит компаньонов заново."
        )
        param_label.TextWrapping = TextWrapping.Wrap
        param_label.Margin = Thickness(0, 6, 0, 2)
        container.Children.Add(param_label)

        param_box = TextBox()
        param_box.Text = pair_values.get("param_map_text", u"")
        param_box.Width = 560
        param_box.HorizontalAlignment = HorizontalAlignment.Left
        param_box.Padding = Thickness(4, 2, 4, 2)

        def on_param_changed(sender, args, pair_values=pair_values, param_box=param_box):
            pair_values["param_map_text"] = param_box.Text

        param_box.TextChanged += on_param_changed
        container.Children.Add(param_box)

        # --- группировка по 2-4 (опционально) ---

        group_checkbox = CheckBox()
        group_checkbox.Content = (
            u"Группировать по 2-4 близких базовых объекта одного помещения — "
            u"ставить один компаньон на группу вместо компаньона на каждый"
        )
        group_checkbox.IsChecked = bool(pair_values.get("group_enabled"))
        group_checkbox.Margin = Thickness(0, 10, 0, 2)

        def on_group_toggle(sender, args, pair_values=pair_values, group_checkbox=group_checkbox):
            pair_values["group_enabled"] = bool(group_checkbox.IsChecked)

        group_checkbox.Checked += on_group_toggle
        group_checkbox.Unchecked += on_group_toggle
        container.Children.Add(group_checkbox)

        group_companion_label = TextBlock()
        group_companion_label.Text = u"Компаньон на группу (семейство с несколькими входами, например на 4)"
        group_companion_label.Margin = Thickness(0, 4, 0, 2)
        container.Children.Add(group_companion_label)

        group_companion_row = StackPanel()
        group_companion_row.Orientation = Orientation.Horizontal

        group_companion_value_label = TextBlock()
        group_companion_value_label.Text = _type_display_name(doc, pair_values.get("group_companion_symbol_id") or u"")
        group_companion_value_label.VerticalAlignment = VerticalAlignment.Center
        group_companion_value_label.Width = 460
        group_companion_value_label.TextWrapping = TextWrapping.Wrap
        group_companion_row.Children.Add(group_companion_value_label)

        group_companion_pick_btn = Button()
        group_companion_pick_btn.Content = u"Выбрать..."
        group_companion_pick_btn.Padding = Thickness(8, 2, 8, 2)
        group_companion_pick_btn.Margin = Thickness(8, 0, 0, 0)

        def on_pick_group_companion(sender, args, pair_values=pair_values, group_companion_value_label=group_companion_value_label):
            symbols = list_all_symbols(doc)
            if not symbols:
                forms.alert(u"В проекте нет ни одного загруженного типа семейства.")
                return
            options = sorted([TypeOption(s) for s in symbols], key=lambda o: o.name)
            selected = forms.SelectFromList.show(
                options,
                title=u"Компаньон на группу — пара «{}»".format(name),
                button_name=u"Выбрать",
                multiselect=False
            )
            if selected:
                pair_values["group_companion_symbol_id"] = str(selected.symbol.Id.IntegerValue)
                group_companion_value_label.Text = selected.name

        group_companion_pick_btn.Click += on_pick_group_companion
        group_companion_row.Children.Add(group_companion_pick_btn)
        container.Children.Add(group_companion_row)

        group_radius_label = TextBlock()
        group_radius_label.Text = u"Радиус группировки, мм (+ обязательно одно помещение — Room в точке базового объекта)"
        group_radius_label.TextWrapping = TextWrapping.Wrap
        group_radius_label.Margin = Thickness(0, 4, 0, 2)
        container.Children.Add(group_radius_label)

        group_radius_box = TextBox()
        group_radius_box.Text = pair_values.get("group_radius_mm", u"2000")
        group_radius_box.Width = 100
        group_radius_box.HorizontalAlignment = HorizontalAlignment.Left
        group_radius_box.Padding = Thickness(4, 2, 4, 2)

        def on_group_radius_changed(sender, args, pair_values=pair_values, group_radius_box=group_radius_box):
            pair_values["group_radius_mm"] = group_radius_box.Text

        group_radius_box.TextChanged += on_group_radius_changed
        container.Children.Add(group_radius_box)

        # --- цепь(и) между компаньоном и его базовым объектом(ами) (опционально) ---

        circuit_checkbox = CheckBox()
        circuit_checkbox.Content = (
            u"Строить электрическую цепь между компаньоном и его базовым "
            u"объектом (или объектами группы) сразу при расстановке — "
            u"компаньон становится источником/панелью, как изолятор в "
            u"«Цепи изолятор-устройства». Второй слот («Цепь 2») — для "
            u"компаньонов, которым к базовому объекту нужны СРАЗУ ДВЕ цепи "
            u"разной категории (например силовая + сигнальная); пусто — "
            u"строится только «Цепь 1»"
        )
        circuit_checkbox.IsChecked = bool(pair_values.get("circuit_enabled"))
        circuit_checkbox.Margin = Thickness(0, 10, 0, 2)

        def on_circuit_toggle(sender, args, pair_values=pair_values, circuit_checkbox=circuit_checkbox):
            pair_values["circuit_enabled"] = bool(circuit_checkbox.IsChecked)

        circuit_checkbox.Checked += on_circuit_toggle
        circuit_checkbox.Unchecked += on_circuit_toggle
        container.Children.Add(circuit_checkbox)

        def add_circuit_slot(slot_number, required_hint):
            type_key = "circuit_{}_system_type".format(slot_number)
            conductor_key = "circuit_{}_conductor_type_id".format(slot_number)

            slot_title = TextBlock()
            slot_title.Text = u"Цепь {}{}".format(slot_number, required_hint)
            slot_title.FontWeight = FontWeights.Bold
            slot_title.Margin = Thickness(0, 8, 0, 2)
            container.Children.Add(slot_title)

            type_label = TextBlock()
            type_label.Text = u"Тип электрической цепи Revit (ElectricalSystemType — «Выбрать...» справа)"
            type_label.TextWrapping = TextWrapping.Wrap
            type_label.Margin = Thickness(0, 2, 0, 2)
            container.Children.Add(type_label)

            type_row = StackPanel()
            type_row.Orientation = Orientation.Horizontal

            type_box = TextBox()
            type_box.Text = pair_values.get(type_key, u"")
            type_box.Width = 360
            type_box.Padding = Thickness(4, 2, 4, 2)
            type_row.Children.Add(type_box)

            def on_type_changed(sender, args, pair_values=pair_values, type_key=type_key, type_box=type_box):
                pair_values[type_key] = type_box.Text

            type_box.TextChanged += on_type_changed

            type_pick_btn = Button()
            type_pick_btn.Content = u"Выбрать..."
            type_pick_btn.Padding = Thickness(8, 2, 8, 2)
            type_pick_btn.Margin = Thickness(8, 0, 0, 0)

            def on_pick_type(sender, args, pair_values=pair_values, type_key=type_key, type_box=type_box):
                type_names = _available_system_type_names()
                if not type_names:
                    forms.alert(u"В этой версии Revit не нашлось значений ElectricalSystemType.")
                    return
                options = [SystemTypeOption(n) for n in type_names]
                selected = forms.SelectFromList.show(
                    options,
                    title=u"Тип электрической цепи {} (в скобках — пояснение) — пара «{}»".format(
                        slot_number, name
                    ),
                    button_name=u"Выбрать",
                    multiselect=False
                )
                if selected:
                    pair_values[type_key] = selected.system_type_name
                    type_box.Text = selected.system_type_name

            type_pick_btn.Click += on_pick_type
            type_row.Children.Add(type_pick_btn)
            container.Children.Add(type_row)

            conductor_label = TextBlock()
            conductor_label.Text = u"Кабель (строка справочника) для этой цепи — необязательно"
            conductor_label.TextWrapping = TextWrapping.Wrap
            conductor_label.Margin = Thickness(0, 4, 0, 2)
            container.Children.Add(conductor_label)

            conductor_row = StackPanel()
            conductor_row.Orientation = Orientation.Horizontal

            conductor_value_label = TextBlock()
            conductor_value_label.Text = _type_display_name(doc, pair_values.get(conductor_key) or u"")
            conductor_value_label.VerticalAlignment = VerticalAlignment.Center
            conductor_value_label.Width = 360
            conductor_value_label.TextWrapping = TextWrapping.Wrap
            conductor_row.Children.Add(conductor_value_label)

            conductor_pick_btn = Button()
            conductor_pick_btn.Content = u"Выбрать..."
            conductor_pick_btn.Padding = Thickness(8, 2, 8, 2)
            conductor_pick_btn.Margin = Thickness(8, 0, 0, 0)

            def on_pick_conductor(sender, args, pair_values=pair_values, conductor_key=conductor_key,
                                   conductor_value_label=conductor_value_label):
                marker_param_name = marker_box.Text.strip()
                if not marker_param_name:
                    forms.alert(u"Сначала заполните поле «Параметр-признак строки справочника кабелей» вверху окна.")
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
                    title=u"Кабель — цепь {}, пара «{}»".format(slot_number, name),
                    button_name=u"Выбрать",
                    multiselect=False
                )
                if selected:
                    pair_values[conductor_key] = str(selected.wire_type.Id.IntegerValue)
                    conductor_value_label.Text = selected.name

            conductor_pick_btn.Click += on_pick_conductor
            conductor_row.Children.Add(conductor_pick_btn)

            conductor_clear_btn = Button()
            conductor_clear_btn.Content = u"Очистить"
            conductor_clear_btn.Padding = Thickness(8, 2, 8, 2)
            conductor_clear_btn.Margin = Thickness(8, 0, 0, 0)

            def on_clear_conductor(sender, args, pair_values=pair_values, conductor_key=conductor_key,
                                    conductor_value_label=conductor_value_label):
                pair_values[conductor_key] = u""
                conductor_value_label.Text = _type_display_name(doc, u"")

            conductor_clear_btn.Click += on_clear_conductor
            conductor_row.Children.Add(conductor_clear_btn)
            container.Children.Add(conductor_row)

        add_circuit_slot(1, u" (обязательна, если галочка выше включена)")
        add_circuit_slot(2, u" (необязательно — вторая цепь другой категории к тому же базовому объекту)")

        circuit_panel_label = TextBlock()
        circuit_panel_label.Text = (
            u"Параметр цепи «Панель» — необязательно, общий для обеих цепей; "
            u"если задан, туда пишется имя компаньона"
        )
        circuit_panel_label.TextWrapping = TextWrapping.Wrap
        circuit_panel_label.Margin = Thickness(0, 8, 0, 2)
        container.Children.Add(circuit_panel_label)

        circuit_panel_box = TextBox()
        circuit_panel_box.Text = pair_values.get("circuit_panel_param", u"")
        circuit_panel_box.Width = 360
        circuit_panel_box.HorizontalAlignment = HorizontalAlignment.Left
        circuit_panel_box.Padding = Thickness(4, 2, 4, 2)

        def on_circuit_panel_changed(sender, args, pair_values=pair_values, circuit_panel_box=circuit_panel_box):
            pair_values["circuit_panel_param"] = circuit_panel_box.Text

        circuit_panel_box.TextChanged += on_circuit_panel_changed
        container.Children.Add(circuit_panel_box)

        circuit_conductor_param_label = TextBlock()
        circuit_conductor_param_label.Text = (
            u"Параметр цепи для кабеля (например «Проводник») — необязательно, общий для обеих цепей"
        )
        circuit_conductor_param_label.TextWrapping = TextWrapping.Wrap
        circuit_conductor_param_label.Margin = Thickness(0, 4, 0, 2)
        container.Children.Add(circuit_conductor_param_label)

        circuit_conductor_param_box = TextBox()
        circuit_conductor_param_box.Text = pair_values.get("circuit_conductor_param", u"")
        circuit_conductor_param_box.Width = 360
        circuit_conductor_param_box.HorizontalAlignment = HorizontalAlignment.Left
        circuit_conductor_param_box.Padding = Thickness(4, 2, 4, 2)

        def on_circuit_conductor_param_changed(sender, args, pair_values=pair_values,
                                                circuit_conductor_param_box=circuit_conductor_param_box):
            pair_values["circuit_conductor_param"] = circuit_conductor_param_box.Text

        circuit_conductor_param_box.TextChanged += on_circuit_conductor_param_changed
        container.Children.Add(circuit_conductor_param_box)

    refresh_btn.Click += rebuild_pairs_panel
    root.Children.Add(pairs_panel)
    rebuild_pairs_panel()

    # --- нижний ряд кнопок ---

    buttons = StackPanel()
    buttons.Orientation = Orientation.Horizontal
    buttons.HorizontalAlignment = HorizontalAlignment.Right
    buttons.Margin = Thickness(16, 8, 16, 12)
    DockPanel.SetDock(buttons, Dock.Bottom)

    cancel_btn = Button()
    cancel_btn.Content = u"Отмена"
    cancel_btn.Padding = Thickness(10, 4, 10, 4)
    cancel_btn.Margin = Thickness(0, 0, 8, 0)

    ok_btn = Button()
    ok_btn.Content = u"Сохранить"
    ok_btn.Padding = Thickness(10, 4, 10, 4)
    ok_btn.FontWeight = FontWeights.Bold

    def on_ok(sender, args):
        result["values"] = {
            "pair_names_text": names_box.Text,
            "wire_catalog_marker_param": marker_box.Text,
            "pairs": {name: dict(pair) for name, pair in pairs_state.items()},
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
        buttons, _read_all, _write_all, u"расстановки компаньонов", _on_settings_imported
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
    Показывает окно настроек, сохраняет введённые значения и возвращает их
    в готовом к использованию виде (см. to_runtime_settings). Возвращает
    None, если пользователь нажал «Отмена». Открывается по Shift+клику на
    кнопке «Расстановка РМ, АМ, МДУ».
    """
    while True:
        saved = load_saved_values()
        edited = show_settings_form(doc, saved)

        if edited == settings_transfer.RELOAD:
            continue

        if edited is None:
            return None

        save_values(edited)
        return to_runtime_settings(doc, edited)


def get_settings_silent(doc):
    """
    Настройки без показа окна — уже сохранённые значения (пары без имён —
    пустой список). Используется рабочей кнопкой «Расстановка РМ, АМ, МДУ».
    """
    return to_runtime_settings(doc, load_saved_values())
