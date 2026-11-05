# -*- coding: utf-8 -*-
"""
Настройки кнопки «Заполнение LOI» (LOI.panel) + хранение параметров между
запусками.

Хранится в JSON-файле %APPDATA%\\pyRevit\\LowLifeLOI_settings.json — тот же
подход, что room_finder_settings.py/room_info_settings.py/scs_settings.py
(простой файл вместо pyrevit.script.get_config(), см. их докстринги про
причину).

Категория «Формы» одна и та же во всех проектах (loi_fill.FORM_CATEGORY_NAME,
не настраивается) — а вот список клонируемых параметров и то, в каких
именно моделях искать «Формы», соглашение конкретного проекта, поэтому
задаётся в настройках (Shift+клик). Настройки:
  - param_names_text — параметры, которые клонируются из «Формы» в
    содержащиеся в ней элементы (по имени, см. get_param_names);
  - search_locations/search_locations_configured — в каких моделях искать
    «Формы»: текущий файл-хост и/или конкретные загруженные связи по имени
    (см. loi_fill.list_search_locations/find_forms). Формы физически часто
    лежат в отдельной связанной архитектурной модели, а не в текущем файле —
    пока эта настройка не тронута (search_locations_configured=False),
    ищем везде (хост + все связи), как было раньше;
  - split_multi_form_boundary — пробовать ли физически разрезать прямой
    линейный элемент (лоток и т.п.), попавший сразу в несколько форм, по их
    границе, прежде чем показывать его в диалоге конфликтов (см. loi_split.py).
"""

try:
    unicode  # noqa: F821 — IronPython/Python 2
except NameError:  # Python 3
    unicode = str


import clr
from lowlife.i18n import N_, tr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')

from pyrevit import forms
from lowlife import select_list

from lowlife import param_autocomplete, settings_core, settings_transfer

from System.Windows import (
    Window, WindowStartupLocation, Thickness,
    FontWeights, HorizontalAlignment, VerticalAlignment, TextWrapping,
    SizeToContent, ResizeMode
)
from System.Windows.Controls import (
    StackPanel, TextBlock, TextBox, Button, CheckBox, RadioButton,
    Orientation, DockPanel, Dock, ScrollViewer, ScrollBarVisibility, ComboBox
)
from System.Windows.Media import Brushes

SETTINGS_FILE_NAME = "LowLifeLOI_settings.json"

# (ключ, заголовок раздела, подпись поля, пояснение под полем,
#  значение по умолчанию, многострочное поле, обязательное поле)
TEXT_FIELDS = [
    (
        "param_names_text",
        N_(u"② Параметры для клонирования из «Форм»"),
        N_(u"Имена параметров (по одному на строке)"),
        N_(u"Значения этих параметров переносятся из «Формы» в содержащиеся в "
        u"ней элементы — по имени параметра, оно должно совпадать у «Формы» "
        u"и у целевого элемента. Один параметр — одна строка."),
        u"", True, True
    ),
]

PLAIN_LABELS = {key: label for key, _section, label, _hint, _default, _multiline, _required in TEXT_FIELDS}

SEARCH_LOCATIONS_KEY = "search_locations"
SEARCH_LOCATIONS_CONFIGURED_KEY = "search_locations_configured"

SPLIT_KEY = "split_multi_form_boundary"
SPLIT_DEFAULT = True


_STORE = settings_core.JsonStore(SETTINGS_FILE_NAME)
_settings_file_path = _STORE.path
_read_all = _STORE.read
_write_all = _STORE.write


def load_saved_values():
    """Значения настроек: из JSON-файла, иначе — значения по умолчанию.
    Область заполнения выбирается при запуске и не сохраняется."""
    saved = _read_all()
    values = {key: saved.get(key, default)
              for key, _section, _label, _hint, default, _multiline, _required in TEXT_FIELDS}

    raw_locations = saved.get(SEARCH_LOCATIONS_KEY, [])
    values[SEARCH_LOCATIONS_KEY] = (
        [unicode(x) for x in raw_locations] if isinstance(raw_locations, list) else []
    )
    values[SEARCH_LOCATIONS_CONFIGURED_KEY] = bool(saved.get(SEARCH_LOCATIONS_CONFIGURED_KEY, False))

    values[SPLIT_KEY] = bool(saved.get(SPLIT_KEY, SPLIT_DEFAULT))

    return values


