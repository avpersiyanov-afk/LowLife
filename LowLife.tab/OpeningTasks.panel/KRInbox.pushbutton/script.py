# -*- coding: utf-8 -*-
__title__ = u"Входящие КР"
__doc__ = u"Входящие КР. Shift+клик — настройки."
from pyrevit import EXEC_PARAMS
from lowlife.opening_tasks_ui import run
run('KR', bool(getattr(EXEC_PARAMS, 'config_mode', False)), 'show')
