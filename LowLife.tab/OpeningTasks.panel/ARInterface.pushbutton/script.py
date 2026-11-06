# -*- coding: utf-8 -*-
__title__ = u"АР"
__doc__ = u"Независимый приём заданий ВИС в модели АР. Shift+клик — настройки."
__persistentengine__ = True
from pyrevit import EXEC_PARAMS
from lowlife.opening_tasks_window import show
show('AR', bool(getattr(EXEC_PARAMS,'config_mode',False)))
