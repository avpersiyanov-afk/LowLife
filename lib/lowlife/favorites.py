# -*- coding: utf-8 -*-
"""«Избранное» на ленте: свои панели пользователя из кнопок LowLife.

Настройки (`%APPDATA%\\pyRevit\\LowLifeFavorites_settings.json`) — список панелей и их кнопок,
логика — `favorites_core`. Здесь — построение панелей на вкладке LowLife через Revit API:

- панель избранного создаётся `UIApplication.CreateRibbonPanel` с именем
  `favorites_core.panel_name(подпись)` и ставится на ленте сразу за панелью «Мои панели»;
- кнопка избранного — `PushButtonData` с той же сборкой и классом команды, что у исходной кнопки
  pyRevit (`PushButton.AssemblyName`/`ClassName`): клик по ней — это запуск той же команды,
  с тем же Shift+кликом, движком и доступностью; подпись, подсказка и иконка — тоже от исходной;
- удалить панель или кнопку с ленты Revit API не даёт — убранные из избранного прячутся до
  перезапуска Revit (при повторном добавлении показываются те же).

pyRevit при перезагрузке прячет чужие панели вкладки и пересобирает свои кнопки в новую сборку,
поэтому `startup.py` после каждой загрузки вызывает `restore_on_idle` — при первом простое Revit
избранное строится заново (сборка и класс кнопок обновляются).
"""

try:
    unicode  # noqa: F821 — IronPython/Python 2
except NameError:  # Python 3
    unicode = str

from lowlife import favorites_core, ribbon_catalog

TAB_NAME = u"LowLife"
FAVORITES_PANEL_TITLE = u"Мои панели"  # Favorites.panel — title из bundle.yaml; панели пользователя — за ней

_STORE = None


def _store():
    global _STORE
    if _STORE is None:
        from lowlife import settings_core
        _STORE = settings_core.JsonStore("LowLifeFavorites_settings.json", u"избранного", share=False)
    return _STORE


def load():
    return favorites_core.normalize(_store().read())


def save(data):
    """True — записано (иначе JsonStore уже показал ошибку)."""
    return _store().write(favorites_core.normalize(data))


def reserved_titles():
    """Подписи панелей самого LowLife — панель избранного так называть нельзя."""
    titles = [title for title, _buttons in ribbon_catalog.list_panels()]
    return titles + [TAB_NAME, FAVORITES_PANEL_TITLE]


# ---------------------------------------------------------------- кнопки LowLife на ленте

def _panels(uiapp):
    try:
        return list(uiapp.GetRibbonPanels(TAB_NAME))
    except Exception:
        return []


def _child(items, name):
    for item in items:
        try:
            if item.Name == name:
                return item
        except Exception:
            pass
    return None


def source_button(uiapp, entry):
    """Revit-`PushButton` исходной кнопки LowLife (entry — из ribbon_catalog.list_buttons()) или None.

    pyRevit называет панель её подписью, а кнопку — именем папки; кнопка в выпадающем списке
    ищется по пути папок внутри него."""
    from Autodesk.Revit.UI import PushButton
    for panel in _panels(uiapp):
        if favorites_core.is_favorite_panel(panel.Name):
            continue
        if panel.Name not in (entry[u"panel_title"], entry[u"panel"]):
            continue
        item = None
        items = panel.GetItems()
        for name in entry[u"path"]:
            item = _child(items, name)
            if item is None:
                break
            try:
                items = item.GetItems()
            except Exception:
                items = []
        if isinstance(item, PushButton):
            return item
    return None


# ---------------------------------------------------------------- Autodesk.Windows: порядок и видимость

def _adwin_tab():
    import clr
    clr.AddReference("AdWindows")
    from Autodesk.Windows import ComponentManager
    for tab in ComponentManager.Ribbon.Tabs:
        if tab.Title == TAB_NAME or tab.Id == TAB_NAME:
            return tab
    return None


def _adwin_panel(tab, name=None, title=None):
    for panel in tab.Panels:
        source = panel.Source
        if source is None:
            continue
        if title is not None and source.Title == title:
            return panel
        if name is not None and unicode(source.Id or u"").endswith(name):
            return panel
    return None


def _move(collection, item, index):
    """Поставить item на место index в коллекции ленты (ObservableCollection)."""
    current = collection.IndexOf(item)
    if current < 0 or current == index:
        return
    try:
        collection.Move(current, index)
    except Exception:
        collection.Remove(item)
        collection.Insert(min(index, collection.Count), item)


