# -*- coding: utf-8 -*-
"""
Настройки кнопки «СОУЭ — расстановка типовой этаж»
(SOUE.panel/PlaceTypicalFloor) + их хранение между запусками.

Хранятся в JSON-файле %APPDATA%\\pyRevit\\LowLifeSOUEFloor_settings.json —
тот же подход, что у остальных кнопок (см. CLAUDE.md).

Окно Shift+клика (show_settings_window) — по образцу «СС1-8Mile»: для
каждой роли (квартиры, коридоры МОП, лифтовые холлы) — семейство
(выпадающий список с поиском) → тип, способ установки (на стену / на
потолок) и высота от уровня; кнопка открывает типовое окно остальных
полей (settings_core.TextSettings: имена помещений, параметры, шаг,
отступы). Имена семейств и параметров — соглашение проекта, умолчания у
них пустые; имена помещений и высоты — общая лексика, с умолчаниями.
"""

from lowlife import settings_core
from lowlife import soue_floor_core as core


BUTTON_NAME = u"СОУЭ - расстановка типовой этаж"

SETTINGS = settings_core.TextSettings(
    file_name="LowLifeSOUEFloor_settings.json",
    button_name=BUTTON_NAME,
    heading=u"СОУЭ, типовой этаж: помещения, параметры, отступы",
    transfer_label=u"СОУЭ (типовой этаж)",
    fields=[
        settings_core.TextField(
            "apartment_room_names",
            u"① Помещения (в связи АР)",
            u"Квартира: где ставить оповещатель (через запятую, по приоритету)",
            hint=(
                u"В каждом лоте — один оповещатель в первом найденном помещении из "
                u"списка: «Прихожая, Холл» — в прихожей, а если её нет — в холле. У "
                u"двухуровневой квартиры — на нижнем уровне."
            ),
            default=u"Прихожая", required=True,
        ),
        settings_core.TextField(
            "corridor_room_names",
            u"",
            u"Коридоры МОП (через запятую)",
            hint=u"Помещения с такими именами внутри квартиры (с её именем лота) пропускаются.",
            default=u"Коридор, Коридор МОП, Поэтажный коридор",
        ),
        settings_core.TextField(
            "lift_hall_room_names",
            u"",
            u"Лифтовые холлы (через запятую)",
            default=u"Лифтовой холл, Лифтовый холл",
        ),
        settings_core.TextField(
            "lot_param_name",
            u"",
            u"Параметр помещения «Имя лота»",
            default=u"", required=True,
        ),
        settings_core.NumberField(
            "mop_step_m",
            u"② Расстановка",
            u"Шаг оповещателей в коридорах и холлах МОП, м",
            hint=(
                u"Помещение делится на клетки не больше шага, в каждой — оповещатель. "
                u"0 — один на помещение."
            ),
            default=0.0, minimum=0,
        ),
        settings_core.NumberField(
            "wall_margin_mm",
            u"",
            u"Отступ от углов стены, мм",
            default=300.0, minimum=0,
        ),
        settings_core.NumberField(
            "opening_clearance_mm",
            u"",
            u"Отступ от дверей и окон, мм (на стене)",
            hint=u"Считается от края проёма; если вся стена занята — ставится в ближайшую точку.",
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
            u"③ Запись в оборудование",
            u"Параметр экземпляра «Помещение»",
            hint=u"В квартирах пишется имя лота, в МОП — имя помещения. Пусто — ничего не пишется.",
            default=u"",
        ),
    ],
    width=760, height=640,
)

REQUIRED_KEYS = ["apartment_room_names", "lot_param_name"]

# Роль → (ключ семейства, ключ типа, ключ установки, ключ высоты, подпись,
# установка по умолчанию, высота по умолчанию)
ROLE_KEYS = [
    (core.ROLE_APARTMENT, "apartment_family", "apartment_type", "apartment_mount",
     "apartment_height_mm", u"Квартиры", core.MOUNT_WALL, 2300.0),
    (core.ROLE_CORRIDOR, "corridor_family", "corridor_type", "corridor_mount",
     "corridor_height_mm", u"Коридоры (МОП)", core.MOUNT_WALL, 2300.0),
    (core.ROLE_LIFT_HALL, "lift_hall_family", "lift_hall_type", "lift_hall_mount",
     "lift_hall_height_mm", u"Лифтовые холлы", core.MOUNT_WALL, 2300.0),
]

MOUNT_LABELS = [(core.MOUNT_WALL, u"На стену"), (core.MOUNT_CEILING, u"На потолок")]

load_saved_values = SETTINGS.load_saved_values


def _number(value, default):
    try:
        number = float(settings_core._text(value).strip().replace(u",", u"."))
    except Exception:
        return default
    return number if number >= 0 else default


def load_all():
    """Поля TextSettings + семейство/тип/установка/высота каждой роли."""
    values = SETTINGS.load_saved_values()
    saved = SETTINGS.store.read()
    for _, family_key, type_key, mount_key, height_key, _, mount, height in ROLE_KEYS:
        values[family_key] = saved.get(family_key) or u""
        values[type_key] = saved.get(type_key) or u""
        values[mount_key] = saved.get(mount_key) if saved.get(mount_key) in (
            core.MOUNT_WALL, core.MOUNT_CEILING) else mount
        values[height_key] = _number(saved.get(height_key, height), height)
    return values


