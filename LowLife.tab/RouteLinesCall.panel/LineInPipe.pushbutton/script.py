# -*- coding: utf-8 -*-
__title__ = u"Линия в трубе" 
__doc__ = u"Линия в трубе — размещение участка трассы в семействе СС_Выз."

from pyrevit import revit

from lowlife.route_lines import run_route_line_button

run_route_line_button(revit.doc, revit.uidoc, u"Линия в трубе", u"СС_Выз")


