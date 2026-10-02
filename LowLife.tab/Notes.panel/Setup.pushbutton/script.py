# -*- coding: utf-8 -*-
from pyrevit import forms
from pnotes import ui

uidoc = __revit__.ActiveUIDocument
if uidoc is None or uidoc.Document.IsFamilyDocument:
    forms.alert(u'Откройте модель проекта — настройка анализирует её «Сведения о проекте».')
else:
    ui.run_setup(uidoc.Document)
