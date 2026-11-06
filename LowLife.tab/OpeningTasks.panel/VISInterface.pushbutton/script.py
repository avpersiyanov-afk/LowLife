# -*- coding: utf-8 -*-
__title__ = u"ВИС"
__doc__ = u"Интерфейс заданий на отверстия. Shift+клик — настройки."
__persistentengine__ = True
from pyrevit import EXEC_PARAMS
from lowlife.opening_tasks_window import show
show('VIS', bool(getattr(EXEC_PARAMS,'config_mode',False)))
