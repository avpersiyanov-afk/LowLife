# -*- coding: utf-8 -*-
"""
Настройки кнопки «СС1-Easy» (SS1.panel/SS1Easy) + их хранение между
запусками.

Хранятся в JSON-файле %APPDATA%\\pyRevit\\LowLifeSS1Easy_settings.json —
тот же подход, что у остальных кнопок (простой файл вместо
pyrevit.script.get_config(), см. CLAUDE.md).

Имена семейств и параметров — соглашение конкретного проекта/ФОП, поэтому
умолчания у них пустые и задаются только через Shift+клик. Имена
помещений («Прихожая», «Коридор», «Вестибюль»), подпись «Ниша СС» и
высоты — общая лексика, у них разумные умолчания.

Окно Shift+клика (show_settings_window) — выбор семейства и типоразмера
кросса и кабельного подвода (два выпадающих списка «семейство → тип» по
загруженным в проект семействам) + кнопка, открывающая типовое окно
остальных полей (settings_core.TextSettings). Выбранные типоразмеры
хранятся в том же файле под ключами SYMBOL_KEYS.
"""

from lowlife import settings_core


BUTTON_NAME = u"СС1-Easy"

SETTINGS = settings_core.TextSettings(
    file_name="LowLifeSS1Easy_settings.json",
    button_name=BUTTON_NAME,
    heading=u"СС1-Easy: шахты, помещения, параметры, высоты",
    transfer_label=u"СС1-Easy",
    fields=[
        settings_core.TextField(
            "shaft_family_name",
            u"① Шахта СС",
            u"Имя семейства шахты инженерных коммуникаций (Обобщённая модель)",
            hint=u"Шахты ищутся в текущей модели среди экземпляров этого семейства.",
            default=u"", required=True,
        ),
        settings_core.TextField(
            "shaft_flag_param",
            u"",
            u"Параметр-флажок «шахта СС» (Да/Нет или текст)",
            hint=(
                u"Экземпляр или тип шахты с этим флажком считается шахтой СС. "
                u"Пусто — не проверяется."
            ),
            default=u"",
        ),
        settings_core.TextField(
            "shaft_discipline_param",
            u"",
            u"Параметр дисциплины шахты",
            hint=(
                u"Шахта считается шахтой СС, если в этом параметре (экземпляра или "
                u"типа) есть ключевое слово ниже. Пусто — не проверяется. Если пусты "
                u"оба параметра — шахтой СС считается любая шахта семейства."
            ),
            default=u"",
        ),
        settings_core.TextField(
            "shaft_discipline_keyword",
            u"",
            u"Ключевое слово дисциплины",
            default=u"СС",
        ),
        settings_core.TextField(
            "target_room_name",
            u"② Помещения (в связи АР)",
            u"Помещение квартиры, где ставится кабельный подвод",
            hint=u"Подвод ставится у двери из этого помещения в одно из соседних ниже.",
            default=u"Прихожая", required=True,
        ),
        settings_core.TextField(
            "neighbor_room_names",
            u"",
            u"Соседние помещения (через запятую)",
            default=u"Коридор, Вестибюль", required=True,
        ),
        settings_core.TextField(
            "lot_param_name",
            u"",
            u"Параметр помещения «Имя лота»",
            hint=(
                u"Значение пишется в кабельный подвод. У двухуровневой квартиры "
                u"(одинаковое имя лота на разных уровнях) подвод ставится только "
                u"в нижнюю прихожую."
            ),
            default=u"", required=True,
        ),
        settings_core.TextField(
            "room_target_param",
            u"③ Запись в оборудование",
            u"Параметр экземпляра «Помещение» у кросса и подвода",
            hint=(
                u"Кроссам пишется текст ниже, подводам — имя лота. Пусто — "
                u"ничего не пишется."
            ),
            default=u"",
        ),
        settings_core.TextField(
            "niche_text",
            u"",
            u"Текст для кроссов",
            default=u"Ниша СС",
        ),
        settings_core.NumberField(
            "cross_height_1_mm",
            u"④ Высоты, мм (от уровня)",
            u"Кросс №1",
            default=1000.0, minimum=0,
        ),
        settings_core.NumberField(
            "cross_height_2_mm",
            u"",
            u"Кросс №2",
            default=1500.0, minimum=0,
        ),
        settings_core.NumberField(
            "feed_height_mm",
            u"",
            u"Кабельный подвод (значение по умолчанию в окне запуска)",
            default=2700.0, minimum=0,
        ),
        settings_core.NumberField(
            "level_tolerance_mm",
            u"",
            u"Допуск по высоте при сопоставлении уровней",
            hint=(
                u"Уровень двери из связи АР совпадает с уровнем модели, если отметки "
                u"отличаются не больше чем на это значение. Тот же допуск — при "
                u"проверке, проходит ли шахта через уровень."
            ),
            default=100.0, minimum=0,
        ),
    ],
    width=760, height=640,
)

