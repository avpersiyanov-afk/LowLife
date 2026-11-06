# -*- coding: utf-8 -*-
__title__ = u'Настройки короба'
from pyrevit import revit
from lowlife.fire_boxes import run
run(revit.doc, revit.uidoc, 'settings')