def _arrange(shown):
    """Панели избранного — сразу за панелью «Мои панели», кнопки — в порядке настроек.

    shown — [(подпись, имя панели, [имена кнопок])]. Без Autodesk.Windows ничего не делает:
    панели просто останутся в конце вкладки."""
    tab = _adwin_tab()
    if tab is None:
        return
    anchor = _adwin_panel(tab, title=FAVORITES_PANEL_TITLE)
    for i, (title, name, buttons) in enumerate(shown):
        panel = _adwin_panel(tab, name=name) or _adwin_panel(tab, title=title)
        if panel is None:
            continue
        panel.IsVisible = True
        if anchor is not None:
            _move(tab.Panels, panel, min(tab.Panels.IndexOf(anchor) + 1 + i, tab.Panels.Count - 1))
        items = panel.Source.Items
        for j, button in enumerate(buttons):
            item = next((it for it in items if unicode(it.Id or u"").endswith(u"%" + button)), None)
            if item is not None:
                _move(items, item, j)


def _hide_adwin_panel(name, title):
    tab = _adwin_tab()
    panel = tab and (_adwin_panel(tab, name=name) or _adwin_panel(tab, title=title))
    if panel is not None:
        panel.IsVisible = False


# ---------------------------------------------------------------- построение избранного

def _copy_look(button, source):
    """Подпись, подсказка и иконки — как у исходной кнопки."""
    for attr in ("ItemText", "ToolTip", "LongDescription", "LargeImage", "Image"):
        try:
            value = getattr(source, attr)
            if value is not None:
                setattr(button, attr, value)
        except Exception:
            pass


def _new_button(panel, name, source):
    from Autodesk.Revit.UI import PushButtonData
    data = PushButtonData(name, source.ItemText or name, source.AssemblyName, source.ClassName)
    try:
        if source.AvailabilityClassName:
            data.AvailabilityClassName = source.AvailabilityClassName
    except Exception:
        pass
    button = panel.AddItem(data)
    _copy_look(button, source)
    return button


def _update_button(button, source):
    # после перезагрузки pyRevit команды лежат в новой сборке — без этого кнопка запускала бы старую
    for attr in ("AssemblyName", "ClassName", "AvailabilityClassName"):
        try:
            value = getattr(source, attr)
            if value and getattr(button, attr) != value:
                setattr(button, attr, value)
        except Exception:
            pass
    _copy_look(button, source)


def _sync_panel(uiapp, panel, refs, entries, problems):
    """Кнопки одной панели избранного: нужные показать/создать, остальные спрятать. Имена показанных."""
    existing = dict((item.Name, item) for item in panel.GetItems())
    shown = []
    for ref in refs:
        entry = favorites_core.find_entry(entries, ref)
        source = source_button(uiapp, entry) if entry is not None else None
        if source is None:
            problems.append(u"«{}»: кнопки {} больше нет на ленте LowLife.".format(
                panel.Title, favorites_core.button_key(ref)))
            continue
        name = favorites_core.button_name(ref)
        button = existing.get(name)
        try:
            if button is None:
                button = _new_button(panel, name, source)
            else:
                _update_button(button, source)
            button.Visible = True
            button.Enabled = True
            shown.append(name)
        except Exception as ex:
            problems.append(u"«{}»: не удалось добавить «{}» — {}".format(panel.Title, entry[u"title"], ex))
    for name, item in existing.items():
        if name not in shown:
            item.Visible = False
    return shown


def sync(uiapp, data=None):
    """Строит избранное на ленте по настройкам (data — по умолчанию сохранённые). Список проблем."""
    data = favorites_core.normalize(data if data is not None else load())
    entries = ribbon_catalog.list_buttons()
    problems = []
    panels = dict((p.Name, p) for p in _panels(uiapp) if favorites_core.is_favorite_panel(p.Name))
    shown = []
    for cfg in data[u"panels"]:
        name = favorites_core.panel_name(cfg[u"title"])
        panel = panels.pop(name, None)
        if panel is None:
            if not cfg[u"buttons"]:
                continue  # пустую панель не создаём — её всё равно нечем заполнить
            try:
                panel = uiapp.CreateRibbonPanel(TAB_NAME, name)
            except Exception as ex:
                problems.append(u"Панель «{}» не создана — {}".format(cfg[u"title"], ex))
                continue
        panel.Title = cfg[u"title"]
        buttons = _sync_panel(uiapp, panel, cfg[u"buttons"], entries, problems)
        panel.Visible = bool(buttons)
        if buttons:
            shown.append((cfg[u"title"], name, buttons))
        else:
            _safe(_hide_adwin_panel, name, cfg[u"title"])
    for name, panel in panels.items():  # убранные из избранного
        panel.Visible = False
        _safe(_hide_adwin_panel, name, panel.Title)
    _safe(_arrange, shown)
    return problems


def _safe(fn, *args):
    try:
        fn(*args)
    except Exception:
        pass  # порядок и скрытие через Autodesk.Windows — удобство, сами кнопки уже на ленте


def restore_on_idle(app):
    """Из startup.py: построить избранное при первом простое Revit (лента к этому времени готова)."""
    state = {"done": False}

    def on_idle(sender, args):
        if state["done"]:
            return
        state["done"] = True
        try:
            app.Idling -= on_idle
        except Exception:
            pass
        try:
            sync(sender)
        except Exception:
            pass

    app.Idling += on_idle
