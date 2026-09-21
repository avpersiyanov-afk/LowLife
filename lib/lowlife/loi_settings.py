# -*- coding: utf-8 -*-
"""
Окно настроек для кнопки «Заполнение LOI» (LOI.panel) + их хранение между
запусками.

Хранится в JSON-файле %APPDATA%\\pyRevit\\LowLifeLOI_settings.json — тот же
подход, что room_finder_settings.py/room_info_settings.py/scs_settings.py
(простой файл вместо pyrevit.script.get_config(), см. их докстринги про
причину).

Имя категории «Формы» и список клонируемых параметров — соглашение
конкретного проекта/ФОП, поэтому не зашиты константами в коде, только через
это окно (Shift+клик по кнопке). Туда же вынесены:
  - selection_mode/selected_type_ids — какие элементы вообще проверяются на
    попадание в форму (см. loi_fill.SELECTION_MODE_*): весь документ, только
    активный вид (по умолчанию, как было раньше) или только отмеченные типы
    семейств;
  - split_multi_form_boundary — пробовать ли физически разрезать прямой
    линейный элемент (лоток и т.п.), попавший сразу в несколько форм, по их
    границе, прежде чем показывать его в диалоге конфликтов (см. loi_split.py).
"""

import os
import io
import json

import clr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')

from pyrevit import forms

from lowlife import settings_transfer

from System.Windows import (
    Window, WindowStartupLocation, Thickness,
    FontWeights, HorizontalAlignment, VerticalAlignment, TextWrapping
)
from System.Windows.Controls import (
    StackPanel, TextBlock, TextBox, Button, CheckBox, RadioButton,
    Orientation, DockPanel, Dock, ScrollViewer, ScrollBarVisibility
)
from System.Windows.Media import Brushes

SETTINGS_FILE_NAME = "LowLifeLOI_settings.json"

# (ключ, заголовок раздела, подпись поля, пояснение под полем,
#  значение по умолчанию, многострочное поле, обязательное поле)
TEXT_FIELDS = [
    (
        "form_category_name",
        u"① Категория элементов «Форма»",
        u"Имя категории семейства",
        u"Категория, к которой должны принадлежать элементы «Форма» — их "
        u"параметры клонируются в элементы, физически находящиеся внутри их "
        u"солида. Обычно это отдельная категория семейства, заведённая под "
        u"эту задачу.",
        u"Форма", False, True
    ),
    (
        "param_names_text",
        u"② Параметры для клонирования",
        u"Имена параметров (по одному на строке)",
        u"Значения этих параметров переносятся из «Формы» в содержащиеся в "
        u"ней элементы — по имени параметра, оно должно совпадать у «Формы» "
        u"и у целевого элемента. Один параметр — одна строка.",
        u"", True, True
    ),
]

PLAIN_LABELS = {key: label for key, _section, label, _hint, _default, _multiline, _required in TEXT_FIELDS}

MODE_KEY = "selection_mode"
MODE_VIEW = "view"     # lowlife.loi_fill.SELECTION_MODE_VIEW
MODE_ALL = "all"        # lowlife.loi_fill.SELECTION_MODE_ALL
MODE_TYPES = "types"    # lowlife.loi_fill.SELECTION_MODE_TYPES
MODE_DEFAULT = MODE_VIEW

TYPE_IDS_KEY = "selected_type_ids"

SPLIT_KEY = "split_multi_form_boundary"
SPLIT_DEFAULT = True


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
        forms.alert(
            u"Не удалось сохранить настройки в файл:\n{}".format(path)
        )


def load_saved_values():
    """Значения настроек: из JSON-файла, иначе — значения по умолчанию.
    Текстовые поля — строки, selected_type_ids — список int, остальное —
    как есть (mode-строка/bool)."""
    saved = _read_all()
    values = {key: saved.get(key, default)
              for key, _section, _label, _hint, default, _multiline, _required in TEXT_FIELDS}

    values[MODE_KEY] = saved.get(MODE_KEY, MODE_DEFAULT)

    raw_ids = saved.get(TYPE_IDS_KEY, [])
    if isinstance(raw_ids, list):
        parsed_ids = []
        for x in raw_ids:
            try:
                parsed_ids.append(int(x))
            except:
                pass
        values[TYPE_IDS_KEY] = parsed_ids
    else:
        values[TYPE_IDS_KEY] = []

    values[SPLIT_KEY] = bool(saved.get(SPLIT_KEY, SPLIT_DEFAULT))

    return values


def save_values(values):
    data = _read_all()
    data.update(values)
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


