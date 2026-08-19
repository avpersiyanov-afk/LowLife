# -*- coding: utf-8 -*-
__title__ = "Параметры\nСОТ"
__doc__ = (
    "Окно настроек СОТ (охранное телевидение): имена параметров "
    "(«Помещение», «Адрес устройства», «Уровень»), признак подземного "
    "этажа и таблица категорий устройств схемы — для каждой категории "
    "выбирается схемное семейство (для вставки) и реальные типы устройств "
    "модели, которые к ней относятся. Без выбора кабеля и без координат — "
    "раскладка структурной схемы полностью автоматическая."
)
__author__ = "Pipers"

import clr

clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from pyrevit import revit, forms

from lowlife.sot_settings import get_settings_interactive

doc = revit.doc

settings = get_settings_interactive(doc)

if settings is None:
    forms.alert(u"Операция отменена.", exitscript=True)

forms.alert(u"Настройки СОТ сохранены.")
