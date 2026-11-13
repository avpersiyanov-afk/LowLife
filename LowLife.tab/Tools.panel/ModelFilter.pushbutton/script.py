# -*- coding: utf-8 -*-
__title__ = u'Фильтр\nнаборов и связей'
__doc__ = u'Закрепляемая панель видимости рабочих наборов и связанных моделей на виде. Shift+клик — маски имён.'
__persistentengine__ = True

from pyrevit import HOST_APP, EXEC_PARAMS, forms
from lowlife import model_filter_panel
from lowlife.i18n import tr

try:
    model_filter_panel.show(HOST_APP.uiapp, settings=EXEC_PARAMS.config_mode)
except Exception as exc:
    forms.alert(tr(u'Ошибка: {0}').format(exc))