def get_selection_mode(settings):
    """SELECTION_MODE_* (см. loi_fill) из настроек, с запасным значением MODE_DEFAULT."""
    mode = settings.get(MODE_KEY, MODE_DEFAULT)
    return mode if mode in (MODE_VIEW, MODE_ALL, MODE_TYPES) else MODE_DEFAULT


def get_selected_type_ids(settings):
    """Список int ElementId.IntegerValue отмеченных типов семейств (может быть пустым)."""
    ids = settings.get(TYPE_IDS_KEY) or []
    return [int(x) for x in ids]


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
                missing.append(PLAIN_LABELS.get(key, key))
            continue
        value = settings.get(key)
        if not (value and unicode(value).strip()):
            missing.append(PLAIN_LABELS.get(key, key))

    if missing:
        forms.alert(
            u"Не заполнены обязательные настройки:\n\n{}\n\n"
            u"Откройте настройки: Shift+клик по кнопке «Заполнение LOI».".format(
                u"\n".join(missing)
            ),
            exitscript=True
        )


def require_selection_mode(settings):
    """
    Отдельная проверка для режима «Только выбранные типы семейств»: если он
    включён, но ни один тип не отмечен — останавливает скрипт с понятным
    сообщением (в отличие от require() выше, эта настройка необязательна
    для остальных режимов, поэтому проверяется отдельно, после чтения mode).
    """
    if get_selection_mode(settings) == MODE_TYPES and not get_selected_type_ids(settings):
        forms.alert(
            u"В настройках выбран режим «Только выбранные типы семейств», "
            u"но ни один тип не отмечен.\n\n"
            u"Откройте настройки (Shift+клик по кнопке «Заполнение LOI») и "
            u"нажмите «Выбрать типы…», либо переключитесь на другой режим "
            u"отбора элементов.",
            exitscript=True
        )


def _types_label_text(ids, options):
    if not ids:
        return u"Типы не выбраны."
    by_id = {o.type_id.IntegerValue: o.name for o in options} if options else {}
    names = [by_id.get(i, u"?(ID {})".format(i)) for i in ids]
    preview = u"; ".join(names[:5])
    if len(names) > 5:
        preview += u"; …"
    return u"Выбрано типов: {}. {}".format(len(ids), preview)