def save_values(values):
    data = _read_all()
    for key in ("selection_mode", "selected_type_ids"):
        data.pop(key, None)
    data.update({key: value for key, value in values.items() if not key.startswith("_")})
    _write_all(data)


def get_param_names(settings):
    """Список имён параметров из param_names_text — по одному на строке, без пустых/дублей."""
    text = settings.get("param_names_text", u"") or u""
    names = []
    seen = set()
    for line in text.splitlines():
        name = line.strip()
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names


def get_search_locations(settings):
    """
    Список моделей для поиска «Форм» (см. loi_fill.find_forms/HOST_LOCATION_KEY),
    либо None, если настройка ещё не тронута — вызывающий код должен
    трактовать None как «искать везде» (хост + все загруженные связи, как
    было до появления этой настройки).
    """
    if not bool(settings.get(SEARCH_LOCATIONS_CONFIGURED_KEY, False)):
        return None
    return list(settings.get(SEARCH_LOCATIONS_KEY) or [])


def get_split_enabled(settings):
    return bool(settings.get(SPLIT_KEY, SPLIT_DEFAULT))


def require(settings, keys):
    """
    Проверяет, что перечисленные ключи заполнены. Останавливает скрипт
    через forms.alert(exitscript=True), если чего-то не хватает.
    """
    missing = []

    for key in keys:
        if key == "param_names_text":
            if not get_param_names(settings):
                missing.append(tr(PLAIN_LABELS.get(key, key)))
            continue
        value = settings.get(key)
        if not (value and unicode(value).strip()):
            missing.append(tr(PLAIN_LABELS.get(key, key)))

    if missing:
        forms.alert(
            tr(u"Не заполнены обязательные настройки:\n\n{}\n\n"
            u"Откройте настройки: Shift+клик по кнопке «Заполнение LOI».").format(
                u"\n".join(missing)
            ),
            exitscript=True
        )


def _locations_label_text(configured, keys, options):
    if not configured:
        return tr(u"Не настроено — ищутся все: текущий файл и все загруженные связи.")
    if not keys:
        return tr(u"Не выбрано ни одной модели — формы не будут найдены.")
    by_key = {o.key: o.name for o in options} if options else {}
    names = [by_key.get(k, k) for k in keys]
    preview = u"; ".join(names[:5])
    if len(names) > 5:
        preview += u"; …"
    return tr(u"Выбрано: {}. {}").format(len(keys), preview)


