# -*- coding: utf-8 -*-

__title__ = u"Правка\nсправочника"
__doc__ = u"Правка справочника кабелей и добавление новых кабелей в окне-таблице."
__author__ = "Pipers"

import traceback

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from pyrevit import revit, forms, script

from lowlife.wire_catalog import apply_entries
from lowlife.wire_catalog_ui import choose_catalog, report_stats, show_edit_window

doc = revit.doc
TITLE = u"Правка справочника кабелей"

ks = choose_catalog(doc, TITLE)
entries = show_edit_window(doc, ks)
if not entries:
    script.exit()

try:
    with revit.Transaction(TITLE):
        stats = apply_entries(doc, ks, entries)
    report_stats(stats, TITLE)
except Exception:
    forms.alert(u"Сбой при записи:\n\n{}".format(traceback.format_exc()), title=TITLE)
