# -*- coding: utf-8 -*-
__title__ = "Привет"
__doc__ = "Тестовая кнопка LowLife"
__author__ = "Pipers"

import inspect
from pyrevit import forms, script as pyrevit_script

forms.alert("Корпоративный инструмент кажется пока работает! 🎉",
            title="LowLifeWife")

output = pyrevit_script.get_output()

try:
    class_source = inspect.getsource(forms.SelectFromList)
except Exception as e:
    class_source = "getsource failed: {}".format(e)

output.print_md("### SelectFromList class source")
output.print_code(class_source)
