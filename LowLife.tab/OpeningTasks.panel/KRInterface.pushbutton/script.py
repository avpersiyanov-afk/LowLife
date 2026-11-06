# -*- coding: utf-8 -*-
__title__ = u"КР"
__doc__ = u"Интерфейс заданий на отверстия. Shift+клик — настройки."
__persistentengine__ = True
from pyrevit import EXEC_PARAMS
from lowlife.opening_tasks_window import show
show('KR', bool(getattr(EXEC_PARAMS,'config_mode',False)))
