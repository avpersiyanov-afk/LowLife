# -*- coding: utf-8 -*-
__title__ = u"Отозвать задания"
__doc__ = u"Отозвать задания. Shift+клик — настройки."
from pyrevit import EXEC_PARAMS
from lowlife.opening_tasks_ui import run
run('VIS', bool(getattr(EXEC_PARAMS, 'config_mode', False)), 'withdraw')
