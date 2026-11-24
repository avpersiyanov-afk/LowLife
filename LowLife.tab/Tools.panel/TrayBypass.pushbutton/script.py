# -*- coding: utf-8 -*-
__title__ = u"Обход\nлотка"
__doc__ = u"Строит обход лотка вокруг инженерных коммуникаций из связанных моделей."

from pyrevit import revit
from lowlife.tray_bypass import run

run(revit.doc, revit.uidoc)
