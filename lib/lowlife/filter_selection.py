# -*- coding: utf-8 -*-
"""
Кнопка «Фильтр выбора» (FilterSelection.panel/CategoryFilterSelect):
ограничивает, что можно выбрать на активном виде, отмеченными
категориями — через штатную временную изоляцию Revit (Isolate Category),
а не через модальный API-пик, чтобы панель «Свойства» продолжала работать
как обычно.

Обычный клик — run(): сразу накладывает изоляцию по категориям,
сохранённым в прошлый раз, без диалога. Shift+клик — configure(): чек-лист
категорий активного вида, отмеченное сохраняется на следующий обычный
клик. Тот же приём Shift+клика, что у
export_rename.configure()/RenameExportFiles.pushbutton.

Настройки — обычный JSON-файл в
%APPDATA%\\pyRevit\\LowLifeFilterSelection_settings.json (тот же подход,
что у scs_settings.py/export_rename.py — не pyrevit.script.get_config()).
Хранятся ИМЕНА категорий, а не ElementId: Id пользовательских категорий
не гарантированно совпадает между документами, а имя обычно стабильно.
"""

import os
import io
import json

from Autodesk.Revit.DB import ElementId, TemporaryViewMode
from System.Collections.Generic import List

from pyrevit import revit, forms

from lowlife.selection import list_view_categories

SETTINGS_FILE_NAME = "LowLifeFilterSelection_settings.json"

DEFAULTS = {
    # имена категорий, отмеченных в прошлый раз (Shift+клик, configure())
    "category_names": [],
}


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
            u"Сохранено. Обычный клик по кнопке теперь сразу выделяет "
            u"элементы категорий:\n{}".format(u", ".join(sorted(names))),
            title=u"Фильтр выбора"
        )
    else:
        forms.alert(
            u"Список категорий очищен — обычный клик по кнопке снова "
            u"попросит настроить фильтр (Shift+клик).",
            title=u"Фильтр выбора"
        )


def run(doc, uidoc, view):
    """
    Обычный клик: временно изолирует на активном виде категории из
    настроек (то же самое «Isolate Category», что в стандартном Revit —
    View.IsolateCategoriesTemporary). Дальше пользователь выбирает
    элементы сколько угодно раз обычным способом Revit (клик, рамка,
    Ctrl/Shift) — это штатное выделение, а не модальный API-пик
    (PickObjects), поэтому панель «Свойства» работает как всегда и сразу
    показывает параметры каждого выбранного элемента. Раньше здесь
    использовался PickObjects — но пока он ждёт клики, Revit блокирует
    панель «Свойства» (она относится к API-командам, а не к обычному
    выделению), и увидеть параметры можно было только после завершения
    выбора Enter'ом. Isolate этого недостатка лишён.

    Снять изоляцию — стандартными средствами Revit: значок в строке
    состояния окна вида (внизу) -> «Reset Temporary Hide/Isolate», либо
    просто повторный клик по этой кнопке (сначала сбрасывает прежнюю
    изоляцию, затем накладывает новую по актуальным настройкам).

    Если список пуст или ни одна из сохранённых категорий не нашлась в
    этом документе — просит настроить (Shift+клик) и останавливает
    скрипт.
    """
    names = load_config()["category_names"]
    if not names:
        forms.alert(
            u"Категории для фильтра выбора ещё не настроены. Нажмите "
            u"кнопку с зажатым Shift, отметьте нужные категории и "
            u"сохраните — дальше обычный клик будет сразу ограничивать "
            u"выбор ими, без вопросов.",
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

    id_list = List[ElementId]()
    for cid in category_ids:
        id_list.Add(ElementId(cid))

    with revit.Transaction(u"Фильтр выбора: изоляция категорий"):
        if view.IsInTemporaryViewMode(TemporaryViewMode.TemporaryHideIsolate):
            view.DisableTemporaryViewMode(TemporaryViewMode.TemporaryHideIsolate)
        view.IsolateCategoriesTemporary(id_list)