def configured_roles(values):
    """Роли, у которых выбраны семейство и тип (их помещения оснащаются)."""
    return [role for role, family_key, type_key, _, _, _, _, _ in ROLE_KEYS
            if values.get(family_key) and values.get(type_key)]


def require_all(values):
    """Хотя бы одна роль настроена и обязательные поля заполнены; иначе — выход."""
    if not configured_roles(values):
        settings_core._alert(
            u"Не выбрано ни одного оповещателя (семейство и тип для квартир, "
            u"коридоров или лифтовых холлов).\n\n"
            u"Откройте настройки: Shift+клик по кнопке «{}».".format(BUTTON_NAME),
            exitscript=True
        )
    SETTINGS.require(values, REQUIRED_KEYS)


# ------------------------------------------------------------
# Окно Shift+клика
# ------------------------------------------------------------

def show_settings_window(doc):
    """
    Для каждой роли: семейство → тип, установка, высота; кнопка «Помещения,
    параметры и отступы…». Сохраняет по «Сохранить»; True — сохранено.
    Роль без семейства и типа не оснащается.
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

    add_text(u"СОУЭ: оповещатели типового этажа", bold=True, size=16, bottom=4)
    add_text(u"Списки — семейства, загруженные в проект. Роль без семейства и типа "
             u"не оснащается. При запуске все экземпляры выбранных типов на отмеченных "
             u"уровнях удаляются и ставятся заново.", gray=True, bottom=4)

    mount_names = [label for _, label in MOUNT_LABELS]
    role_controls = {}
    for role, family_key, type_key, mount_key, height_key, label, _, _ in ROLE_KEYS:
        add_text(label, bold=True, top=14)
        family_combo = add_search_combo(u"Семейство оповещателя", all_names)
        type_combo = add_combo(u"Тип")
        fill(family_combo, all_names, values.get(family_key))
        fill(type_combo, family_types.get(family_combo.SelectedItem, []), values.get(type_key))
        saved_family = values.get(family_key)
        if saved_family and saved_family not in family_types:
            missing = add_text(u"Сохранённое семейство «{}» не загружено в проект.".format(
                saved_family), gray=True)
            missing.Foreground = Brushes.IndianRed

        row = StackPanel()
        row.Orientation = Orientation.Horizontal
        row.Margin = Thickness(0, 6, 0, 0)
        add_text(u"Установка:", top=3, parent=row).Margin = Thickness(0, 3, 6, 0)
        mount_combo = ComboBox()
        mount_combo.Width = 130
        for name in mount_names:
            mount_combo.Items.Add(name)
        mount_combo.SelectedIndex = [key for key, _ in MOUNT_LABELS].index(values.get(mount_key))
        row.Children.Add(mount_combo)
        add_text(u"Высота от уровня, мм:", parent=row).Margin = Thickness(16, 3, 6, 0)
        height_box = TextBox()
        height_box.Width = 80
        height_box.Text = u"{:.0f}".format(float(values.get(height_key) or 0.0))
        row.Children.Add(height_box)
        root.Children.Add(row)

        def on_family(sender, args, type_combo=type_combo):
            fill(type_combo, family_types.get(sender.SelectedItem, []), None)

        family_combo.SelectionChanged += on_family
        role_controls[role] = (family_combo, type_combo, mount_combo, height_box)

    add_text(u"На стену — на стену помещения (ближайшую к центру помещения или клетки, "
             u"в стороне от дверей и окон), лицом в помещение. На потолок — в центр "
             u"помещения (клетки). Высота — смещение от уровня (для потолка — отметка "
             u"потолка).", gray=True, top=6)

    other_btn = Button()
    other_btn.Content = u"Помещения, параметры и отступы…"
    other_btn.Padding = Thickness(10, 4, 10, 4)
    other_btn.Margin = Thickness(0, 16, 0, 0)
    other_btn.HorizontalAlignment = HorizontalAlignment.Left
    root.Children.Add(other_btn)
    add_text(u"Имена помещений квартир, коридоров и лифтовых холлов, параметр имени "
             u"лота, шаг в МОП, отступы от углов и проёмов, параметр «Помещение».",
             gray=True, top=2)

    def on_other(sender, args):
        # Окно без Topmost — дочернее окно не застрянет позади (см. CLAUDE.md).
        SETTINGS.get_settings_interactive()

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
        for role, family_key, type_key, mount_key, height_key, label, _, _ in ROLE_KEYS:
            family_combo, type_combo, mount_combo, height_box = role_controls[role]
            update[family_key] = family_combo.SelectedItem or u""
            update[type_key] = type_combo.SelectedItem or u""
            if bool(update[family_key]) != bool(update[type_key]):
                problems.append(u"{}: выберите и семейство, и тип (или ни того, ни другого)".format(label))
            update[mount_key] = MOUNT_LABELS[max(0, mount_combo.SelectedIndex)][0]
            height = _number(height_box.Text, None)
            if height is None:
                problems.append(u"{}: высота — нужно неотрицательное число".format(label))
            else:
                update[height_key] = height
        if not problems and not configured_roles(update):
            problems.append(u"Выберите семейство и тип хотя бы для одной роли")
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
