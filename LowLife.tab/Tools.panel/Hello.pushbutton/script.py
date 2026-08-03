# -*- coding: utf-8 -*-
__title__ = "Привет"
__doc__ = "Тестовая кнопка LowLife"
__author__ = "Pipers"

import inspect
from pyrevit import forms, script as pyrevit_script

forms.alert("Корпоративный инструмент кажется пока работает! 🎉",
            title="LowLifeWife")

try:
    source = inspect.getsource(forms.SelectFromList.show)
except Exception as e:
    source = "getsource failed: {}".format(e)

output = pyrevit_script.get_output()
output.print_md("### SelectFromList.show source")
output.print_code(source)
