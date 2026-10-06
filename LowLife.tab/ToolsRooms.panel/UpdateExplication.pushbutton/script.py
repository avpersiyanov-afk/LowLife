# -*- coding: utf-8 -*-

__title__ = u"Обновить\nэкспликацию"
__doc__ = (
    u"Пересобирает экспликации фрагментов (созданные кнопкой «Экспликация "
    u"фрагмента») по текущим помещениям и настройкам. Что обновлять — по "
    u"контексту: выделенные спецификации (на листе или в диспетчере "
    u"проекта), открытая экспликация, экспликации открытого плана или "
    u"открытого листа; иначе — все экспликации проекта (с подтверждением)."
)
__author__ = "Pipers"

import traceback

from Autodesk.Revit.DB import SubTransaction

from pyrevit import revit, forms, script

from lowlife import room_explication as rexp
from lowlife import room_explication_settings

doc = revit.doc
uidoc = revit.uidoc
TITLE = u"Обновить экспликацию"

settings = room_explication_settings.get_settings_silent()

items, scope = rexp.explications_to_update(doc, uidoc)
if not items:
    items = rexp.list_explications(doc)
    if not items:
        forms.alert(u"В проекте нет экспликаций фрагментов. Создайте их "
                    u"кнопкой «Экспликация фрагмента».", title=TITLE, exitscript=True)
    if not forms.alert(u"Обновить все экспликации фрагментов в проекте ({})?"
                       .format(len(items)), title=TITLE, yes=True, no=True):
        script.exit()
    scope = u"все в проекте"

done, lost, failed = [], [], []
with revit.Transaction(TITLE):
    for schedule, view, sources in items:
        name = rexp.element_name(schedule)
        if view is None or rexp.unsupported_reason(view):
            lost.append(name)
            continue
        # Ошибка в одной экспликации откатывает только её.
        sub = SubTransaction(doc)
        sub.Start()
        try:
            _s, count, _skipped = rexp.rebuild(doc, view, sources, settings, schedule)
            sub.Commit()
            done.append(u"{} — {} пом.".format(name, count))
        except Exception:
            sub.RollBack()
            failed.append(u"{}:\n{}".format(name, traceback.format_exc()))

lines = [u"Обновлено ({}): {}".format(scope, len(done))] + done
if lost:
    lines.append(u"\nНе обновлены — план удалён или у него выключена подрезка:")
    lines += lost
if failed:
    lines.append(u"\nОшибки:")
    lines += failed
forms.alert(u"\n".join(lines), title=TITLE)
