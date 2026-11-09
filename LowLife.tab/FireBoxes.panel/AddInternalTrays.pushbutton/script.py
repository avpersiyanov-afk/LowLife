# -*- coding: utf-8 -*-
__title__ = u'Лотки в\nкороб'
from pyrevit import revit
from lowlife.fire_boxes import run
run(revit.doc, revit.uidoc, 'add')
