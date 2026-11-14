# -*- coding: utf-8 -*-
__title__ = u'Маркировка\nзадания для АР'
__doc__ = u'Текстовые аннотации задания для АР по типам семейств на активном плане. Shift+клик — выбор типов, текст и отступы.'
__author__ = 'Pipers'

import traceback
from Autodesk.Revit.DB import ViewPlan
from pyrevit import revit, forms, EXEC_PARAMS
from lowlife import ar_task_annotations, ar_task_annotations_settings as config
from lowlife.i18n import tr

doc = revit.doc
if doc is None:
    forms.alert(tr(u'Откройте проект Revit.', u'Open a Revit project.'), exitscript=True)

if EXEC_PARAMS.config_mode:
    edited = config.edit(doc)
    forms.alert(tr(u'Настройки сохранены.') if edited is not None else tr(u'Отменено.'), exitscript=True)

view = doc.ActiveView
if not isinstance(view, ViewPlan) or view.IsTemplate:
    forms.alert(tr(u'Откройте план для маркировки задания АР.',
                   u'Open a plan to place AR task annotations.'), exitscript=True)
settings = config.load()
if 'selected_types' not in settings:
    settings = config.edit(doc)
    if settings is None:
        forms.alert(tr(u'Отменено.'), exitscript=True)

try:
    with revit.Transaction(tr(u'Маркировка задания для АР', u'AR task annotations')):
        stats = ar_task_annotations.run(doc, view, settings)
except Exception:
    forms.alert(tr(u'Маркировка задания АР отменена, изменения не сохранены:\n{}',
                   u'AR task annotation cancelled; changes were rolled back:\n{}').format(traceback.format_exc()),
                exitscript=True)

forms.alert(tr(u'Разложено аннотаций: {}. Новых: {}. Закреплённых пропущено: {}.\n'
               u'Без габарита на виде: {}. Наложений: {}, пересечений выносок: {}.',
               u'Annotations placed: {}. New: {}. Pinned skipped: {}.\n'
               u'No view bounds: {}. Overlaps: {}, leader crossings: {}.').format(
                   stats['moved'], stats['created'], stats['pinned'], stats['no_bbox'],
                   stats['overlaps'], stats['crossings']))