REQUIRED_KEYS = [
    "shaft_family_name", "target_room_name", "neighbor_room_names", "lot_param_name",
]

# Роль → (ключ семейства, ключ типоразмера, подпись)
SYMBOL_KEYS = [
    ("cross", "cross_family", "cross_type", u"Кросс"),
    ("feed", "feed_family", "feed_type", u"Кабельный подвод"),
]

load_saved_values = SETTINGS.load_saved_values
require = SETTINGS.require


def load_all():
    """Поля TextSettings + выбранные типоразмеры (семейство/тип по ролям)."""
    values = SETTINGS.load_saved_values()
    saved = SETTINGS.store.read()
    for _, family_key, type_key, _ in SYMBOL_KEYS:
        values[family_key] = saved.get(family_key) or u""
        values[type_key] = saved.get(type_key) or u""
    return values


def missing_symbols(values):
    """Подписи ролей, у которых не выбран семейство+тип."""
    return [label for _, family_key, type_key, label in SYMBOL_KEYS
            if not values.get(family_key) or not values.get(type_key)]


def require_all(values):
    """Обязательные поля + выбранные типоразмеры; иначе — сообщение и выход."""
    SETTINGS.require(values, REQUIRED_KEYS)
    missing = missing_symbols(values)
    if missing:
        settings_core._alert(
            u"Не выбраны семейство и тип:\n\n{}\n\n"
            u"Откройте настройки: Shift+клик по кнопке «{}».".format(
                u"\n".join(missing), BUTTON_NAME),
            exitscript=True
        )


# ------------------------------------------------------------
# Типоразмеры проекта
# ------------------------------------------------------------

def list_family_types(doc):
    """
    {имя семейства: [имена типоразмеров]} всех загружаемых модельных
    семейств проекта — через OfClass(Family) → GetFamilySymbolIds(), чтобы
    попали и ещё не вставленные типы (см. CLAUDE.md).
    """
    from Autodesk.Revit.DB import FilteredElementCollector, Family, CategoryType
    from lowlife.scs import safe_element_name

    result = {}
    for family in FilteredElementCollector(doc).OfClass(Family):
        try:
            category = family.FamilyCategory
            if category is not None and category.CategoryType != CategoryType.Model:
                continue
        except Exception:
            pass
        family_name = safe_element_name(family)
        if not family_name:
            continue
        names = []
        for symbol_id in family.GetFamilySymbolIds():
            symbol = doc.GetElement(symbol_id)
            type_name = safe_element_name(symbol) if symbol is not None else None
            if type_name:
                names.append(type_name)
        if names:
            result[family_name] = sorted(set(names), key=lambda n: n.lower())
    return result


# ------------------------------------------------------------
# Окно Shift+клика
# ------------------------------------------------------------

