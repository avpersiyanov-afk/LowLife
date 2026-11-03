# -*- coding: utf-8 -*-
"""Настроить виды нескольких связанных моделей для текущего вида."""
from pyrevit import forms, revit, script
from lowlife import link_views, link_views_dialog
from lowlife.i18n import tr

__title__ = u"Виды\nсвязей"
__doc__ = u"Выбрать виды нескольких связанных моделей для текущего вида и применить вместе."


def main():
    doc = revit.doc
    view = revit.active_view
    title = tr(u"Виды связанных моделей", u"Linked model views")
    if doc is None or view is None:
        forms.alert(tr(u"Откройте модель и вид.", u"Open a model and a view."), title=title)
        return
    try:
        problem = link_views.availability(doc, view)
        if problem:
            forms.alert(problem, title=title)
            return
        rows = link_views.collect_rows(doc, view)
        if not rows:
            forms.alert(tr(u"В модели нет связей Revit.", u"The model has no Revit links."), title=title)
            return
        choices = link_views_dialog.show(view, rows)
        if choices is None:
            return
        count = link_views.apply(doc, view, choices)
        forms.alert(tr(u"Настроено связей: {}", u"Links configured: {}").format(count), title=title)
    except Exception as ex:
        script.get_logger().exception('Linked model view settings failed')
        forms.alert(tr(u"Не удалось настроить связи. Изменения не сохранены.\n{}",
                       u"Could not configure links. Changes were not saved.\n{}").format(ex), title=title)


main()
