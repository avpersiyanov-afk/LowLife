# -*- coding: utf-8 -*-
"""
Окно настроек кнопки «Модель → JSON» (ToolsSchedules.panel/ModelToJson) +
их хранение между запусками: ЧТО попадает в снимок модели.

Хранится в JSON-файле %APPDATA%\\pyRevit\\LowLifeJsonSnapshot_settings.json —
тот же подход, что room_finder_settings.py/loi_settings.py/scs_settings.py
(простой файл вместо pyrevit.script.get_config(), см. их докстринги про
причину).

Настройки:
  - scope               — область: активный вид / выделенные элементы /
                          весь документ (json_snapshot.SCOPE_*);
  - categories_text     — категории по имени, по одной на строке (пусто —
                          все категории модели);
  - param_names_text    — параметры по имени, по одному на строке (пусто —
                          все параметры экземпляра);
  - include_readonly    — добавлять параметры только для чтения (для
                          анализа: длины, вычисляемые значения);
  - include_type_params — добавлять параметры типа (только для анализа);
  - include_empty       — выгружать и пустые значения (нужно, если в
                          снимке предполагается ЗАПОЛНЯТЬ пустые параметры —
                          так их имена видны сразу);
  - include_circuits    — добавлять электрические цепи выгружаемых
                          элементов, с панелью и составом цепи;
  - include_location    — координаты и поворот элементов (мм, градусы) —
                          при загрузке по ним элементы перемещаются;
  - include_tags        — марки выгружаемых элементов (положение головы
                          марки тоже загружается обратно);
  - include_rooms       — помещения и пространства (текущая модель + связи)
                          с контурами и привязкой элементов к ним;
  - room_param_names_text — какие параметры помещений/пространств добавить
                          в "rooms" (по одному на строке);
  - include_catalog     — каталог загруженных типоразмеров ("catalog") —
                          из него выбирают, что создавать в "new".
Без настройки кнопка работает со значениями по умолчанию (активный вид,
все категории, все параметры) — обязательных полей нет.
"""

import os
import io
import json

import clr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')

from pyrevit import forms

from lowlife import settings_transfer
from lowlife import json_snapshot
from lowlife import json_snapshot_rooms

from System.Windows import (
    Window, WindowStartupLocation, Thickness,
    FontWeights, HorizontalAlignment, TextWrapping
)
from System.Windows.Controls import (
    StackPanel, TextBlock, TextBox, Button, CheckBox, RadioButton,
    Orientation, DockPanel, Dock, ScrollViewer, ScrollBarVisibility
)
from System.Windows.Media import Brushes

SETTINGS_FILE_NAME = "LowLifeJsonSnapshot_settings.json"

SCOPE_KEY = "scope"
CATEGORIES_KEY = "categories_text"
PARAMS_KEY = "param_names_text"
ROOM_PARAMS_KEY = "room_param_names_text"

