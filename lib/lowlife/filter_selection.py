# -*- coding: utf-8 -*-
"""
Кнопка «Фильтр выбора» (FilterSelection.panel/CategoryFilterSelect):
выделение элементов на активном виде, ограниченное отмеченными
категориями.

Обычный клик — run(): сразу запускает интерактивный выбор по категориям,
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

from Autodesk.Revit.DB import ElementId
from System.Collections.Generic import List

from pyrevit import forms

from lowlife.selection import (
    list_view_categories, pick_elements_by_categories, show_properties_palette
)

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
    Обычный клик: сразу интерактивный выбор по категориям из настроек,
    без диалога. Если список пуст или ни одна из сохранённых категорий не
    нашлась в этом документе — просит настроить (Shift+клик) и
    останавливает скрипт.
    """
    names = load_config()["category_names"]
    if not names:
        forms.alert(
            u"Категории для фильтра выбора ещё не настроены. Нажмите "
            u"кнопку с зажатым Shift, отметьте нужные категории и "
            u"сохраните — дальше обычный клик будет сразу выделять по "
            u"ним, без вопросов.",
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

    elements = pick_elements_by_categories(uidoc, doc, category_ids)

    # Явно фиксируем выбор как текущее выделение Revit, чтобы оно осталось
    # активным (подсветка, панель «Свойства») после завершения инструмента —
    # сами по себе результаты PickObjects этого не гарантируют.
    ids = List[ElementId]()
    for el in elements:
        ids.Add(el.Id)
    uidoc.Selection.SetElementIds(ids)

    # Сразу поднимаем вкладку «Свойства» — чтобы после выбора можно было
    # тут же менять параметры отмеченных элементов, не выцепляя вкладку
    # вручную (её обычно задвигает вкладка «Диспетчер проекта»).
    show_properties_palette()
