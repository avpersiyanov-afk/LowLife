# -*- coding: utf-8 -*-
__title__ = u"Линия\nв трубе открыто"
__doc__ = u"Линия в трубе открыто — размещение участка трассы в семействе СС_Дан."

from pyrevit import revit

from lowlife.route_lines import run_route_line_button

run_route_line_button(revit.doc, revit.uidoc, "data", "pipe_open")


