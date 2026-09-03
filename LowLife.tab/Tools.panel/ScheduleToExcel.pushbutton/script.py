# -*- coding: utf-8 -*-

__title__ = u"Экспорт\nв Эксель"
__doc__ = u"Экспорт спецификации в .xlsx: первый столбец Revit ID, дальше параметры по столбцам"
__author__ = "Pipers"

import os
import traceback

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import ViewSchedule
from pyrevit import revit, forms, script

from lowlife.schedule_excel import list_schedules, schedule_to_rows, schedule_name
from lowlife.xlsx_io import write_xlsx

doc = revit.doc


def pick_schedule():
    av = doc.ActiveView
    if isinstance(av, ViewSchedule):
        try:
            if not av.IsTemplate and not av.Definition.IsKeySchedule:
                return av
        except Exception:
            pass

    scheds = list_schedules(doc)
    if not scheds:
        forms.alert(u"В проекте нет подходящих спецификаций.", exitscript=True)

    by_name = {}
    for v in scheds:
        by_name[schedule_name(v)] = v

    chosen = forms.SelectFromList.show(
        sorted(by_name.keys()),
        title=u"Какую спецификацию выгрузить",
        button_name=u"Выгрузить",
        multiselect=False,
    )
    if not chosen:
        script.exit()
    return by_name[chosen]


try:
    sched = pick_schedule()
    name = schedule_name(sched)

    rows, n_els, n_cols = schedule_to_rows(doc, sched)
    if n_els == 0:
        forms.alert(
            u"В спецификации «{}» нет элементов-экземпляров для выгрузки.".format(name),
            exitscript=True
        )

    path = forms.save_file(file_ext='xlsx', default_name=name)
    if not path:
        script.exit()

    write_xlsx(path, rows, sheet_name=name)

    forms.alert(
        u"Готово.\n\nСпецификация: {}\nСтрок: {}\nСтолбцов-параметров: {}\n\n{}\n\n"
        u"Правьте значения в Excel (столбец «Revit ID» не трогать) и "
        u"загружайте кнопкой «Импорт из Эксель».".format(name, n_els, n_cols, path)
    )

    try:
        os.startfile(path)
    except Exception:
        pass
except Exception:
    forms.alert(
        u"Сбой при экспорте:\n\n{}".format(traceback.format_exc()),
        title=u"Экспорт в Эксель"
    )
