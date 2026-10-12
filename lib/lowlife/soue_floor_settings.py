# -*- coding: utf-8 -*-
"""
Настройки кнопки «СОУЭ - расстановка типовой этаж»
(SOUE.panel/PlaceTypicalFloor) + их хранение между запусками.

Хранятся в JSON-файле %APPDATA%\\pyRevit\\LowLifeSOUEFloor_settings.json —
тот же подход, что у остальных кнопок (см. CLAUDE.md).

Окно Shift+клика (show_settings_window) — по образцу «СС1-8Mile»:
  - квартиры: семейство (выпадающий список с поиском) → тип, установка (на
    стену / на потолок) и высота от уровня;
  - остальные помещения: настенный оповещатель (семейство → тип, высота) и
    потолочный — для помещений с подвесным потолком (семейство → тип,
    высота — по потолку);
  - кнопка «Помещения объекта…» — таблица уникальных имён помещений
    (категория, уровень шума, «исключить»; soue_floor_rooms.py, хранится
    здесь же под ключом ROOM_TABLE_KEY);
  - кнопка «Параметры и отступы…» — типовое окно TextSettings (имена
    помещений квартир, параметр лота, параметры оповещателя SPL/мощность,
    отступы).
Исходные данные расчёта (превышение 15 дБ, ШДН 6 дБ, расчётная точка
1,5 м, шум по категориям) зашиты в soue_floor_core.
"""

from lowlife import settings_core
from lowlife import soue_floor_core as core


BUTTON_NAME = u"СОУЭ - расстановка типовой этаж"

SETTINGS = settings_core.TextSettings(
    file_name="LowLifeSOUEFloor_settings.json",
    button_name=BUTTON_NAME,
    heading=u"СОУЭ, типовой этаж: квартиры, параметры, отступы",
    transfer_label=u"СОУЭ (типовой этаж)",
    fields=[
        settings_core.TextField(
            "apartment_room_names",
            u"① Квартиры (помещения связи АР)",
            u"Где ставить оповещатель в квартире (через запятую, по приоритету)",
            hint=(
                u"В каждом лоте — один оповещатель в первом найденном помещении из "
                u"списка: «Прихожая, Холл» — в прихожей, а если её нет — в холле. У "
                u"двухуровневой квартиры — на нижнем уровне. Остальные помещения "
                u"квартиры не оснащаются."
            ),
            default=u"Прихожая", required=True,
        ),
        settings_core.TextField(
            "lot_param_name",
            u"",
            u"Параметр помещения «Имя лота»",
            hint=u"Лот, в котором есть помещение из списка выше, — квартира.",
            default=u"", required=True,
        ),
        settings_core.TextField(
            "spl_param_name",
            u"② Параметры оповещателя (типа или экземпляра)",
            u"Чувствительность SPL (1 Вт/1 м), дБ",
            hint=(
                u"Числовой или текстовый параметр («87», «87 дБ»). Берётся у типа, "
                u"иначе — у любого уже стоящего экземпляра этого типа."
            ),
            default=u"СОУЭ_Чувствительность",
        ),
        settings_core.TextField(
            "power_param_name",
            u"",
            u"Мощность подключения (отвод трансформатора), Вт",
            default=u"СОУЭ_Мощность",
        ),
        settings_core.NumberField(
            "fallback_spl_db",
            u"",
            u"SPL, если параметра нет, дБ",
            hint=u"Тогда в отчёт пишется предупреждение.",
            default=87.0, minimum=0,
        ),
        settings_core.NumberField(
            "fallback_power_w",
            u"",
            u"Мощность, если параметра нет, Вт",
            default=1.5, minimum=0,
        ),
        settings_core.NumberField(
            "wall_margin_mm",
            u"③ Расстановка",
            u"Отступ от углов стены, мм",
            default=300.0, minimum=0,
        ),
        settings_core.NumberField(
            "opening_clearance_mm",
            u"",
            u"Отступ от дверей и окон, мм (на стене)",
            hint=u"Считается от края проёма.",
            default=200.0, minimum=0,
        ),
        settings_core.NumberField(
            "level_tolerance_mm",
            u"",
            u"Допуск по высоте при сопоставлении уровней, мм",
            hint=u"Уровень помещения из связи АР совпадает с уровнем модели, если отметки отличаются не больше.",
            default=100.0, minimum=0,
        ),
        settings_core.TextField(
            "room_target_param",
            u"④ Запись в оборудование",
            u"Параметр экземпляра «Помещение»",
            hint=u"В квартирах пишется имя лота, в остальных — имя помещения. Пусто — ничего не пишется.",
            default=u"",
        ),
    ],
    width=760, height=640,
)

