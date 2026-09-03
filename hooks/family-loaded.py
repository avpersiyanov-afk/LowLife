# -*- coding: utf-8 -*-
"""
Авто-метка даты при ШТАТНОЙ загрузке семейства (меню Revit «Загрузить
семейство», перезагрузка из браузера и т.п.).

Если в настройках включено «ставить метку при штатной загрузке» и файл
семейства лежит внутри настроенной папки-каталога — сразу после загрузки
пишет скрытую метку даты (ExtensibleStorage) и, если задан, дублирует
дату в видимый текстовый параметр типа. Ничего не спрашивает.

Запись идёт в отдельной транзакции из обработчика события
FamilyLoadedIntoDocument. В некоторых версиях/контекстах Revit это может
быть запрещено — тогда метка просто не ставится (кнопки «Семейства из
каталога» / «Загрузить семейства» её всё равно проставляют).
"""

try:
    from pyrevit import EXEC_PARAMS
    from lowlife import family_catalog as fc
except Exception:
    fc = None


def _run():
    if fc is None or not fc.load_autostamp_enabled():
        return

    try:
        e = EXEC_PARAMS.event_args
        doc = e.Document
        path = e.FamilyPath
    except Exception:
        return
    if doc is None or not path:
        return

    fam = None
    try:
        fam = doc.GetElement(e.NewFamilyId)
    except Exception:
        fam = None
    if fam is None:
        try:
            fam = fc.find_family_by_name(doc, e.FamilyName)
        except Exception:
            fam = None
    if fam is None:
        return

    try:
        fc.stamp_loaded_family(doc, fam, path)
    except Exception:
        pass


_run()
