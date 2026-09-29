# -*- coding: utf-8 -*-

__title__ = u"Выгрузить\nсправочник"
__doc__ = u"Выгрузка справочника кабелей в .xlsx."
__author__ = "Pipers"

import re
import traceback

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from pyrevit import revit, forms, script

from lowlife.wire_catalog import catalog_to_table
from lowlife.wire_catalog_ui import choose_catalog
from lowlife.xlsx_io import write_xlsx

doc = revit.doc
TITLE = u"Выгрузка справочника кабелей"

ks = choose_catalog(doc, TITLE)
path = forms.save_file(file_ext='xlsx', default_name=re.sub(r'[\\/:*?"<>|]', u'_', ks.name))
if not path:
    script.exit()

try:
    rows, widths = catalog_to_table(ks)
    write_xlsx(path, rows, sheet_name=u"Справочник", col_widths=widths)
    forms.alert(u"Выгружено строк: {}\n\n{}".format(len(rows) - 1, path), title=TITLE)
except Exception:
    forms.alert(u"Сбой при выгрузке:\n\n{}".format(traceback.format_exc()), title=TITLE)
