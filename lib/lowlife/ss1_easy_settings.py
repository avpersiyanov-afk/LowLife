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

Окно Shift+клика (show_settings_window) — выпадающие списки по
загруженным в проект семействам:
  - шахта СС: семейство «Обобщённой модели» → параметр (типа или
    экземпляра) → значение («СС»; у других шахт там «СБ», «СПЗ»…);
  - кросс и кабельный подвод: семейство → тип;
и кнопка, открывающая типовое окно остальных полей
(settings_core.TextSettings: помещения, параметры, высоты). Шахта и
типоразмеры хранятся в том же файле под ключами SHAFT_KEYS/SYMBOL_KEYS.
"""

from lowlife import settings_core


BUTTON_NAME = u"СС1-Easy"

SETTINGS = settings_core.TextSettings(
    file_name="LowLifeSS1Easy_settings.json",
    button_name=BUTTON_NAME,
    heading=u"СС1-Easy: помещения, параметры, высоты",
    transfer_label=u"СС1-Easy",
    fields=[
        settings_core.TextField(
            "target_room_name",
            u"① Помещения (в связи АР)",
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
            u"② Запись в оборудование",
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
            u"③ Высоты, мм (от уровня)",
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

REQUIRED_KEYS = ["target_room_name", "neighbor_room_names", "lot_param_name"]

# Шахта СС: семейство + параметр (типа или экземпляра) + значение — в окне
# Shift+клика, хранятся в том же файле.
SHAFT_KEYS = [
    ("shaft_family_name", u"Шахта СС — семейство"),
    ("shaft_param", u"Шахта СС — параметр"),
    ("shaft_value", u"Шахта СС — значение"),
]

# Роль → (ключ семейства, ключ типоразмера, подпись)
SYMBOL_KEYS = [
    ("cross", "cross_family", "cross_type", u"Кросс"),
    ("feed", "feed_family", "feed_type", u"Кабельный подвод"),
]

load_saved_values = SETTINGS.load_saved_values
require = SETTINGS.require

# Сколько экземпляров семейства шахты просматривать, собирая параметры и
# их значения для выпадающих списков (параметры типа берутся у всех типов).
_MAX_SAMPLE_INSTANCES = 300


def load_all():
    """Поля TextSettings + шахта СС + выбранные типоразмеры."""
    values = SETTINGS.load_saved_values()
    saved = SETTINGS.store.read()
    for key, _ in SHAFT_KEYS:
        values[key] = saved.get(key) or u""
    for _, family_key, type_key, _ in SYMBOL_KEYS:
        values[family_key] = saved.get(family_key) or u""
        values[type_key] = saved.get(type_key) or u""
    return values


def missing_main(values):
    """Подписи незаполненных пунктов главного окна (шахта, кросс, подвод)."""
    missing = [label for key, label in SHAFT_KEYS if not (values.get(key) or u"").strip()]
    missing += [label + u" — семейство и тип" for _, family_key, type_key, label in SYMBOL_KEYS
                if not values.get(family_key) or not values.get(type_key)]
    return missing


def require_all(values):
    """Всё обязательное заполнено; иначе — сообщение и выход."""
    missing = missing_main(values)
    if missing:
        settings_core._alert(
            u"Не заполнены настройки:\n\n{}\n\n"
            u"Откройте настройки: Shift+клик по кнопке «{}».".format(
                u"\n".join(missing), BUTTON_NAME),
            exitscript=True
        )
    SETTINGS.require(values, REQUIRED_KEYS)


# ------------------------------------------------------------
# Семейства, типы, параметры проекта
# ------------------------------------------------------------

def _is_generic_model(family):
    from Autodesk.Revit.DB import BuiltInCategory
    try:
        category = family.FamilyCategory
        return category is not None and category.Id.IntegerValue == int(BuiltInCategory.OST_GenericModel)
    except Exception:
        return False


def list_families(doc):
    """
    [(имя семейства, обобщённая модель?, [имена типов])] всех загружаемых
    модельных семейств — через OfClass(Family) → GetFamilySymbolIds(), чтобы
    попали и ещё не вставленные типы (см. CLAUDE.md).
    """
    from Autodesk.Revit.DB import FilteredElementCollector, Family, CategoryType
    from lowlife.scs import safe_element_name

    result = []
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
            result.append((family_name, _is_generic_model(family),
                           sorted(set(names), key=lambda n: n.lower())))
    return sorted(result, key=lambda item: item[0].lower())


def _param_text(param):
    """Значение параметра текстом: строка как есть, остальное — как в Revit."""
    from Autodesk.Revit.DB import StorageType
    value = None
    try:
        if param.StorageType == StorageType.String:
            value = param.AsString()
        else:
            value = param.AsValueString()
    except Exception:
        pass
    return (value or u"").strip()


def list_family_params(doc, family_name):
    """
    {имя параметра: [значения]} параметров типов семейства family_name и
    его экземпляров (первые _MAX_SAMPLE_INSTANCES). Значения — непустые,
    встретившиеся у типов/экземпляров (для списка «Значение»).
    """
    from Autodesk.Revit.DB import FilteredElementCollector, Family, FamilyInstance
    from lowlife.scs import safe_element_name

    params = {}

    def collect(element):
        for param in element.Parameters:
            try:
                name = param.Definition.Name
            except Exception:
                continue
            if not name:
                continue
            values = params.setdefault(name, set())
            text = _param_text(param)
            if text:
                values.add(text)

    family = None
    for candidate in FilteredElementCollector(doc).OfClass(Family):
        if safe_element_name(candidate) == family_name:
            family = candidate
            break
    if family is None:
        return {}

    for symbol_id in family.GetFamilySymbolIds():
        symbol = doc.GetElement(symbol_id)
        if symbol is not None:
            collect(symbol)

    symbol_ids = set(i.IntegerValue for i in family.GetFamilySymbolIds())
    seen = 0
    for instance in FilteredElementCollector(doc).OfClass(FamilyInstance):
        try:
            if instance.GetTypeId().IntegerValue not in symbol_ids:
                continue
        except Exception:
            continue
        collect(instance)
        seen += 1
        if seen >= _MAX_SAMPLE_INSTANCES:
            break

    return dict((name, sorted(values, key=lambda v: v.lower())) for name, values in params.items())


# ------------------------------------------------------------
# Окно Shift+клика
# ------------------------------------------------------------

def show_settings_window(doc):
    """
    Шахта СС (семейство → параметр → значение), кросс и подвод (семейство →
    тип), кнопка «Помещения, параметры и высоты…». Сохраняет по
    «Сохранить»; True — сохранено, False — отмена.
    """
    import clr
    clr.AddReference('PresentationFramework')
    clr.AddReference('PresentationCore')

    from System.Windows import (
        Window, WindowStartupLocation, Thickness, FontWeights, HorizontalAlignment,
        TextWrapping, SizeToContent
    )
    from System.Windows.Controls import (
        StackPanel, TextBlock, Button, ComboBox, Orientation, ScrollViewer, ScrollBarVisibility
    )
    from System.Windows.Media import Brushes

    from pyrevit import forms

    values = load_all()
    families = list_families(doc)
    family_types = dict((name, types) for name, _, types in families)
    all_names = [name for name, _, _ in families]
    generic_names = [name for name, is_generic, _ in families if is_generic]
    param_cache = {}

    def family_params(name):
        if name not in param_cache:
            param_cache[name] = list_family_params(doc, name) if name else {}
        return param_cache[name]

    win = Window()
    win.Title = u"Настройки: {}".format(BUTTON_NAME)
    win.Width = 620
    win.SizeToContent = SizeToContent.Height
    win.MaxHeight = 860
    win.WindowStartupLocation = WindowStartupLocation.CenterScreen

    root = StackPanel()
    root.Margin = Thickness(16)
    scroll = ScrollViewer()
    scroll.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
    scroll.Content = root
    win.Content = scroll

    def add_text(text, bold=False, size=None, gray=False, top=0, bottom=0):
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
        root.Children.Add(block)
        return block

    def add_combo(label, editable=False):
        add_text(label, top=4)
        combo = ComboBox()
        combo.IsEditable = editable
        combo.IsTextSearchEnabled = True
        root.Children.Add(combo)
        return combo

    def fill(combo, items, selected):
        combo.Items.Clear()
        for item in items:
            combo.Items.Add(item)
        if selected and selected in items:
            combo.SelectedItem = selected
        elif selected and combo.IsEditable:
            combo.Text = selected
        elif len(items) == 1:
            combo.SelectedIndex = 0

    add_text(u"СС1-Easy: что и куда ставить", bold=True, size=16, bottom=4)
    add_text(u"Списки — семейства, загруженные в проект. При запуске все экземпляры "
             u"выбранных типов кросса и подвода на отмеченных уровнях удаляются и "
             u"ставятся заново.", gray=True, bottom=4)

    # --- шахта СС ---------------------------------------------------------
    add_text(u"Шахта СС *", bold=True, top=12)
    add_text(u"Шахта — экземпляр этого семейства (Обобщённая модель), у которого "
             u"параметр (типа или экземпляра) равен значению. Например, параметр со "
             u"значениями СС / СБ / СПЗ и значение «СС».", gray=True)
    shaft_family = add_combo(u"Семейство")
    shaft_param = add_combo(u"Параметр, по которому отличаются шахты")
    shaft_value = add_combo(u"Значение для шахты СС", editable=True)

    def fill_shaft_params(family_name, selected_param, selected_value):
        params = family_params(family_name)
        fill(shaft_param, sorted(params.keys(), key=lambda n: n.lower()), selected_param)
        fill_shaft_values(family_name, shaft_param.SelectedItem, selected_value)

    def fill_shaft_values(family_name, param_name, selected_value):
        values_list = family_params(family_name).get(param_name, []) if param_name else []
        fill(shaft_value, values_list, selected_value)

    fill(shaft_family, generic_names, values.get("shaft_family_name"))
    fill_shaft_params(shaft_family.SelectedItem, values.get("shaft_param"),
                      values.get("shaft_value") or u"СС")

    def on_shaft_family(sender, args):
        fill_shaft_params(shaft_family.SelectedItem, None, u"СС")

    def on_shaft_param(sender, args):
        fill_shaft_values(shaft_family.SelectedItem, shaft_param.SelectedItem, u"СС")

    shaft_family.SelectionChanged += on_shaft_family
    shaft_param.SelectionChanged += on_shaft_param

    # --- кросс, подвод ------------------------------------------------------
    symbol_combos = {}
    for role, family_key, type_key, label in SYMBOL_KEYS:
        add_text(label + u" *", bold=True, top=12)
        family_combo = add_combo(u"Семейство")
        type_combo = add_combo(u"Тип")
        fill(family_combo, all_names, values.get(family_key))
        fill(type_combo, family_types.get(family_combo.SelectedItem, []), values.get(type_key))
        saved_family = values.get(family_key)
        if saved_family and saved_family not in family_types:
            missing = add_text(u"Сохранённое семейство «{}» не загружено в проект.".format(
                saved_family), gray=True)
            missing.Foreground = Brushes.IndianRed

        def on_family(sender, args, type_combo=type_combo):
            fill(type_combo, family_types.get(sender.SelectedItem, []), None)

        family_combo.SelectionChanged += on_family
        symbol_combos[role] = (family_combo, type_combo)

    # --- остальное ----------------------------------------------------------
    other_btn = Button()
    other_btn.Content = u"Помещения, параметры и высоты…"
    other_btn.Padding = Thickness(10, 4, 10, 4)
    other_btn.Margin = Thickness(0, 16, 0, 0)
    other_btn.HorizontalAlignment = HorizontalAlignment.Left
    root.Children.Add(other_btn)
    add_text(u"Имена прихожей и соседних помещений, параметр имени лота, параметр "
             u"«Помещение» оборудования, высоты кроссов и подвода.", gray=True, top=2)

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
        update = {
            "shaft_family_name": shaft_family.SelectedItem or u"",
            "shaft_param": shaft_param.SelectedItem or u"",
            "shaft_value": (shaft_value.Text or u"").strip(),
        }
        for role, family_key, type_key, label in SYMBOL_KEYS:
            family_combo, type_combo = symbol_combos[role]
            update[family_key] = family_combo.SelectedItem or u""
            update[type_key] = type_combo.SelectedItem or u""
        problems = missing_main(update)
        if problems:
            forms.alert(u"Заполните:\n\n" + u"\n".join(problems))
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