REQUIRED_KEYS = ["apartment_room_names", "lot_param_name"]

# Роль оповещателя → (ключ семейства, ключ типа, подпись).
SYMBOL_APARTMENT = "apartment"
SYMBOL_WALL = "wall"
SYMBOL_CEILING = "ceiling"
SYMBOL_KEYS = [
    (SYMBOL_APARTMENT, "apartment_family", "apartment_type", u"Квартиры"),
    (SYMBOL_WALL, "room_wall_family", "room_wall_type", u"Помещения — настенный"),
    (SYMBOL_CEILING, "room_ceiling_family", "room_ceiling_type",
     u"Помещения — потолочный (в подвесной потолок)"),
]

# Прочие значения главного окна: ключ → умолчание.
MAIN_DEFAULTS = {
    "apartment_mount": core.MOUNT_WALL,
    "apartment_height_mm": 2300.0,
    "room_wall_height_mm": 2500.0,
}

MOUNT_LABELS = [(core.MOUNT_WALL, u"На стену"), (core.MOUNT_CEILING, u"На потолок")]

# Таблица помещений объекта: {нормализованное имя: {name, category, noise, exclude}}.
ROOM_TABLE_KEY = "room_table"

load_saved_values = SETTINGS.load_saved_values


def _number(value, default):
    try:
        number = float(settings_core._text(value).strip().replace(u",", u"."))
    except Exception:
        return default
    return number if number >= 0 else default


def load_all():
    """Поля TextSettings + типы оповещателей, установка и высоты."""
    values = SETTINGS.load_saved_values()
    saved = SETTINGS.store.read()
    for _, family_key, type_key, _ in SYMBOL_KEYS:
        values[family_key] = saved.get(family_key) or u""
        values[type_key] = saved.get(type_key) or u""
    mount = saved.get("apartment_mount")
    values["apartment_mount"] = mount if mount in (core.MOUNT_WALL, core.MOUNT_CEILING) \
        else MAIN_DEFAULTS["apartment_mount"]
    for key in ("apartment_height_mm", "room_wall_height_mm"):
        values[key] = _number(saved.get(key, MAIN_DEFAULTS[key]), MAIN_DEFAULTS[key])
    return values


def load_room_table():
    """{ключ: core.RoomRow} из настроек."""
    return core.table_from_saved(SETTINGS.store.read().get(ROOM_TABLE_KEY))


def save_room_table(rows):
    """Сохраняет строки (дополняя/заменяя по имени) в таблицу помещений."""
    table = SETTINGS.store.read().get(ROOM_TABLE_KEY) or {}
    table.update(core.table_to_saved(rows))
    SETTINGS.store.update({ROOM_TABLE_KEY: table})


def configured(values, role):
    for key, family_key, type_key, _ in SYMBOL_KEYS:
        if key == role:
            return bool(values.get(family_key) and values.get(type_key))
    return False


def require_all(values):
    """Квартиры или настенный оповещатель выбраны, обязательные поля заполнены; иначе — выход."""
    if not configured(values, SYMBOL_APARTMENT) and not configured(values, SYMBOL_WALL):
        settings_core._alert(
            u"Не выбраны оповещатели: нужен тип для квартир и/или настенный тип для "
            u"остальных помещений.\n\n"
            u"Откройте настройки: Shift+клик по кнопке «{}».".format(BUTTON_NAME),
            exitscript=True
        )
    SETTINGS.require(values, REQUIRED_KEYS)


# ------------------------------------------------------------
# Окно Shift+клика
# ------------------------------------------------------------

