# -*- coding: utf-8 -*-
__title__ = u"Линия\nв лотке"
__doc__ = u"Линия в лотке — размещение участка трассы в семействе СС_Охр."

from pyrevit import revit

from lowlife.route_lines import run_route_line_button

run_route_line_button(revit.doc, revit.uidoc, u"Линия в лотке", u"СС_Охр")


