# -*- coding: utf-8 -*-
__title__ = u"Боксы ВИС"
__doc__ = u"Боксы ВИС. Shift+клик — настройки."
from pyrevit import EXEC_PARAMS
from lowlife.opening_tasks_ui import run
run('VIS', bool(getattr(EXEC_PARAMS, 'config_mode', False)), 'place')