def show_settings_form(doc, values):
    """Модальное окно редактирования настроек. Возвращает словарь значений
    или None, если пользователь отменил."""
    from lowlife import loi_fill

    result = {"values": None}
    state = {
        "locations": list(values.get(SEARCH_LOCATIONS_KEY) or []),
        "locations_configured": bool(values.get(SEARCH_LOCATIONS_CONFIGURED_KEY, False)),
    }

    win = Window()
    win.Title = tr(u"Настройки: Заполнение LOI")
    win.Width = 760
    win.Height = 760
    win.WindowStartupLocation = WindowStartupLocation.CenterScreen

    outer = DockPanel()
    outer.LastChildFill = True

    root = StackPanel()
    root.Margin = Thickness(16)

    title = TextBlock()
    title.Text = tr(u"В каких моделях искать «Формы» и что из них клонировать")
    title.FontSize = 16
    title.FontWeight = FontWeights.Bold
    title.Margin = Thickness(0, 0, 0, 4)
    root.Children.Add(title)

    hint = TextBlock()
    hint.Text = tr(u"Значения сохраняются и подставляются при следующих запусках.")
    hint.FontSize = 11
    hint.Foreground = Brushes.Gray
    hint.Margin = Thickness(0, 0, 0, 10)
    root.Children.Add(hint)

    # --- ① в каких моделях искать формы ---------------------------------

    locations_section = TextBlock()
    locations_section.Text = tr(u"① В каких моделях искать элементы «Форма»")
    locations_section.FontWeight = FontWeights.Bold
    locations_section.Margin = Thickness(0, 2, 0, 2)
    root.Children.Add(locations_section)

    locations_row = StackPanel()
    locations_row.Orientation = Orientation.Horizontal
    locations_row.Margin = Thickness(0, 4, 0, 0)

    locations_pick_btn = Button()
    locations_pick_btn.Content = tr(u"Выбрать модели…")
    locations_pick_btn.Padding = Thickness(8, 2, 8, 2)
    locations_row.Children.Add(locations_pick_btn)

    locations_label = TextBlock()
    locations_label.Text = _locations_label_text(
        state["locations_configured"], state["locations"], None
    )
    locations_label.VerticalAlignment = VerticalAlignment.Center
    locations_label.Margin = Thickness(8, 0, 0, 0)
    locations_label.TextWrapping = TextWrapping.Wrap
    locations_row.Children.Add(locations_label)

    root.Children.Add(locations_row)

    def on_pick_locations(sender, args):
        options = loi_fill.list_search_locations(doc)
        checked_keys = (
            set(state["locations"]) if state["locations_configured"]
            else set(o.key for o in options)
        )
        items = [forms.TemplateListItem(o, checked=(o.key in checked_keys)) for o in options]

        chosen = select_list.SelectFromList.show(
            items,
            title=tr(u"Модели, в которых искать элементы «Форма»"),
            button_name=tr(u"Сохранить"),
            multiselect=True
        )
        if chosen is None:
            return

        state["locations"] = [o.key for o in chosen]
        state["locations_configured"] = True
        locations_label.Text = _locations_label_text(True, state["locations"], options)

    locations_pick_btn.Click += on_pick_locations

    locations_hint = TextBlock()
    locations_hint.Text = (
        tr(u"«Формы» обычно лежат в отдельной связанной архитектурной модели — "
        u"отметьте текущий файл и/или конкретные загруженные связи. Пока не "
        u"настроено — «Формы» ищутся везде: в текущем файле и во всех связях.")
    )
    locations_hint.FontSize = 11
    locations_hint.Foreground = Brushes.Gray
    locations_hint.TextWrapping = TextWrapping.Wrap
    locations_hint.Margin = Thickness(0, 4, 0, 0)
    root.Children.Add(locations_hint)

    boxes = {}

    for key, section_title, label_text, hint_text, _, multiline, required in TEXT_FIELDS:
        section = TextBlock()
        section.Text = tr(section_title)
        section.FontWeight = FontWeights.Bold
        section.Margin = Thickness(0, 16, 0, 2)
        root.Children.Add(section)

        label = TextBlock()
        label.Text = tr(label_text) + (u" *" if required else u"")
        label.Margin = Thickness(0, 2, 0, 2)
        label.TextWrapping = TextWrapping.Wrap
        root.Children.Add(label)

        box = TextBox()
        box.Text = values.get(key, "")
        box.Padding = Thickness(4)

        if multiline:
            box.AcceptsReturn = True
            box.TextWrapping = TextWrapping.Wrap
            box.Height = 100
            box.VerticalScrollBarVisibility = ScrollBarVisibility.Auto

        root.Children.Add(box)
        boxes[key] = box

        field_hint = TextBlock()
        field_hint.Text = tr(hint_text)
        field_hint.FontSize = 11
        field_hint.Foreground = Brushes.Gray
        field_hint.TextWrapping = TextWrapping.Wrap
        field_hint.Margin = Thickness(0, 2, 0, 0)
        root.Children.Add(field_hint)

    # --- ④ разбиение элементов на границе форм --------------------------

    split_section = TextBlock()
    split_section.Text = tr(u"Элемент сразу в нескольких формах")
    split_section.FontWeight = FontWeights.Bold
    split_section.Margin = Thickness(0, 16, 0, 2)
    root.Children.Add(split_section)

    split_cb = CheckBox()
    split_cb.Content = (
        tr(u"Разрезать прямой линейный элемент (лоток, короб, труба…) по "
        u"границе форм и записать каждому куску значения его формы")
    )
    split_cb.Margin = Thickness(0, 4, 0, 2)
    split_cb.IsChecked = bool(values.get(SPLIT_KEY, SPLIT_DEFAULT))
    root.Children.Add(split_cb)

    split_hint = TextBlock()
    split_hint.Text = (
        tr(u"Применяется только к прямым линейным элементам, физически "
        u"проходящим через границу нескольких форм. То, что разрезать не "
        u"удалось (кривые участки, точечные элементы, наложенные формы), "
        u"по-прежнему показывается в окне разрешения конфликтов, где форму-"
        u"источник для всего элемента выбирает пользователь.")
    )
    split_hint.FontSize = 11
    split_hint.Foreground = Brushes.Gray
    split_hint.TextWrapping = TextWrapping.Wrap
    split_hint.Margin = Thickness(0, 2, 0, 0)
    root.Children.Add(split_hint)

    # --- нижний ряд кнопок -----------------------------------------------

    buttons = StackPanel()
    buttons.Orientation = Orientation.Horizontal
    buttons.HorizontalAlignment = HorizontalAlignment.Right
    buttons.Margin = Thickness(16, 8, 16, 12)
    DockPanel.SetDock(buttons, Dock.Bottom)

    cancel_btn = Button()
    cancel_btn.Content = tr(u"Отмена")
    cancel_btn.Padding = Thickness(10, 4, 10, 4)
    cancel_btn.Margin = Thickness(0, 0, 8, 0)

    ok_btn = Button()
    ok_btn.Content = tr(u"Сохранить")
    ok_btn.Padding = Thickness(10, 4, 10, 4)
    ok_btn.FontWeight = FontWeights.Bold

    def on_ok(sender, args):
        combined = {key: box.Text for key, box in boxes.items()}
        if not get_param_names(combined):
            forms.alert(tr(u"Укажите хотя бы один параметр для заполнения LOI."))
            return
        combined[SPLIT_KEY] = bool(split_cb.IsChecked)
        combined[SEARCH_LOCATIONS_KEY] = list(state["locations"])
        combined[SEARCH_LOCATIONS_CONFIGURED_KEY] = bool(state["locations_configured"])
        result["values"] = combined
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
        buttons, _read_all, _write_all, u"заполнения LOI", _on_settings_imported
    )

    scroll = ScrollViewer()
    scroll.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
    scroll.Content = root

    outer.Children.Add(buttons)
    outer.Children.Add(scroll)

    win.Content = outer
    # подсказка имён параметров модели в полях имён параметров
    # (список «Параметры для заполнения» — по одному на строке)
    param_autocomplete.attach_by_keys(
        boxes, param_autocomplete.NameSource(doc),
        overrides={"param_names_text": (u"\n", None)}
    )

    win.ShowDialog()

    return result["values"]


