# -*- coding: utf-8 -*-
"""
Окно настроек кнопки «Проверка LOI» (LOI.panel/CheckLOI) + их хранение
между запусками.

Хранится в JSON-файле %APPDATA%\\pyRevit\\LowLifeLOICheck_settings.json —
тот же подход, что floor_settings.py/loi_settings.py (простой файл вместо
pyrevit.script.get_config()).

Настройки:
  - category_names — проверяемые категории, по имени (как в
    filter_selection.py: Id категорий не гарантированно совпадают между
    документами, имя стабильно);
  - labels_text — список параметров «как в требованиях LOI», по одному на
    строке (шаг ① — вписывается сначала);
  - param_map — {строка списка: имя параметра модели} (шаг ② — для каждой
    строки вписывается нужный параметр; пусто — берётся сама строка, см.
    loi_check_core.build_rows);
  - floor_param_name — параметр для столбца «Этаж»; пусто — тот же, что
    у кнопки «Заполнение этажа», а если и там пусто — уровень элемента;
  - appendix — импортированное приложение «Требования к LOI» (только
    выбранные разделы, см. loi_appendix.parse): если оно есть, при запуске
    кнопка спрашивает этап проверки (стадия · ПЧ/НЧ · подэтап) или «свой
    список» (категории и параметры выше);
  - last_stage — последний выбранный этап (предлагается первым).

Имена параметров и категорий из приложения хранятся только здесь, в файле
настроек пользователя, — в репозитории их нет.
"""

import clr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')

from pyrevit import forms

from lowlife import settings_core, settings_transfer, loi_check_core as core

from System.Collections.Generic import List

from System.Windows import (
    Window, WindowStartupLocation, Thickness,
    FontWeights, HorizontalAlignment, VerticalAlignment, TextWrapping
)
from System.Windows.Controls import (
    StackPanel, TextBlock, TextBox, Button, Orientation, DockPanel, Dock,
    ScrollViewer, ScrollBarVisibility,
    DataGrid, DataGridTextColumn, DataGridLength, DataGridLengthUnitType,
    DataGridHeadersVisibility, DataGridGridLinesVisibility, DataGridSelectionMode
)
from System.Windows.Data import Binding, BindingMode, UpdateSourceTrigger
from System.Windows.Media import Brushes

SETTINGS_FILE_NAME = "LowLifeLOICheck_settings.json"
BUTTON_NAME = u"Проверка LOI"

CATEGORIES_KEY = "category_names"
LABELS_KEY = "labels_text"
PARAM_MAP_KEY = "param_map"
FLOOR_KEY = "floor_param_name"
APPENDIX_KEY = "appendix"
LAST_STAGE_KEY = "last_stage"

MANUAL_TITLE = u"Свой список (категории и параметры из настроек)"


_STORE = settings_core.JsonStore(SETTINGS_FILE_NAME)
_settings_file_path = _STORE.path
_read_all = _STORE.read
_write_all = _STORE.write


def load_saved_values():
    """Значения настроек: из JSON-файла, иначе — значения по умолчанию."""
    saved = _read_all()
    names = saved.get(CATEGORIES_KEY, [])
    param_map = saved.get(PARAM_MAP_KEY, {})
    return {
        CATEGORIES_KEY: [unicode(n) for n in names] if isinstance(names, list) else [],
        LABELS_KEY: unicode(saved.get(LABELS_KEY, u"") or u""),
        PARAM_MAP_KEY: ({unicode(k): unicode(v) for k, v in param_map.items()}
                        if isinstance(param_map, dict) else {}),
        FLOOR_KEY: unicode(saved.get(FLOOR_KEY, u"") or u""),
        APPENDIX_KEY: saved.get(APPENDIX_KEY) if isinstance(saved.get(APPENDIX_KEY), dict) else None,
        LAST_STAGE_KEY: unicode(saved.get(LAST_STAGE_KEY, u"") or u""),
    }


def save_values(values):
    data = _read_all()
    data.update(values)
    _write_all(data)


def get_rows(settings):
    """[(строка списка, имя параметра)] — см. loi_check_core.build_rows."""
    labels = core.parse_labels(settings.get(LABELS_KEY))
    return core.build_rows(labels, settings.get(PARAM_MAP_KEY))


def get_floor_param(settings):
    """Параметр столбца «Этаж»: свой, иначе из «Заполнения этажа», иначе u""."""
    own = unicode(settings.get(FLOOR_KEY) or u"").strip()
    if own:
        return own
    try:
        from lowlife import floor_settings
        return unicode(floor_settings.load_saved_values().get(floor_settings.PARAM_KEY) or u"").strip()
    except Exception:
        return u""


