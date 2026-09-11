# -*- coding: utf-8 -*-
"""
Кнопка «Фильтр выбора» (FilterSelection.panel/CategoryFilterSelect):
ограничивает, что попадает в выделение на активном виде, отмеченными
категориями — не трогая видимость остальных элементов и не блокируя
панель «Свойства».

История подхода (важно, чтобы не наступить на те же грабли):
1. Сначала — ``uidoc.Selection.PickObjects`` с ``ISelectionFilter`` по
   категориям. Проблема: пока PickObjects ждёт клики, Revit блокирует
   панель «Свойства» (она живёт в контексте штатного выделения, а не
   API-команды) — параметры были видны только после Enter.
2. Затем — ``View.IsolateCategoriesTemporary`` (как штатный Isolate
   Category). Панель «Свойства» при этом работает, но остальные категории
   пропадают с экрана — пользователю они тоже нужны видимыми.
3. Текущий подход: подписка на ``UIApplication.SelectionChanged``. run()
   включает фильтр — ничего не скрывает и не запускает никакой пик,
   просто взводит флаг. Дальше пользователь выделяет элементы СОВЕРШЕННО
   штатно (клик/рамка/Ctrl) — это обычное выделение Revit, не API-пик,
   поэтому панель «Свойства» ведёт себя как всегда. Обработчик на каждое
   изменение выделения тут же обрезает его до элементов разрешённых
   категорий через ``uidoc.Selection.SetElementIds`` (не запускает
   транзакцию — это только выбор, не правка модели), остальные элементы
   просто не попадают в выделение, но остаются на экране. Повторный клик
   по кнопке выключает фильтр.

Подписка на событие — общая на весь процесс Revit
(``System.AppDomain.CurrentDomain``), как у ``export_watcher.py``: у
каждого движка pyRevit свой ``sys``, поэтому подписываться заново на
каждый клик нельзя — задвоится. ``run()`` подписывается один раз лениво
(при первом включении фильтра), дальше только переключает ``enabled``.

Shift+клик — configure(): чек-лист категорий активного вида, отмеченное
сохраняется на следующее включение. Тот же приём Shift+клика, что у
export_rename.configure()/RenameExportFiles.pushbutton.

Настройки — обычный JSON-файл в
%APPDATA%\\pyRevit\\LowLifeFilterSelection_settings.json (тот же подход,
что у scs_settings.py/export_rename.py — не pyrevit.script.get_config()).
Хранятся ИМЕНА категорий, а не ElementId: Id пользовательских категорий
не гарантированно совпадает между документами. Для сравнения с реальным
выделением имена резолвятся в id по текущему документу (resolve_category_ids).
"""

import os
import io
import json

from Autodesk.Revit.DB import ElementId
from System.Collections.Generic import List

from pyrevit import forms

from lowlife.selection import list_view_categories

SETTINGS_FILE_NAME = "LowLifeFilterSelection_settings.json"

DEFAULTS = {
    # имена категорий, отмеченных в прошлый раз (Shift+клик, configure())
    "category_names": [],
}

# Состояние фильтра — общее на процесс Revit, не на модуль (у каждого
# движка pyRevit свой sys/свои импорты, см. export_watcher._pg()).
_SYS_KEY = "LowLife_FilterSelection_State"
_STATE_DEFAULTS = {
    "enabled": False,        # фильтр сейчас активен
    "category_ids": None,    # set(int) разрешённых категорий, пока активен
    "installed": False,      # обработчик SelectionChanged подписан
    "host": None,            # UIApplication, на который подписались (держим ссылку)
    "delegate": None,        # сам обработчик (держим ссылку — иначе GC съест)
    "suppress": False,       # True внутри нашего же SetElementIds — не реагировать рекурсивно
}
_STATE_FALLBACK = {}


