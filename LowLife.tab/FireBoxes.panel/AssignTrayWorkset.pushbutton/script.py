# -*- coding: utf-8 -*-
__title__ = u'Назначить всем\nлоткам РН'

from pyrevit import forms, revit, script
from lowlife import cable_tray
from lowlife.i18n import tr

try:
    count = cable_tray.run_assign_all_trays_workset_button(revit.doc)
    forms.alert(tr(
        u'Готово. Рабочий набор из настроек назначен элементам: {}.',
        u'Done. The configured workset was assigned to elements: {}.'
    ).format(count))
except Exception as exc:
    script.get_logger().exception('Assigning tray workset failed')
    forms.alert(tr(
        u'Не удалось назначить рабочий набор лоткам:\n{}',
        u'Could not assign the tray workset:\n{}'
    ).format(exc))
