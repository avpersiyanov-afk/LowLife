# -*- coding: utf-8 -*-
"""Лёгкая замена Autodesk.Revit.DB.XYZ для тестов вне Revit.

scs_circuits.py и fire_alarm_loops.py читают у "точек" атрибуты .X/.Y/.Z и
(в паре мест) вызывают .DistanceTo(other) — этого достаточно, чтобы
подменить реальный Revit XYZ на этот класс в тестах.
"""

import math


class FakeXYZ(object):
    def __init__(self, x, y, z=0.0):
        self.X = x
        self.Y = y
        self.Z = z

    def DistanceTo(self, other):
        return math.sqrt(
            (self.X - other.X) ** 2 +
            (self.Y - other.Y) ** 2 +
            (self.Z - other.Z) ** 2
        )