def get_appendix(settings):
    appendix = settings.get(APPENDIX_KEY)
    return appendix if appendix and appendix.get("rules") else None


class _ModeOption(object):
    def __init__(self, title, stage):
        self.name = title
        self.stage = stage

    def __str__(self):
        return self.name


def choose_stage(settings):
    """
    Режим проверки при запуске. Без импортированного приложения — сразу
    «свой список» (возвращает None). Иначе — список этапов приложения +
    «свой список»; возвращает loi_check_core.Stage или None (свой список).
    Отмена — останавливает скрипт.
    """
    appendix = get_appendix(settings)
    if appendix is None:
        return None
    stages = core.list_stages(appendix)
    options = [_ModeOption(st.title, st) for st in stages]
    options.append(_ModeOption(MANUAL_TITLE, None))
    last = settings.get(LAST_STAGE_KEY)
    options.sort(key=lambda o: 0 if o.name == last else 1)

    chosen = forms.SelectFromList.show(
        options,
        title=u"Этап проверки LOI (стадия · ПЧ/НЧ · подэтап)",
        button_name=u"Проверить",
        multiselect=False
    )
    if chosen is None:
        raise SystemExit
    save_values({LAST_STAGE_KEY: chosen.name})
    return chosen.stage


def require(settings):
    """Останавливает скрипт через forms.alert(exitscript=True), если не
    выбраны категории или пуст список параметров."""
    missing = []
    if not settings.get(CATEGORIES_KEY):
        missing.append(u"Категории для проверки")
    if not get_rows(settings):
        missing.append(u"Список параметров")
    if missing:
        forms.alert(
            u"Не заполнены обязательные настройки:\n\n{}\n\n"
            u"Откройте настройки: Shift+клик по кнопке «{}».".format(
                u"\n".join(missing), BUTTON_NAME),
            exitscript=True
        )


# --- окно ----------------------------------------------------------------------

class _ParamRow(object):
    def __init__(self, label, param):
        self.Label = label
        self.Param = param


def _star(n):
    return DataGridLength(n, DataGridLengthUnitType.Star)


def _section(text, top=16):
    tb = TextBlock()
    tb.Text = text
    tb.FontWeight = FontWeights.Bold
    tb.Margin = Thickness(0, top, 0, 2)
    return tb


def _hint(text):
    tb = TextBlock()
    tb.Text = text
    tb.FontSize = 11
    tb.Foreground = Brushes.Gray
    tb.TextWrapping = TextWrapping.Wrap
    tb.Margin = Thickness(0, 2, 0, 4)
    return tb


def _appendix_label_text(appendix):
    if not appendix or not appendix.get("rules"):
        return u"Не загружено — проверяется только свой список ниже."
    return u"{}: {}. Элементов: {}, этапов: {}.".format(
        appendix.get("source") or u"Приложение",
        u"; ".join(appendix.get("sections") or []),
        len(appendix.get("rules") or []),
        len(core.list_stages(appendix)))


class _SectionOption(object):
    def __init__(self, name, count):
        self.raw_name = name
        self.name = u"{} ({})".format(name, count)

    def __str__(self):
        return self.name


def import_appendix(current=None):
    """
    Выбор файла приложения (Excel → «Таблица XML 2003») и разделов. Возвращает
    словарь для APPENDIX_KEY или None (отмена/ошибка — с сообщением).
    """
    import os
    from lowlife import loi_appendix

    path = forms.pick_file(file_ext="xml", title=u"Приложение «Требования к LOI» (XML)")
    if not path:
        return None
    try:
        appendix = loi_appendix.read_appendix(path)
    except Exception as ex:
        forms.alert(u"Не удалось разобрать файл:\n\n{}".format(ex), title=BUTTON_NAME)
        return None
    if not appendix["rules"]:
        forms.alert(u"В файле не найдено ни одного элемента с параметрами LOI.", title=BUTTON_NAME)
        return None

    counts = {}
    for rule in appendix["rules"]:
        counts[rule["section"]] = counts.get(rule["section"], 0) + 1
    was = set((current or {}).get("sections") or [])
    items = [forms.TemplateListItem(_SectionOption(name, counts.get(name, 0)),
                                    checked=(name in was))
             for name in appendix["sections"]]
    chosen = forms.SelectFromList.show(
        items,
        title=u"Разделы приложения для проверки (в скобках — число элементов)",
        button_name=u"Загрузить",
        multiselect=True
    )
    if not chosen:
        return None
    appendix = loi_appendix.select_sections(appendix, [o.raw_name for o in chosen])
    appendix["source"] = os.path.basename(path)
    return appendix


