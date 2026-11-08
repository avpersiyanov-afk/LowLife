# -*- coding: utf-8 -*-
__title__ = u'Смоделировать\nкороб'
__persistentengine__ = True
from pyrevit import revit
from lowlife.fire_boxes import run
run(revit.doc, revit.uidoc, 'draw')
