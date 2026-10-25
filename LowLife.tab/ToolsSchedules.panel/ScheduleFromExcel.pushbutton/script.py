# -*- coding: utf-8 -*-

__title__ = u"Импорт\nиз Эксель"
__doc__ = u"Импорт правок из .xlsx обратно в модель: по столбцу Revit ID находит элементы и пишет параметры"
__author__ = "Pipers"

import traceback
from lowlife.i18n import tr

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from pyrevit import revit, forms, script

from lowlife.schedule_excel import rows_to_model
from lowlife.xlsx_io import read_xlsx

doc = revit.doc


try:
    path = forms.pick_file(file_ext='xlsx')
    if not path:
        script.exit()

    rows = read_xlsx(path)
    if not rows:
        forms.alert(tr(u"Файл пустой или не прочитался."), exitscript=True)

    with revit.Transaction(tr(u"Импорт спецификации из Excel")):
        res = rows_to_model(doc, rows)

    parts = [
        tr(u"Готово."),
        u"",
        tr(u"Изменено значений: {}").format(res["changed"]),
    ]
    if res["unchanged"]:
        parts.append(tr(u"Без изменений: {}").format(res["unchanged"]))
    if res["read_only"]:
        parts.append(tr(u"Пропущено (только чтение / ссылка): {}").format(res["read_only"]))
    if res.get("skipped_cols"):
        parts.append(tr(u"Столбцы не из модели (пропущены целиком): {}").format(
            u", ".join(res["skipped_cols"])))
    if res["no_param"]:
        parts.append(tr(u"Параметр не найден у отдельных элементов: {}").format(res["no_param"]))
    if res["no_element"]:
        parts.append(tr(u"Элемент не найден по ID: {}").format(res["no_element"]))
    if res["errors"]:
        parts.append(u"")
        parts.append(tr(u"Ошибки записи ({}):").format(len(res["errors"])))
        parts.extend(res["errors"][:20])
        if len(res["errors"]) > 20:
            parts.append(tr(u"… и ещё {}").format(len(res["errors"]) - 20))

    forms.alert(u"\n".join(parts))
except Exception:
    forms.alert(
        tr(u"Сбой при импорте:\n\n{}").format(traceback.format_exc()),
        title=tr(u"Импорт из Эксель")
    )
