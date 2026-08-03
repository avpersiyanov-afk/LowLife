# -*- coding: utf-8 -*-
__title__ = "Привет"
__doc__ = "Тестовая кнопка LowLife"
__author__ = "Pipers"

import inspect
from pyrevit import forms

forms.alert("Корпоративный инструмент кажется пока работает! 🎉",
            title="LowLifeWife")

forms.alert(str(inspect.getargspec(forms.SelectFromList.show)), title="SelectFromList.show signature")