def get_settings_interactive(doc):
    """
    Показывает окно настроек, сохраняет введённые значения и возвращает
    их. Возвращает None, если пользователь нажал «Отмена». Открывается
    по Shift+клику на кнопке «Заполнение LOI».
    """
    while True:
        saved = load_saved_values()
        edited = show_settings_form(doc, saved)

        if edited == settings_transfer.RELOAD:
            continue

        if edited is None:
            return None

        save_values(edited)
        return edited


def get_settings_silent():
    """Настройки без показа окна — уже сохранённые значения (или значения
    по умолчанию, если ещё не настроено). Используется «СС1-8Mile»."""
    return load_saved_values()


def show_scope_dialog(doc, selected_ids):
    """Choose selected objects or a 3D view for this run. Cancel returns None."""
    result = {"scope": None}
    win = Window()
    win.Title = tr(u"Заполнение LOI")
    win.Width = 520
    win.SizeToContent = SizeToContent.Height
    win.ResizeMode = ResizeMode.NoResize
    win.WindowStartupLocation = WindowStartupLocation.CenterScreen
    root = StackPanel()
    root.Margin = Thickness(16)

    # Runtime scope is chosen on every launch; document IDs are never saved.
    from Autodesk.Revit.DB import FilteredElementCollector, View3D

    selected_ids = list(selected_ids or [])
    views = sorted(
        [v for v in FilteredElementCollector(doc).OfClass(View3D) if not v.IsTemplate],
        key=lambda v: unicode(v.Name).lower()
    )
    scope_title = TextBlock()
    scope_title.Text = tr(u"Где заполнять LOI")
    scope_title.FontWeight = FontWeights.Bold
    root.Children.Add(scope_title)

    rb_selected = RadioButton()
    rb_selected.Content = tr(u"Выбранные объекты ({})").format(len(selected_ids))
    rb_selected.GroupName = "loi_scope"
    rb_selected.Margin = Thickness(0, 6, 0, 4)
    rb_selected.IsEnabled = bool(selected_ids)
    rb_selected.IsChecked = bool(selected_ids)
    root.Children.Add(rb_selected)

    rb_view = RadioButton()
    rb_view.Content = tr(u"Объекты на выбранном 3D-виде")
    rb_view.GroupName = "loi_scope"
    rb_view.Margin = Thickness(0, 2, 0, 4)
    rb_view.IsChecked = not bool(selected_ids)
    root.Children.Add(rb_view)

    view_combo = ComboBox()
    view_combo.Margin = Thickness(20, 0, 0, 12)
    for view in views:
        view_combo.Items.Add(unicode(view.Name))
    view_combo.SelectedIndex = 0 if views else -1
    active = doc.ActiveView
    for index, view in enumerate(views):
        if active is not None and view.Id == active.Id:
            view_combo.SelectedIndex = index
            break
    view_combo.IsEnabled = bool(rb_view.IsChecked)

    def on_scope_changed(sender, args):
        view_combo.IsEnabled = bool(rb_view.IsChecked)

    rb_view.Checked += on_scope_changed
    rb_selected.Checked += on_scope_changed
    root.Children.Add(view_combo)

    buttons = StackPanel()
    buttons.Orientation = Orientation.Horizontal
    buttons.HorizontalAlignment = HorizontalAlignment.Right
    cancel_btn = Button()
    cancel_btn.Content = tr(u"Отмена")
    cancel_btn.Padding = Thickness(10, 4, 10, 4)
    cancel_btn.Margin = Thickness(0, 0, 8, 0)
    cancel_btn.IsCancel = True
    ok_btn = Button()
    ok_btn.Content = tr(u"Заполнить LOI")
    ok_btn.Padding = Thickness(10, 4, 10, 4)
    ok_btn.IsDefault = True

    def on_ok(sender, args):
        combined = {}
        if rb_selected.IsChecked:
            if not selected_ids:
                forms.alert(tr(u"Сначала выделите объекты в Revit."))
                return
            combined["_selected_ids"] = selected_ids
            combined["_view"] = None
        else:
            index = view_combo.SelectedIndex
            if index < 0:
                forms.alert(tr(u"Выберите 3D-вид для заполнения LOI."))
                return
            combined["_selected_ids"] = None
            combined["_view"] = views[index]
        result["scope"] = combined
        win.Close()

    def on_cancel(sender, args):
        win.Close()

    ok_btn.Click += on_ok
    cancel_btn.Click += on_cancel
    buttons.Children.Add(cancel_btn)
    buttons.Children.Add(ok_btn)
    root.Children.Add(buttons)
    win.Content = root
    win.ShowDialog()
    return result["scope"]