def _state():
    try:
        from System import AppDomain
        dom = AppDomain.CurrentDomain
        d = dom.GetData(_SYS_KEY)
        if d is None:
            d = dict(_STATE_DEFAULTS)
            dom.SetData(_SYS_KEY, d)
    except Exception:
        d = _STATE_FALLBACK
    for k, v in _STATE_DEFAULTS.items():
        if k not in d:
            d[k] = v
    return d


def _settings_file_path():
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    folder = os.path.join(appdata, "pyRevit")

    if not os.path.isdir(folder):
        try:
            os.makedirs(folder)
        except Exception:
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
    except Exception:
        return {}


def _write_all(data):
    path = _settings_file_path()

    try:
        with io.open(path, "w", encoding="utf-8") as f:
            f.write(unicode(json.dumps(data, ensure_ascii=False,
                                       indent=2, sort_keys=True)))
        return True
    except Exception:
        forms.alert(
            u"Не удалось сохранить настройки фильтра выбора в файл:\n{}".format(path)
        )
        return False


def load_config():
    """Настройки из JSON-файла поверх :data:`DEFAULTS`."""
    cfg = dict(DEFAULTS)
    saved = _read_all()
    if isinstance(saved, dict) and isinstance(saved.get("category_names"), list):
        cfg["category_names"] = [unicode(n) for n in saved["category_names"]
                                  if unicode(n).strip()]
    return cfg


def save_config(cfg):
    data = _read_all()
    if not isinstance(data, dict):
        data = {}
    data["category_names"] = list(cfg.get("category_names") or [])
    return _write_all(data)


def resolve_category_ids(doc, names):
    """Имена категорий -> набор int (Category.Id.IntegerValue), какие
    нашлись в этом документе. Регистр не важен."""
    wanted = set(unicode(n).lower() for n in names)
    ids = set()
    for cat in doc.Settings.Categories:
        try:
            nm = cat.Name
        except Exception:
            continue
        if nm and nm.lower() in wanted:
            ids.add(cat.Id.IntegerValue)
    return ids


def configure(doc, view):
    """
    Shift+клик: чек-лист категорий активного вида, предвыбор — то, что
    отмечено сейчас. Сохраняет отметку в файл настроек; отмена
    (Esc/крестик) ничего не меняет.
    """
    options = list_view_categories(doc, view)
    if not options:
        forms.alert(
            u"На активном виде нет модельных элементов, по которым можно "
            u"настроить фильтр выбора.",
            title=u"Фильтр выбора",
            exitscript=True
        )

    saved_lower = set(n.lower() for n in load_config()["category_names"])

    items = [forms.TemplateListItem(o, checked=(o.sort_name in saved_lower))
             for o in options]

    chosen = forms.SelectFromList.show(
        items,
        title=u"Категории для фильтра выбора (можно несколько)",
        button_name=u"Сохранить",
        multiselect=True
    )

    if chosen is None:
        # окно закрыли крестиком/Esc — настройки не трогаем
        return

    names = [o.raw_name for o in chosen]
    save_config({"category_names": names})

    if names:
        forms.alert(
            u"Сохранено. Включение фильтра теперь будет ограничивать "
            u"выделение категориями:\n{}".format(u", ".join(sorted(names))),
            title=u"Фильтр выбора"
        )
    else:
        forms.alert(
            u"Список категорий очищен — включение фильтра снова "
            u"попросит настроить его (Shift+клик).",
            title=u"Фильтр выбора"
        )


def _category_id_of(doc, element_id):
    """int Category.Id выбранного элемента, либо None (нет категории/не
    нашёлся/удалён)."""
    try:
        el = doc.GetElement(element_id)
        if el is not None and el.Category is not None:
            return el.Category.Id.IntegerValue
    except Exception:
        pass
    return None


def _trim_to_categories(uidoc, doc, element_ids, category_ids):
    """Оставляет из element_ids только те, чья категория — в category_ids.
    Возвращает (List[ElementId] оставшихся, True если что-то отсеяли)."""
    keep = List[ElementId]()
    dropped = False
    for eid in element_ids:
        cat_id = _category_id_of(doc, eid)
        if cat_id is not None and cat_id in category_ids:
            keep.Add(eid)
        else:
            dropped = True
    return keep, dropped


