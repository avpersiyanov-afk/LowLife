# -*- coding: utf-8 -*-

__title__ = u"Загрузить\nсправочник"
__doc__ = u"Загрузка справочника кабелей из .xlsx: обновление по ключевому имени и добавление новых строк."
__author__ = "Pipers"

import traceback

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from pyrevit import revit, forms, script

from lowlife.wire_catalog import apply_entries, table_to_entries
from lowlife.wire_catalog_ui import choose_catalog, report_stats
from lowlife.xlsx_io import read_xlsx

doc = revit.doc
TITLE = u"Загрузка справочника кабелей"

ks = choose_catalog(doc, TITLE)
path = forms.pick_file(files_filter=u"Excel (*.xlsx;*.xlsm)|*.xlsx;*.xlsm|Все файлы (*.*)|*.*")
if not path:
    script.exit()

try:
    entries, unknown = table_to_entries(ks, read_xlsx(path))
except ValueError as ex:
    forms.alert(unicode(ex), title=TITLE, exitscript=True)

new_count = len([1 for el, _ in entries if el is None])
question = u"Строк в файле: {}\nИз них новых для «{}»: {}".format(len(entries), ks.name, new_count)
if unknown:
    question += u"\n\nСтолбцы, которых нет в спецификации (будут пропущены):\n{}".format(
        u", ".join(unknown))
if not forms.alert(question + u"\n\nЗагрузить?", title=TITLE, yes=True, no=True):
    script.exit()

try:
    with revit.Transaction(TITLE):
        stats = apply_entries(doc, ks, entries)
    report_stats(stats, TITLE)
except Exception:
    forms.alert(u"Сбой при загрузке:\n\n{}".format(traceback.format_exc()), title=TITLE)
