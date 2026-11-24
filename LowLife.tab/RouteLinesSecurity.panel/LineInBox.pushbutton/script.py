# -*- coding: utf-8 -*-
__title__ = u"Линия в коробе" 
__doc__ = u"Линия в коробе — размещение участка трассы в семействе СС_Охр."

from pyrevit import revit

from lowlife.route_lines import run_route_line_button

run_route_line_button(revit.doc, revit.uidoc, u"Линия в коробе", u"СС_Охр")


