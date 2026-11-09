# -*- coding: utf-8 -*-
__title__ = u'Фильтр осей и уровней'
__doc__ = u'Закрепляемая панель видимости осей и уровней на текущем виде. Shift+клик — маски имён.'
__persistentengine__ = True

from pyrevit import HOST_APP, EXEC_PARAMS, forms
from lowlife import datum_filter_panel
from lowlife.i18n import tr

try:
    datum_filter_panel.show(HOST_APP.uiapp, settings=EXEC_PARAMS.config_mode)
except Exception as exc:
    forms.alert(tr(u'Ошибка: {0}').format(exc))
