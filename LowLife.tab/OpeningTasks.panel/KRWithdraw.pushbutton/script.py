# -*- coding: utf-8 -*-
__title__ = u"Отработать отзыв"
__doc__ = u"Отработать отзыв. Shift+клик — настройки."
from pyrevit import EXEC_PARAMS
from lowlife.opening_tasks_ui import run
run('KR', bool(getattr(EXEC_PARAMS, 'config_mode', False)), 'remove')
