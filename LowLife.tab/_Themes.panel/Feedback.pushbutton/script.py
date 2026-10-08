# -*- coding: utf-8 -*-
from pnotes import feedback

__persistentengine__ = True  # то же, что engine: persistent в bundle.yaml — для старых версий pyRevit

feedback.run(__revit__)