def show_settings_form(doc, values):
    """Модальное окно редактирования настроек. Возвращает словарь
    значений (строки TEXT_FIELDS + MODE_KEY/TYPE_IDS_KEY/SPLIT_KEY) или
    None, если пользователь отменил."""
    from lowlife import loi_fill

    result = {"values": None}
    state = {"type_ids": list(values.get(TYPE_IDS_KEY) or [])}

    win = Window()
    win.Title = u"Настройки: Заполнение LOI"
    win.Width = 760
    win.Height = 700
    win.WindowStartupLocation = WindowStartupLocation.CenterScreen

    outer = DockPanel()
    outer.LastChildFill = True

    root = StackPanel()
    root.Margin = Thickness(16)

    title = TextBlock()
    title.Text = u"Категория «Формы» и параметры для клонирования"
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

    for key, section_title, label_text, hint_text, _, multiline, required in TEXT_FIELDS:
        section = TextBlock()
        section.Text = section_title
        section.FontWeight = FontWeights.Bold
        section.Margin = Thickness(0, 16, 0, 2)
        root.Children.Add(section)

        label = TextBlock()
        label.Text = label_text + (u" *" if required else u"")
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
        field_hint.Text = hint_text
        field_hint.FontSize = 11
        field_hint.Foreground = Brushes.Gray
        field_hint.TextWrapping = TextWrapping.Wrap
        field_hint.Margin = Thickness(0, 2, 0, 0)
        root.Children.Add(field_hint)

    # --- ③ какие элементы проверять -----------------------------------

    mode_section = TextBlock()
    mode_section.Text = u"③ Какие элементы проверять на попадание в форму"
    mode_section.FontWeight = FontWeights.Bold
    mode_section.Margin = Thickness(0, 16, 0, 2)
    root.Children.Add(mode_section)

    current_mode = values.get(MODE_KEY, MODE_DEFAULT)

    rb_view = RadioButton()
    rb_view.Content = u"Все элементы на активном виде"
    rb_view.GroupName = u"loi_selection_mode"
    rb_view.Margin = Thickness(0, 4, 0, 2)
    rb_view.IsChecked = (current_mode == MODE_VIEW)
    root.Children.Add(rb_view)

    rb_all = RadioButton()
    rb_all.Content = u"Все элементы документа (без учёта вида)"
    rb_all.GroupName = u"loi_selection_mode"
    rb_all.Margin = Thickness(0, 2, 0, 2)
    rb_all.IsChecked = (current_mode == MODE_ALL)
    root.Children.Add(rb_all)

    rb_types = RadioButton()
    rb_types.Content = u"Только выбранные типы семейств"
    rb_types.GroupName = u"loi_selection_mode"
    rb_types.Margin = Thickness(0, 2, 0, 2)
    rb_types.IsChecked = (current_mode == MODE_TYPES)
    root.Children.Add(rb_types)

    types_row = StackPanel()
    types_row.Orientation = Orientation.Horizontal
    types_row.Margin = Thickness(20, 6, 0, 0)

    types_pick_btn = Button()
    types_pick_btn.Content = u"Выбрать типы…"
    types_pick_btn.Padding = Thickness(8, 2, 8, 2)
    types_row.Children.Add(types_pick_btn)

    types_label = TextBlock()
    types_label.Text = _types_label_text(state["type_ids"], None)
    types_label.VerticalAlignment = VerticalAlignment.Center
    types_label.Margin = Thickness(8, 0, 0, 0)
    types_label.TextWrapping = TextWrapping.Wrap
    types_row.Children.Add(types_label)

    root.Children.Add(types_row)

    def on_pick_types(sender, args):
        exclude_name = boxes["form_category_name"].Text.strip() or u"Форма"
        options = loi_fill.list_candidate_types(doc, exclude_name)
        if not options:
            forms.alert(
                u"В документе не найдено модельных элементов с типами (кроме "
                u"категории «{}»).".format(exclude_name)
            )
            return

        checked_ids = set(state["type_ids"])
        items = [forms.TemplateListItem(o, checked=(o.type_id.IntegerValue in checked_ids))
                 for o in options]

        chosen = forms.SelectFromList.show(
            items,
            title=u"Типы семейств — кандидаты для заполнения LOI",
            button_name=u"Сохранить",
            multiselect=True
        )
        if chosen is None:
            return

        state["type_ids"] = [o.type_id.IntegerValue for o in chosen]
        types_label.Text = _types_label_text(state["type_ids"], options)
        rb_types.IsChecked = True

    types_pick_btn.Click += on_pick_types

    types_hint = TextBlock()
    types_hint.Text = (
        u"Учитываются только при выбранном режиме «Только выбранные типы "
        u"семейств» — поиск идёт по всему документу, без привязки к виду."
    )
    types_hint.FontSize = 11
    types_hint.Foreground = Brushes.Gray
    types_hint.TextWrapping = TextWrapping.Wrap
    types_hint.Margin = Thickness(0, 4, 0, 0)
    root.Children.Add(types_hint)

    # --- ④ разбиение элементов на границе форм --------------------------

    split_section = TextBlock()
    split_section.Text = u"④ Элемент сразу в нескольких формах"
    split_section.FontWeight = FontWeights.Bold
    split_section.Margin = Thickness(0, 16, 0, 2)
    root.Children.Add(split_section)

    split_cb = CheckBox()
    split_cb.Content = (
        u"Разрезать прямой линейный элемент (лоток, короб, труба…) по "
        u"границе форм и записать каждому куску значения его формы"
    )
    split_cb.Margin = Thickness(0, 4, 0, 2)
    split_cb.IsChecked = bool(values.get(SPLIT_KEY, SPLIT_DEFAULT))
    root.Children.Add(split_cb)

    split_hint = TextBlock()
    split_hint.Text = (
        u"Применяется только к прямым линейным элементам, физически "
        u"проходящим через границу нескольких форм. То, что разрезать не "
        u"удалось (кривые участки, точечные элементы, наложенные формы), "
        u"по-прежнему показывается в окне разрешения конфликтов, где форму-"
        u"источник для всего элемента выбирает пользователь."
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
    cancel_btn.Content = u"Отмена"
    cancel_btn.Padding = Thickness(10, 4, 10, 4)
    cancel_btn.Margin = Thickness(0, 0, 8, 0)

    ok_btn = Button()
    ok_btn.Content = u"Сохранить"
    ok_btn.Padding = Thickness(10, 4, 10, 4)
    ok_btn.FontWeight = FontWeights.Bold

    def on_ok(sender, args):
        combined = {key: box.Text for key, box in boxes.items()}
        if rb_all.IsChecked:
            combined[MODE_KEY] = MODE_ALL
        elif rb_types.IsChecked:
            combined[MODE_KEY] = MODE_TYPES
        else:
            combined[MODE_KEY] = MODE_VIEW
        combined[TYPE_IDS_KEY] = list(state["type_ids"])
        combined[SPLIT_KEY] = bool(split_cb.IsChecked)
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
    по умолчанию, если ещё не настроено). Используется кнопкой «Заполнение LOI»."""
    return load_saved_values()
