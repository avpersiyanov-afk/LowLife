# -*- coding: utf-8 -*-
__title__ = u"Линия\nв трубе"
__doc__ = u"Линия в трубе — размещение участка трассы в семействе СС_Упр."

from pyrevit import revit

from lowlife.route_lines import run_route_line_button

run_route_line_button(revit.doc, revit.uidoc, "control", "pipe")