def show_settings_window(doc):
    """
    Типы оповещателей, установка в квартирах, высоты; кнопки «Помещения
    объекта…» и «Параметры и отступы…». Сохраняет по «Сохранить»; True —
    сохранено.
    """
    import clr
    clr.AddReference('PresentationFramework')
    clr.AddReference('PresentationCore')

    from System.Windows import (
        Window, WindowStartupLocation, Thickness, FontWeights, HorizontalAlignment,
        TextWrapping, SizeToContent
    )
    from System.Windows.Controls import (
        StackPanel, TextBlock, TextBox, Button, ComboBox, Orientation, ScrollViewer,
        ScrollBarVisibility, DockPanel, Dock
    )
    from System.Windows.Media import Brushes

    from pyrevit import forms

    from lowlife import ss1_easy_core
    from lowlife.ss1_easy_settings import list_families

    values = load_all()
    families = list_families(doc)
    family_types = dict((name, types) for name, _, types in families)
    all_names = [name for name, _, _ in families]

    win = Window()
    win.Title = u"Настройки: {}".format(BUTTON_NAME)
    win.Width = 620
    win.SizeToContent = SizeToContent.Height
    win.MaxHeight = 900
    win.WindowStartupLocation = WindowStartupLocation.CenterScreen

    root = StackPanel()
    root.Margin = Thickness(16)
    scroll = ScrollViewer()
    scroll.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
    scroll.Content = root
    win.Content = scroll

    def add_text(text, bold=False, size=None, gray=False, top=0, bottom=0, parent=None):
        block = TextBlock()
        block.Text = text
        block.TextWrapping = TextWrapping.Wrap
        block.Margin = Thickness(0, top, 0, bottom)
        if bold:
            block.FontWeight = FontWeights.Bold
        if size:
            block.FontSize = size
        if gray:
            block.FontSize = 11
            block.Foreground = Brushes.Gray
        (parent or root).Children.Add(block)
        return block

    def add_combo(label):
        add_text(label, top=4)
        combo = ComboBox()
        combo.IsTextSearchEnabled = True
        root.Children.Add(combo)
        return combo

    def add_search_combo(label, names):
        """Список семейств с полем поиска слева (как в «СС1-8Mile»)."""
        add_text(label + u" — слева поиск по части имени", top=4)
        row = DockPanel()
        search = TextBox()
        search.Width = 170
        search.Padding = Thickness(2)
        search.Margin = Thickness(0, 0, 6, 0)
        search.ToolTip = u"Поиск: введите часть имени семейства (можно несколько слов)"
        DockPanel.SetDock(search, Dock.Left)
        row.Children.Add(search)
        combo = ComboBox()
        combo.IsTextSearchEnabled = True
        row.Children.Add(combo)
        root.Children.Add(row)
        found = add_text(u"", gray=True)

        def on_search(sender, args):
            current = combo.SelectedItem
            matches = ss1_easy_core.filter_names(names, search.Text)
            combo.Items.Clear()
            for name in matches:
                combo.Items.Add(name)
            if current in matches:
                combo.SelectedItem = current
            elif len(matches) == 1:
                combo.SelectedIndex = 0
            if (search.Text or u"").strip():
                found.Text = u"Найдено: {} из {}".format(len(matches), len(names))
            else:
                found.Text = u""

        search.TextChanged += on_search
        return combo

    def fill(combo, items, selected):
        combo.Items.Clear()
        for item in items:
            combo.Items.Add(item)
        if selected and selected in items:
            combo.SelectedItem = selected
        elif len(items) == 1:
            combo.SelectedIndex = 0

    def add_symbol_pick(family_value, type_value):
        family_combo = add_search_combo(u"Семейство", all_names)
        type_combo = add_combo(u"Тип")
        fill(family_combo, all_names, family_value)
        fill(type_combo, family_types.get(family_combo.SelectedItem, []), type_value)
        if family_value and family_value not in family_types:
            missing = add_text(u"Сохранённое семейство «{}» не загружено в проект.".format(
                family_value), gray=True)
            missing.Foreground = Brushes.IndianRed

        def on_family(sender, args):
            fill(type_combo, family_types.get(sender.SelectedItem, []), None)

        family_combo.SelectionChanged += on_family
        return family_combo, type_combo

    def add_height_row(label, value):
        row = StackPanel()
        row.Orientation = Orientation.Horizontal
        row.Margin = Thickness(0, 6, 0, 0)
        add_text(label, parent=row).Margin = Thickness(0, 3, 6, 0)
        box = TextBox()
        box.Width = 80
        box.Text = u"{:.0f}".format(float(value or 0.0))
        row.Children.Add(box)
        root.Children.Add(row)
        return row, box

    add_text(u"СОУЭ: оповещатели", bold=True, size=16, bottom=4)
    add_text(u"Списки — семейства, загруженные в проект. При запуске все экземпляры "
             u"выбранных типов на отмеченных уровнях удаляются и ставятся заново.",
             gray=True, bottom=4)

    symbol_combos = {}

    # --- квартиры ---
    add_text(u"Квартиры", bold=True, top=14)
    add_text(u"Один оповещатель на лот — в прихожей (список помещений — в «Параметрах»). "
             u"Не выбрано — квартиры не оснащаются.", gray=True)
    symbol_combos[SYMBOL_APARTMENT] = add_symbol_pick(
        values.get("apartment_family"), values.get("apartment_type"))
    row, apartment_height = add_height_row(u"Высота от уровня, мм:", values.get("apartment_height_mm"))
    add_text(u"Установка:", parent=row).Margin = Thickness(16, 3, 6, 0)
    mount_combo = ComboBox()
    mount_combo.Width = 130
    for _, label in MOUNT_LABELS:
        mount_combo.Items.Add(label)
    mount_combo.SelectedIndex = [key for key, _ in MOUNT_LABELS].index(values.get("apartment_mount"))
    row.Children.Add(mount_combo)

    # --- остальные помещения ---
    add_text(u"Остальные помещения — настенный", bold=True, top=14)
    add_text(u"Все помещения объекта вне квартир, кроме исключённых: количество и места — "
             u"по акустическому расчёту. По умолчанию — на стену.", gray=True)
    symbol_combos[SYMBOL_WALL] = add_symbol_pick(
        values.get("room_wall_family"), values.get("room_wall_type"))
    _, wall_height = add_height_row(u"Высота от уровня, мм:", values.get("room_wall_height_mm"))

    add_text(u"Остальные помещения — потолочный", bold=True, top=14)
    add_text(u"Если над помещением подвесной потолок (луч вверх по связям), ставится этот "
             u"тип в плоскость потолка. Не выбрано — везде настенный.", gray=True)
    symbol_combos[SYMBOL_CEILING] = add_symbol_pick(
        values.get("room_ceiling_family"), values.get("room_ceiling_type"))

    # --- кнопки дополнительных окон ---
    def add_button(text, hint):
        btn = Button()
        btn.Content = text
        btn.Padding = Thickness(10, 4, 10, 4)
        btn.Margin = Thickness(0, 16, 0, 0)
        btn.HorizontalAlignment = HorizontalAlignment.Left
        root.Children.Add(btn)
        add_text(hint, gray=True, top=2)
        return btn

    rooms_btn = add_button(
        u"Помещения объекта: шум и исключения…",
        u"Уникальные имена помещений всех связей: категория и уровень шума (справочник "
        u"расчёта), «исключить». Выгрузка в Excel и загрузка обратно.")
    other_btn = add_button(
        u"Параметры и отступы…",
        u"Помещения квартир, параметр имени лота, параметры оповещателя (SPL, мощность), "
        u"отступы от углов и проёмов, параметр «Помещение».")

    def on_rooms(sender, args):
        from lowlife import soue_floor_rooms
        soue_floor_rooms.edit_all_rooms(doc)

    def on_other(sender, args):
        # Окно без Topmost — дочернее окно не застрянет позади (см. CLAUDE.md).
        SETTINGS.get_settings_interactive()

    rooms_btn.Click += on_rooms
    other_btn.Click += on_other

    buttons = StackPanel()
    buttons.Orientation = Orientation.Horizontal
    buttons.HorizontalAlignment = HorizontalAlignment.Right
    buttons.Margin = Thickness(0, 16, 0, 0)
    root.Children.Add(buttons)

    cancel_btn = Button()
    cancel_btn.Content = u"Отмена"
    cancel_btn.Padding = Thickness(10, 4, 10, 4)
    cancel_btn.Margin = Thickness(0, 0, 8, 0)
    buttons.Children.Add(cancel_btn)

    ok_btn = Button()
    ok_btn.Content = u"Сохранить"
    ok_btn.Padding = Thickness(10, 4, 10, 4)
    ok_btn.FontWeight = FontWeights.Bold
    buttons.Children.Add(ok_btn)

    result = {"saved": False}

    def on_ok(sender, args):
        update = {}
        problems = []
        for role, family_key, type_key, label in SYMBOL_KEYS:
            family_combo, type_combo = symbol_combos[role]
            update[family_key] = family_combo.SelectedItem or u""
            update[type_key] = type_combo.SelectedItem or u""
            if bool(update[family_key]) != bool(update[type_key]):
                problems.append(u"{}: выберите и семейство, и тип (или ни того, ни другого)".format(label))
        for box, key, label in ((apartment_height, "apartment_height_mm", u"Квартиры: высота"),
                                (wall_height, "room_wall_height_mm", u"Настенный: высота")):
            number = _number(box.Text, None)
            if number is None:
                problems.append(u"{} — нужно неотрицательное число".format(label))
            else:
                update[key] = number
        update["apartment_mount"] = MOUNT_LABELS[max(0, mount_combo.SelectedIndex)][0]
        if not problems and not (configured(update, SYMBOL_APARTMENT) or configured(update, SYMBOL_WALL)):
            problems.append(u"Выберите тип для квартир и/или настенный тип для остальных помещений")
        if problems:
            forms.alert(u"Исправьте:\n\n" + u"\n".join(problems))
            return
        SETTINGS.store.update(update)
        result["saved"] = True
        win.Close()

    def on_cancel(sender, args):
        win.Close()

    ok_btn.Click += on_ok
    cancel_btn.Click += on_cancel

    win.ShowDialog()
    return result["saved"]