# (ключ, подпись, пояснение, по умолчанию)
FLAGS = [
    ("include_readonly", u"Параметры только для чтения",
     u"Параметры, которые Revit не даёт менять вручную (длины, вычисляемые "
     u"значения, ссылки на элементы). Попадают в раздел \"readonly\" — их видно "
     u"при анализе, но при загрузке файла обратно в модель они не меняются.", True),
    ("include_type_params", u"Параметры типа",
     u"Добавляет параметры типоразмера в раздел \"type_params\" — только для "
     u"просмотра: параметр типа общий для всех экземпляров этого типа, поэтому "
     u"при загрузке файла обратно он не меняется.", False),
    ("include_empty", u"Пустые значения",
     u"Выгружать и незаполненные параметры. Включите, если в снимке нужно "
     u"ЗАПОЛНЯТЬ пустые параметры (например LOI) — так их имена видны сразу.",
     False),
    ("include_circuits", u"Электрические цепи выгружаемых элементов",
     u"Добавляет цепи, в которые входят элементы (как устройство или как "
     u"панель), с панелью и составом цепи в \"circuit\". Параметры цепи "
     u"(имя нагрузки, номер и т.п.) можно править так же, как у элементов.",
     True),
    ("include_location", u"Координаты и поворот элементов (можно править)",
     u"Точка вставки и поворот или начало/конец линейного элемента, в мм. "
     u"Изменённые в файле координаты при загрузке перемещают и поворачивают "
     u"элемент (с предпросмотром).", False),
    ("include_tags", u"Марки выгружаемых элементов (положение можно править)",
     u"Марки этих элементов — на активном виде (если выгружается активный "
     u"вид) или на всех видах. Изменённое \"tag_head_mm\" при загрузке "
     u"переносит голову марки.", False),
    ("include_rooms", u"Помещения и пространства (в т.ч. из связей)",
     u"Раздел \"rooms\": номер, имя, уровень, площадь, объём, высота и "
     u"контур каждого помещения/пространства на уровнях выгружаемых "
     u"элементов, плюс у каждого элемента — в каком помещении и "
     u"пространстве он стоит. Только для анализа. Параметры помещений — "
     u"список ниже.", False),
    ("include_catalog", u"Каталог загруженных типоразмеров (для создания новых)",
     u"Раздел \"catalog\": семейства и типоразмеры выбранных категорий (или "
     u"категорий выгружаемых элементов), способ размещения, сколько уже "
     u"расставлено и пример экземпляра. Из него выбираются \"family\"/"
     u"\"type\" (или \"copy_of\") для новых элементов в разделе \"new\".",
     False),
]

SCOPE_LABELS = [
    (json_snapshot.SCOPE_VIEW, u"Элементы активного вида"),
    (json_snapshot.SCOPE_SELECTION, u"Выделенные элементы"),
    (json_snapshot.SCOPE_ALL, u"Весь документ"),
]


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
    """Значения настроек: из JSON-файла, иначе — значения по умолчанию."""
    saved = _read_all()
    scope = saved.get(SCOPE_KEY, json_snapshot.SCOPE_VIEW)
    if scope not in [k for k, _label in SCOPE_LABELS]:
        scope = json_snapshot.SCOPE_VIEW
    values = {
        SCOPE_KEY: scope,
        CATEGORIES_KEY: saved.get(CATEGORIES_KEY, u"") or u"",
        PARAMS_KEY: saved.get(PARAMS_KEY, u"") or u"",
        ROOM_PARAMS_KEY: saved.get(ROOM_PARAMS_KEY, u"") or u"",
    }
    for key, _label, _hint, default in FLAGS:
        values[key] = bool(saved.get(key, default))
    return values


def save_values(values):
    data = _read_all()
    data.update(values)
    _write_all(data)


def _lines(text):
    out = []
    seen = set()
    for line in (text or u"").splitlines():
        s = line.strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def to_options(settings):
    """Настройки -> options для json_snapshot.collect_elements/build_snapshot."""
    options = {
        "scope": settings.get(SCOPE_KEY) or json_snapshot.SCOPE_VIEW,
        "categories": _lines(settings.get(CATEGORIES_KEY)),
        "param_names": _lines(settings.get(PARAMS_KEY)),
        "room_param_names": _lines(settings.get(ROOM_PARAMS_KEY)),
    }
    for key, _label, _hint, default in FLAGS:
        options[key] = bool(settings.get(key, default))
    return options


class _NameOption(object):
    """Строка списка для forms.SelectFromList."""

    def __init__(self, key, label=None):
        self.key = key
        self.name = label or key

    def __str__(self):
        return self.name


def _section(root, text):
    tb = TextBlock()
    tb.Text = text
    tb.FontWeight = FontWeights.Bold
    tb.Margin = Thickness(0, 16, 0, 2)
    root.Children.Add(tb)


