# -*- coding: utf-8 -*-

__title__ = u"Лотки связи\nв Эксель"
__doc__ = (
    u"Собирает кабельные лотки из связанных моделей, видимые на активном "
    u"виде, и выгружает в .xlsx: ID (в связанном файле), имя типа, модель, "
    u"отметку (середина, мм), базовый уровень, связь."
)
__author__ = "Pipers"

import os
import traceback

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from pyrevit import revit, forms, script

from lowlife.link_trays import COL_WIDTHS, build_rows, link_label, visible_links
from lowlife.xlsx_io import write_xlsx

doc = revit.doc
TITLE = u"Лотки связи в Эксель"


def pick_links(view):
    links = visible_links(doc, view)
    if not links:
        forms.alert(u"На активном виде нет видимых загруженных связей.",
                    title=TITLE, exitscript=True)
    if len(links) == 1:
        return links

    by_name = {}
    for link in links:
        by_name[u"{} [{}]".format(link_label(link), link.Id)] = link
    chosen = forms.SelectFromList.show(
        sorted(by_name.keys()),
        title=u"Из каких связей собрать лотки",
        button_name=u"Собрать",
        multiselect=True,
    )
    if not chosen:
        script.exit()
    return [by_name[n] for n in chosen]


try:
    view = doc.ActiveView
    links = pick_links(view)

    rows, counts, used_fallback = build_rows(doc, view, links)
    total = len(rows) - 1
    if total == 0:
        forms.alert(u"На активном виде нет кабельных лотков из выбранных связей.",
                    title=TITLE, exitscript=True)

    default_name = u"Лотки связи - {}".format(view.Name)
    for ch in u'\\/:*?"<>|':
        default_name = default_name.replace(ch, u"_")
    path = forms.save_file(file_ext='xlsx', default_name=default_name)
    if not path:
        script.exit()

    write_xlsx(path, rows, sheet_name=u"Лотки", col_widths=COL_WIDTHS)

    lines = u"\n".join(u"  {} — {}".format(n, c) for n, c in counts)
    note = u""
    if used_fallback:
        note = (u"\n\nВерсия Revit не умеет отбирать элементы связи по виду — "
                u"лотки отобраны по подрезке/диапазону вида (приблизительно).")
    forms.alert(
        u"Готово. Лотков: {}\n{}{}\n\n{}".format(total, lines, note, path),
        title=TITLE
    )

    try:
        os.startfile(path)
    except Exception:
        pass
except Exception:
    forms.alert(u"Сбой при выгрузке:\n\n{}".format(traceback.format_exc()),
                title=TITLE)