def _on_selection_changed(sender, args):
    st = _state()
    if not st.get("enabled") or st.get("suppress"):
        return

    category_ids = st.get("category_ids")
    if not category_ids:
        return

    try:
        uidoc = sender.ActiveUIDocument
        if uidoc is None:
            return
        doc = uidoc.Document
    except Exception:
        return

    try:
        elem_ids = list(args.GetSelectedElements())
    except Exception:
        return

    keep, dropped = _trim_to_categories(uidoc, doc, elem_ids, category_ids)
    if not dropped:
        # уже только разрешённые категории — ничего трогать не нужно, это
        # самый частый случай (обычный клик по нужному элементу)
        return

    st["suppress"] = True
    try:
        uidoc.Selection.SetElementIds(keep)
    except Exception:
        pass
    finally:
        st["suppress"] = False


def _ensure_installed(uiapp):
    st = _state()
    if st.get("installed") or uiapp is None:
        return
    try:
        uiapp.SelectionChanged += _on_selection_changed
    except Exception:
        return
    st["installed"] = True
    st["host"] = uiapp
    st["delegate"] = _on_selection_changed


def run(doc, uidoc, view):
    """
    Обычный клик — переключатель. Выключен -> включает фильтр по
    категориям из настроек: дальше любое штатное выделение Revit (клик,
    рамка, Ctrl/Shift) обрезается до этих категорий обработчиком
    SelectionChanged; остальные элементы остаются видимыми, просто не
    попадают в выделение. Включён -> выключает, выделение снова работает
    без ограничений.

    Если список категорий пуст или ни одна из сохранённых не нашлась в
    этом документе — просит настроить (Shift+клик) и останавливает
    скрипт, не трогая текущее состояние фильтра.
    """
    st = _state()

    if st.get("enabled"):
        st["enabled"] = False
        forms.alert(
            u"Фильтр выбора выключен — выделение снова работает без "
            u"ограничений.",
            title=u"Фильтр выбора"
        )
        return

    names = load_config()["category_names"]
    if not names:
        forms.alert(
            u"Категории для фильтра выбора ещё не настроены. Нажмите "
            u"кнопку с зажатым Shift, отметьте нужные категории и "
            u"сохраните — дальше обычный клик будет включать "
            u"ограничение выбора ими, без вопросов.",
            title=u"Фильтр выбора",
            exitscript=True
        )

    category_ids = resolve_category_ids(doc, names)
    if not category_ids:
        forms.alert(
            u"Ни одна из сохранённых категорий ({}) не найдена в этом "
            u"документе. Настройте список заново — Shift+клик по "
            u"кнопке.".format(u", ".join(names)),
            title=u"Фильтр выбора",
            exitscript=True
        )

    from pyrevit import HOST_APP
    _ensure_installed(HOST_APP.uiapp)

    st["category_ids"] = set(category_ids)
    st["enabled"] = True

    # Если что-то уже выбрано прямо сейчас — сразу обрезаем под фильтр,
    # не дожидаясь следующего клика пользователя.
    try:
        current = list(uidoc.Selection.GetElementIds())
        keep, dropped = _trim_to_categories(uidoc, doc, current, category_ids)
        if dropped:
            uidoc.Selection.SetElementIds(keep)
    except Exception:
        pass

    forms.alert(
        u"Фильтр выбора включён. В выделение будут попадать только "
        u"категории:\n{}\n\n"
        u"Выбирайте элементы как обычно (клик, рамка, Ctrl/Shift) сколько "
        u"угодно раз — остальные категории останутся видимыми, просто не "
        u"будут попадать в выделение. Повторный клик по кнопке — "
        u"выключить.".format(u", ".join(sorted(names))),
        title=u"Фильтр выбора"
    )