def _hint(root, text):
    tb = TextBlock()
    tb.Text = text
    tb.FontSize = 11
    tb.Foreground = Brushes.Gray
    tb.TextWrapping = TextWrapping.Wrap
    tb.Margin = Thickness(0, 2, 0, 0)
    root.Children.Add(tb)


def _multiline_box(root, text):
    box = TextBox()
    box.Text = text
    box.AcceptsReturn = True
    box.TextWrapping = TextWrapping.NoWrap
    box.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
    box.MinHeight = 90
    box.MaxHeight = 160
    box.Padding = Thickness(4)
    root.Children.Add(box)
    return box


def _pick_button(root, caption):
    row = StackPanel()
    row.Orientation = Orientation.Horizontal
    row.Margin = Thickness(0, 4, 0, 4)
    btn = Button()
    btn.Content = caption
    btn.Padding = Thickness(8, 2, 8, 2)
    row.Children.Add(btn)
    root.Children.Add(row)
    return btn


def show_settings_form(doc, values):
    """Модальное окно редактирования настроек. Возвращает словарь значений
    или None, если пользователь отменил."""
    result = {"values": None}

    win = Window()
    win.Title = u"Настройки: Модель → JSON"
    win.Width = 760
    win.Height = 820
    win.WindowStartupLocation = WindowStartupLocation.CenterScreen

    outer = DockPanel()
    outer.LastChildFill = True

    root = StackPanel()
    root.Margin = Thickness(16)

    title = TextBlock()
    title.Text = u"Что выгружать в снимок модели"
    title.FontSize = 16
    title.FontWeight = FontWeights.Bold
    title.Margin = Thickness(0, 0, 0, 4)
    root.Children.Add(title)

    hint = TextBlock()
    hint.Text = (u"Значения сохраняются и подставляются при следующих запусках. "
                 u"Чем уже выгрузка, тем меньше файл и тем легче его разобрать.")
    hint.FontSize = 11
    hint.Foreground = Brushes.Gray
    hint.TextWrapping = TextWrapping.Wrap
    hint.Margin = Thickness(0, 0, 0, 4)
    root.Children.Add(hint)

    # --- ① область ---------------------------------------------------------
    _section(root, u"① Какие элементы")
    scope_buttons = {}
    for key, label in SCOPE_LABELS:
        rb = RadioButton()
        rb.Content = label
        rb.GroupName = "json_snapshot_scope"
        rb.Margin = Thickness(0, 2, 0, 2)
        rb.IsChecked = (values.get(SCOPE_KEY) == key)
        root.Children.Add(rb)
        scope_buttons[key] = rb
    _hint(root, u"Активный вид — то, что видно на текущем плане/3D-виде или в "
                u"текущей спецификации. Электрические цепи на виде не видны — "
                u"их добавляет флажок «Электрические цепи» ниже.")

    # --- ② категории -------------------------------------------------------
    _section(root, u"② Категории (по одной на строке)")
    cat_box = _multiline_box(root, values.get(CATEGORIES_KEY, u""))
    cat_btn = _pick_button(root, u"Выбрать из модели…")
    _hint(root, u"Имена категорий как в Revit. Пусто — все категории модели "
                u"(без аннотаций, осей, уровней и видов).")

    def on_pick_categories(sender, args):
        names = json_snapshot.list_model_category_names(doc)
        if not names:
            forms.alert(u"В документе не найдено элементов модели.")
            return
        checked = set(_lines(cat_box.Text))
        items = [forms.TemplateListItem(_NameOption(n), checked=(n in checked))
                 for n in names]
        chosen = forms.SelectFromList.show(
            items,
            title=u"Категории для выгрузки",
            button_name=u"Выбрать",
            multiselect=True
        )
        if chosen is None:
            return
        cat_box.Text = u"\r\n".join(o.key for o in chosen)

    cat_btn.Click += on_pick_categories

    # --- ③ параметры -------------------------------------------------------
    _section(root, u"③ Параметры (по одному на строке)")
    param_box = _multiline_box(root, values.get(PARAMS_KEY, u""))
    param_btn = _pick_button(root, u"Выбрать из модели…")
    _hint(root, u"Имена параметров экземпляра (и типа, если включено ниже). "
                u"Пусто — все параметры. Список «Выбрать из модели» берётся по "
                u"категориям из пункта ②; «✎» — параметр можно править.")

    def on_pick_params(sender, args):
        pairs = json_snapshot.list_param_names(doc, _lines(cat_box.Text))
        if not pairs:
            forms.alert(u"Не найдено ни одного параметра у элементов "
                        u"выбранных категорий.")
            return
        checked = set(_lines(param_box.Text))
        items = [
            forms.TemplateListItem(
                _NameOption(n, (u"✎ " if writable else u"    ") + n),
                checked=(n in checked))
            for n, writable in pairs
        ]
        chosen = forms.SelectFromList.show(
            items,
            title=u"Параметры для выгрузки",
            button_name=u"Выбрать",
            multiselect=True
        )
        if chosen is None:
            return
        param_box.Text = u"\r\n".join(o.key for o in chosen)

    param_btn.Click += on_pick_params

    # --- ④ дополнительно ---------------------------------------------------
    _section(root, u"④ Дополнительно")
    flag_boxes = {}
    for key, label, hint_text, _default in FLAGS:
        cb = CheckBox()
        cb.Content = label
        cb.IsChecked = bool(values.get(key))
        cb.Margin = Thickness(0, 8, 0, 0)
        root.Children.Add(cb)
        flag_boxes[key] = cb
        _hint(root, hint_text)

    # --- ⑤ параметры помещений ---------------------------------------------
    _section(root, u"⑤ Параметры помещений и пространств (по одному на строке)")
    room_box = _multiline_box(root, values.get(ROOM_PARAMS_KEY, u""))
    room_btn = _pick_button(root, u"Выбрать из модели…")
    _hint(root, u"Добавляются в раздел \"rooms\", если включён флажок "
                u"«Помещения и пространства». Номер, имя, уровень, площадь, "
                u"объём, высота и контур выгружаются всегда. Для воздушного "
                u"баланса — параметры расходов пространств.")

    def on_pick_room_params(sender, args):
        pairs = json_snapshot_rooms.list_room_param_names(doc)
        if not pairs:
            forms.alert(u"Не найдено ни одного размещённого помещения или "
                        u"пространства ни в модели, ни в связях.")
            return
        checked = set(_lines(room_box.Text))
        items = [
            forms.TemplateListItem(
                _NameOption(n, u"{}  [{}]".format(n, kinds)),
                checked=(n in checked))
            for n, kinds in pairs
        ]
        chosen = forms.SelectFromList.show(
            items,
            title=u"Параметры помещений/пространств",
            button_name=u"Выбрать",
            multiselect=True
        )
        if chosen is None:
            return
        room_box.Text = u"\r\n".join(o.key for o in chosen)

    room_btn.Click += on_pick_room_params

    # --- нижний ряд кнопок -------------------------------------------------
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
        combined = {
            CATEGORIES_KEY: cat_box.Text,
            PARAMS_KEY: param_box.Text,
            ROOM_PARAMS_KEY: room_box.Text,
            SCOPE_KEY: json_snapshot.SCOPE_VIEW,
        }
        for key, rb in scope_buttons.items():
            if rb.IsChecked:
                combined[SCOPE_KEY] = key
        for key, cb in flag_boxes.items():
            combined[key] = bool(cb.IsChecked)
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
        buttons, _read_all, _write_all, u"выгрузки JSON", _on_settings_imported
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
    по Shift+клику на кнопке «Модель → JSON».
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
    """Настройки без показа окна — сохранённые значения или значения по
    умолчанию. Используется кнопкой «Модель → JSON»."""
    return load_saved_values()
