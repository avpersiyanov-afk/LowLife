# -*- coding: utf-8 -*-
"""Открыть или закрыть рабочие наборы загруженных связей из одного окна."""
__title__ = u'Рабочие\nнаборы связей'

from pyrevit import revit, forms, script
from lowlife import link_worksets, link_worksets_dialog
from lowlife.i18n import tr

doc = revit.doc
if doc is None or doc.IsFamilyDocument or doc.IsReadOnly or doc.IsModifiable:
    forms.alert(tr(u'Откройте проект и завершите режим редактирования.',
                   u'Open a project and finish edit mode.'), exitscript=True)
rows = link_worksets.collect_rows(doc)
if not rows:
    forms.alert(tr(u'В проекте нет загруженных связей Revit.',
                   u'The project has no loaded Revit links.'), exitscript=True)
choices = link_worksets_dialog.show(rows)
if choices is None:
    script.exit()
with forms.ProgressBar(title=tr(u'Перезагрузка связей', u'Reloading links')) as bar:
    changed, errors = link_worksets.apply(doc, choices, bar.update_progress)
message = tr(u'Перезагружено связей: {}.', u'Links reloaded: {}.').format(len(changed))
if errors:
    message += u'\n\n' + tr(u'Ошибки (успешные изменения сохранены):',
                            u'Errors (successful changes are retained):') + u'\n' + u'\n'.join(errors)
forms.alert(message, title=tr(u'Рабочие наборы связей', u'Linked worksets'))
