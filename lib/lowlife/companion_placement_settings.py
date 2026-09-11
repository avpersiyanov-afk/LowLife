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
групповой) — см. lowlife.companion_placement.build_companion_circuit.
Нужен тип цепи Revit (ElectricalSystemType); параметр цепи «Панель» —
опционален (если задан, туда пишется имя компаньона).
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
from lowlife.scs_settings import TypeOption, _type_display_name, _type_names_display
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
        "circuit_system_type": u"",
        "circuit_panel_param": u"",
    }
    for key, _label, default in OFFSET_FIELDS:
        values[key] = default
    return values


def load_saved_values():
    """Строковые/сырые значения настроек: из JSON-файла, иначе — пусто."""
    saved = _read_all()
    values = {"pair_names_text": saved.get("pair_names_text", u"")}

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
            "circuit_system_type": (raw.get("circuit_system_type") or u"").strip(),
            "circuit_panel_param": (raw.get("circuit_panel_param") or u"").strip(),
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
            if pair["circuit_enabled"] and not pair["circuit_system_type"]:
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
            u"У этих пар включено построение цепи, но не выбран «Тип "
            u"электрической цепи» — для них цепь строиться не будет:\n\n{}".format(
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

        # --- цепь между компаньоном и его базовым объектом(ами) (опционально) ---

        circuit_checkbox = CheckBox()
        circuit_checkbox.Content = (
            u"Строить электрическую цепь между компаньоном и его базовым "
            u"объектом (или объектами группы) сразу при расстановке — "
            u"компаньон становится источником/панелью, как изолятор в "
            u"«Цепи изолятор-устройства»"
        )
        circuit_checkbox.IsChecked = bool(pair_values.get("circuit_enabled"))
        circuit_checkbox.Margin = Thickness(0, 10, 0, 2)

        def on_circuit_toggle(sender, args, pair_values=pair_values, circuit_checkbox=circuit_checkbox):
            pair_values["circuit_enabled"] = bool(circuit_checkbox.IsChecked)

        circuit_checkbox.Checked += on_circuit_toggle
        circuit_checkbox.Unchecked += on_circuit_toggle
        container.Children.Add(circuit_checkbox)

        circuit_type_label = TextBlock()
        circuit_type_label.Text = u"Тип электрической цепи Revit (ElectricalSystemType — «Выбрать...» справа)"
        circuit_type_label.TextWrapping = TextWrapping.Wrap
        circuit_type_label.Margin = Thickness(0, 4, 0, 2)
        container.Children.Add(circuit_type_label)

        circuit_type_row = StackPanel()
        circuit_type_row.Orientation = Orientation.Horizontal

        circuit_type_box = TextBox()
        circuit_type_box.Text = pair_values.get("circuit_system_type", u"")
        circuit_type_box.Width = 360
        circuit_type_box.Padding = Thickness(4, 2, 4, 2)
        circuit_type_row.Children.Add(circuit_type_box)

        def on_circuit_type_changed(sender, args, pair_values=pair_values, circuit_type_box=circuit_type_box):
            pair_values["circuit_system_type"] = circuit_type_box.Text

        circuit_type_box.TextChanged += on_circuit_type_changed

        circuit_type_pick_btn = Button()
        circuit_type_pick_btn.Content = u"Выбрать..."
        circuit_type_pick_btn.Padding = Thickness(8, 2, 8, 2)
        circuit_type_pick_btn.Margin = Thickness(8, 0, 0, 0)

        def on_pick_circuit_type(sender, args, pair_values=pair_values, circuit_type_box=circuit_type_box):
            names = _available_system_type_names()
            if not names:
                forms.alert(u"В этой версии Revit не нашлось значений ElectricalSystemType.")
                return
            options = [SystemTypeOption(n) for n in names]
            selected = forms.SelectFromList.show(
                options,
                title=u"Тип электрической цепи (в скобках — пояснение) — пара «{}»".format(name),
                button_name=u"Выбрать",
                multiselect=False
            )
            if selected:
                pair_values["circuit_system_type"] = selected.system_type_name
                circuit_type_box.Text = selected.system_type_name

        circuit_type_pick_btn.Click += on_pick_circuit_type
        circuit_type_row.Children.Add(circuit_type_pick_btn)
        container.Children.Add(circuit_type_row)

        circuit_panel_label = TextBlock()
        circuit_panel_label.Text = (
            u"Параметр цепи «Панель» — необязательно; если задан, туда пишется имя компаньона"
        )
        circuit_panel_label.TextWrapping = TextWrapping.Wrap
        circuit_panel_label.Margin = Thickness(0, 4, 0, 2)
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
