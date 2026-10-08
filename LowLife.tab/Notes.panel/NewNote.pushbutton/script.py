# -*- coding: utf-8 -*-
from pnotes import ui

__persistentengine__ = True  # то же, что engine: persistent в bundle.yaml — для старых версий pyRevit

ui.run_new_note(__revit__.ActiveUIDocument)
