# -*- coding: utf-8 -*-
__title__ = u"Виды и реестр"
__doc__ = u"Создать виды контроля, спецификацию и фильтры статусов. Shift+клик — настройки."
from pyrevit import EXEC_PARAMS
from lowlife.opening_tasks_views import run
run(bool(getattr(EXEC_PARAMS,'config_mode',False)))