def show_settings_window(doc):
    """
    Выбор семейства+типа кросса и подвода, кнопка «Остальные настройки…».
    Сохраняет по «Сохранить»; True — сохранено, False — отмена.
    """
    import clr
    clr.AddReference('PresentationFramework')
    clr.AddReference('PresentationCore')

    from System.Windows import (
        Window, WindowStartupLocation, Thickness, FontWeights, HorizontalAlignment,
        TextWrapping, SizeToContent
    )
    from System.Windows.Controls import (
        StackPanel, TextBlock, Button, ComboBox, Orientation
    )
    from System.Windows.Media import Brushes

    from pyrevit import forms

    values = load_all()
    family_types = list_family_types(doc)
    family_names = sorted(family_types.keys(), key=lambda n: n.lower())

    win = Window()
    win.Title = u"Настройки: {}".format(BUTTON_NAME)
    win.Width = 620
    win.SizeToContent = SizeToContent.Height
    win.WindowStartupLocation = WindowStartupLocation.CenterScreen

    root = StackPanel()
    root.Margin = Thickness(16)
    win.Content = root

    title = TextBlock()
    title.Text = u"Семейства оборудования СС1"
    title.FontSize = 16
    title.FontWeight = FontWeights.Bold
    title.Margin = Thickness(0, 0, 0, 4)
    root.Children.Add(title)

    hint = TextBlock()
    hint.Text = (u"Список — загруженные в проект семейства. Перед расстановкой "
                 u"все экземпляры выбранных типоразмеров на отмеченных уровнях "
                 u"удаляются и ставятся заново.")
    hint.FontSize = 11
    hint.Foreground = Brushes.Gray
    hint.TextWrapping = TextWrapping.Wrap
    hint.Margin = Thickness(0, 0, 0, 6)
    root.Children.Add(hint)

    combos = {}

    def fill_types(type_combo, family_name, selected_type):
        type_combo.Items.Clear()
        for type_name in family_types.get(family_name, []):
            type_combo.Items.Add(type_name)
        if selected_type and selected_type in family_types.get(family_name, []):
            type_combo.SelectedItem = selected_type
        elif type_combo.Items.Count == 1:
            type_combo.SelectedIndex = 0

    for role, family_key, type_key, label in SYMBOL_KEYS:
        caption = TextBlock()
        caption.Text = label + u" *"
        caption.FontWeight = FontWeights.Bold
        caption.Margin = Thickness(0, 12, 0, 2)
        root.Children.Add(caption)

        family_label = TextBlock()
        family_label.Text = u"Семейство"
        root.Children.Add(family_label)

        family_combo = ComboBox()
        family_combo.IsEditable = True
        family_combo.IsTextSearchEnabled = True
        for name in family_names:
            family_combo.Items.Add(name)
        root.Children.Add(family_combo)

        type_label = TextBlock()
        type_label.Text = u"Тип"
        type_label.Margin = Thickness(0, 4, 0, 0)
        root.Children.Add(type_label)

        type_combo = ComboBox()
        root.Children.Add(type_combo)

        saved_family = values.get(family_key) or u""
        if saved_family in family_types:
            family_combo.SelectedItem = saved_family
            fill_types(type_combo, saved_family, values.get(type_key))
        elif saved_family:
            family_combo.Text = saved_family
            missing = TextBlock()
            missing.Text = u"Сохранённое семейство «{}» не загружено в проект.".format(saved_family)
            missing.Foreground = Brushes.IndianRed
            missing.FontSize = 11
            root.Children.Add(missing)

        def on_family_changed(sender, args, type_combo=type_combo):
            name = sender.SelectedItem
            fill_types(type_combo, name, None)

        family_combo.SelectionChanged += on_family_changed
        combos[role] = (family_combo, type_combo)

    other_btn = Button()
    other_btn.Content = u"Шахты, помещения, параметры и высоты…"
    other_btn.Padding = Thickness(10, 4, 10, 4)
    other_btn.Margin = Thickness(0, 16, 0, 0)
    other_btn.HorizontalAlignment = HorizontalAlignment.Left
    root.Children.Add(other_btn)

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
        for role, family_key, type_key, label in SYMBOL_KEYS:
            family_combo, type_combo = combos[role]
            family_name = family_combo.SelectedItem
            type_name = type_combo.SelectedItem
            if not family_name or not type_name:
                problems.append(label)
                continue
            update[family_key] = family_name
            update[type_key] = type_name
        if problems:
            forms.alert(u"Выберите семейство и тип:\n\n" + u"\n".join(problems))
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