def _categories_label_text(names):
    if not names:
        return u"Категории не выбраны."
    preview = u"; ".join(sorted(names)[:6])
    if len(names) > 6:
        preview += u"; …"
    return u"Выбрано: {}. {}".format(len(names), preview)


def show_settings_form(doc, values):
    """Модальное окно настроек. Возвращает словарь значений или None (отмена)."""
    from lowlife import loi_check

    result = {"values": None}
    state = {
        "categories": list(values.get(CATEGORIES_KEY) or []),
        # все когда-либо вписанные соответствия — строку можно удалить из
        # списка и вернуть, не теряя вписанный для неё параметр
        "map": dict(values.get(PARAM_MAP_KEY) or {}),
        "appendix": values.get(APPENDIX_KEY),
    }

    win = Window()
    win.Title = u"Настройки: " + BUTTON_NAME
    win.Width = 720
    win.Height = 820
    win.WindowStartupLocation = WindowStartupLocation.CenterScreen

    outer = DockPanel()
    outer.LastChildFill = True

    root = StackPanel()
    root.Margin = Thickness(16)

    title = TextBlock()
    title.Text = u"Что проверять и какие столбцы выводить в спецификацию"
    title.FontSize = 16
    title.FontWeight = FontWeights.Bold
    root.Children.Add(title)
    root.Children.Add(_hint(u"Значения сохраняются и подставляются при следующих запусках."))

    # --- ① приложение LOI ----------------------------------------------------
    root.Children.Add(_section(u"① Требования LOI по этапам (приложение)", 8))

    app_row = StackPanel()
    app_row.Orientation = Orientation.Horizontal
    app_row.Margin = Thickness(0, 4, 0, 0)

    app_btn = Button()
    app_btn.Content = u"Загрузить приложение…"
    app_btn.Padding = Thickness(8, 2, 8, 2)
    app_row.Children.Add(app_btn)

    app_clear_btn = Button()
    app_clear_btn.Content = u"Убрать"
    app_clear_btn.Padding = Thickness(8, 2, 8, 2)
    app_clear_btn.Margin = Thickness(6, 0, 0, 0)
    app_row.Children.Add(app_clear_btn)
    root.Children.Add(app_row)

    app_label = TextBlock()
    app_label.Text = _appendix_label_text(state["appendix"])
    app_label.TextWrapping = TextWrapping.Wrap
    app_label.Margin = Thickness(0, 4, 0, 0)
    root.Children.Add(app_label)

    root.Children.Add(_hint(
        u"Таблица «Требования к LOI», сохранённая из Excel как «Таблица XML 2003» "
        u"(*.xml). Берутся выбранные разделы: категории Revit, классы с кодами "
        u"по классификатору и для каждого параметра — с какого подэтапа "
        u"(Б-1…, ПЭ-1…) он обязателен на стадии, отдельно ПЧ и НЧ. При запуске "
        u"кнопка спросит этап; у каждого элемента проверяются только параметры "
        u"его класса (по значению параметра кода классификатора)."))

    def on_import(sender, args):
        appendix = import_appendix(state["appendix"])
        if appendix is not None:
            state["appendix"] = appendix
            app_label.Text = _appendix_label_text(appendix)

    def on_clear(sender, args):
        state["appendix"] = None
        app_label.Text = _appendix_label_text(None)

    app_btn.Click += on_import
    app_clear_btn.Click += on_clear

    root.Children.Add(_section(u"Свой список — если этап из приложения не выбран"))

    # --- ② категории ---------------------------------------------------------
    root.Children.Add(_section(u"② Категории семейств", 8))

    cat_row = StackPanel()
    cat_row.Orientation = Orientation.Horizontal
    cat_row.Margin = Thickness(0, 4, 0, 0)

    cat_btn = Button()
    cat_btn.Content = u"Выбрать категории…"
    cat_btn.Padding = Thickness(8, 2, 8, 2)
    cat_row.Children.Add(cat_btn)

    cat_label = TextBlock()
    cat_label.Text = _categories_label_text(state["categories"])
    cat_label.VerticalAlignment = VerticalAlignment.Center
    cat_label.Margin = Thickness(8, 0, 0, 0)
    cat_label.TextWrapping = TextWrapping.Wrap
    cat_row.Children.Add(cat_label)
    root.Children.Add(cat_row)

    root.Children.Add(_hint(
        u"Проверяются все экземпляры отмеченных категорий в текущем файле. "
        u"По каждой категории строится своя спецификация."))

    def on_pick_categories(sender, args):
        options = loi_check.list_categories(doc)
        if not options:
            forms.alert(u"В документе нет модельных элементов.")
            return
        checked = set(n.lower() for n in state["categories"])
        items = [forms.TemplateListItem(o, checked=(o.raw_name.lower() in checked))
                 for o in options]
        chosen = forms.SelectFromList.show(
            items,
            title=u"Категории для проверки LOI (в скобках — число элементов)",
            button_name=u"Сохранить",
            multiselect=True
        )
        if chosen is None:
            return
        state["categories"] = [o.raw_name for o in chosen]
        cat_label.Text = _categories_label_text(state["categories"])

    cat_btn.Click += on_pick_categories

    # --- ② список параметров ---------------------------------------------------
    root.Children.Add(_section(u"③ Список параметров (по одному на строке) *"))
    root.Children.Add(_hint(
        u"Впишите параметры так, как они названы в требованиях LOI, — по "
        u"одному на строке. Строка станет заголовком столбца спецификации."))

    labels_box = TextBox()
    labels_box.Text = values.get(LABELS_KEY, u"")
    labels_box.AcceptsReturn = True
    labels_box.TextWrapping = TextWrapping.Wrap
    labels_box.Height = 130
    labels_box.Padding = Thickness(4)
    labels_box.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
    root.Children.Add(labels_box)

    # --- ③ параметр для каждой строки ----------------------------------------
    root.Children.Add(_section(u"④ Параметр модели для каждой строки"))
    root.Children.Add(_hint(
        u"Таблица повторяет список выше. Для каждой строки впишите имя "
        u"параметра в модели (экземпляра или типа), из которого брать значение. "
        u"Пусто — параметр с тем же именем, что и строка."))

    data = List[object]()

    grid = DataGrid()
    grid.Height = 220
    grid.AutoGenerateColumns = False
    grid.CanUserAddRows = False
    grid.CanUserDeleteRows = False
    grid.CanUserResizeRows = False
    grid.CanUserSortColumns = False
    grid.HeadersVisibility = DataGridHeadersVisibility.Column
    grid.GridLinesVisibility = DataGridGridLinesVisibility.Horizontal
    grid.SelectionMode = DataGridSelectionMode.Single
    grid.ItemsSource = data

    label_col = DataGridTextColumn()
    label_col.Header = u"Строка списка"
    label_col.Binding = Binding("Label")
    label_col.IsReadOnly = True
    label_col.Width = _star(1)
    grid.Columns.Add(label_col)

    param_binding = Binding("Param")
    param_binding.Mode = BindingMode.TwoWay
    param_binding.UpdateSourceTrigger = UpdateSourceTrigger.PropertyChanged
    param_col = DataGridTextColumn()
    param_col.Header = u"Параметр в модели"
    param_col.Binding = param_binding
    param_col.Width = _star(1)
    grid.Columns.Add(param_col)

    root.Children.Add(grid)

    def collect_grid():
        try:
            grid.CommitEdit()
        except Exception:
            pass
        for row in data:
            state["map"][row.Label] = unicode(row.Param or u"").strip()

    def refresh_grid():
        collect_grid()
        data.Clear()
        for label in core.parse_labels(labels_box.Text):
            data.Add(_ParamRow(label, state["map"].get(label, u"")))
        grid.ItemsSource = None
        grid.ItemsSource = data

    def on_labels_changed(sender, args):
        refresh_grid()

    refresh_grid()
    labels_box.TextChanged += on_labels_changed

    # --- ④ этаж -------------------------------------------------------------
    root.Children.Add(_section(u"⑤ Параметр для столбца «Этаж»"))
    floor_box = TextBox()
    floor_box.Text = values.get(FLOOR_KEY, u"")
    floor_box.Padding = Thickness(4)
    root.Children.Add(floor_box)
    root.Children.Add(_hint(
        u"Пусто — параметр из настроек кнопки «Заполнение этажа», а если "
        u"не задан и он — уровень элемента."))

    # --- кнопки ----------------------------------------------------------------
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
        collect_grid()
        labels = core.parse_labels(labels_box.Text)
        result["values"] = {
            CATEGORIES_KEY: list(state["categories"]),
            LABELS_KEY: u"\n".join(labels),
            PARAM_MAP_KEY: core.clean_param_map(labels, state["map"]),
            FLOOR_KEY: floor_box.Text.strip(),
            APPENDIX_KEY: state["appendix"],
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
        buttons, _read_all, _write_all, u"проверки LOI", _on_settings_imported
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
    """Окно настроек (Shift+клик); сохраняет и возвращает значения, None — отмена."""
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
    """Сохранённые настройки без показа окна."""
    return load_saved_values()
