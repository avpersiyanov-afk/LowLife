# -*- coding: utf-8 -*-
__title__ = u"Параметры\nСОТ"
__doc__ = (
    u"Окно настроек СОТ (охранное телевидение): имена параметров "
    u"(«Помещение», «Адрес устройства», «Уровень»), признак подземного "
    u"этажа и таблица категорий устройств схемы — для каждой категории "
    u"выбирается схемное семейство (для вставки) и реальные типы устройств "
    u"модели, которые к ней относятся. Без выбора кабеля и без координат — "
    u"раскладка структурной схемы полностью автоматическая."
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
