# -*- coding: utf-8 -*-
"""Скрыть на текущем виде элементы связей по пользовательскому условию."""
from pyrevit import forms, script
from lowlife import link_hide
from lowlife.i18n import tr

__title__ = u"Скрыть в связи"
__doc__ = u"Выбрать связи, категории и условие, проверить совпадения и скрыть выбранные элементы на текущем виде. Shift+клик — настройки."

try:
    link_hide.run(__revit__, settings_only=bool(__shiftclick__))
except Exception as ex:
    script.get_logger().exception("Hide linked elements failed")
    forms.alert(tr(u"Не удалось передать элементы команде скрытия Revit.\n{}",
                   u"Could not submit the elements to Revit's Hide Elements command.\n{}").format(ex))
