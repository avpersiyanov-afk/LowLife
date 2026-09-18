# -*- coding: utf-8 -*-
__title__ = u"Подсветить\nбез цепи"
__author__ = "Pipers"

from pyrevit import revit, forms, EXEC_PARAMS

from lowlife.circuit_highlight import (
    highlight_elements_without_circuit, clear_highlight, install_idling_watch
)

doc = revit.doc
uidoc = revit.uidoc
view = doc.ActiveView

try:
    config_mode = bool(EXEC_PARAMS.config_mode)
except Exception:
    config_mode = False

if config_mode:
    with revit.Transaction(u"Снять подсветку без цепи"):
        count = clear_highlight(doc, view)

    forms.alert(
        u"Подсветка снята с {} элементов.".format(count) if count
        else u"На активном виде нет подсветки, поставленной этой кнопкой."
    )
else:
    with revit.Transaction(u"Подсветить элементы без цепи"):
        count = highlight_elements_without_circuit(doc, view)

    install_idling_watch(uidoc.Application)

    if count == 0:
        forms.alert(u"На активном виде все элементы с электрическими коннекторами уже входят в какую-нибудь цепь.")
    else:
        forms.alert(
            u"Подсвечено элементов без цепи: {}.\n\n"
            u"Можно сразу создавать цепи (кнопками LowLife или штатной командой Revit «Создать "
            u"электрическую цепь») — подсветка снимется сама, как только у элемента появится "
            u"цепь.".format(count)
        )
