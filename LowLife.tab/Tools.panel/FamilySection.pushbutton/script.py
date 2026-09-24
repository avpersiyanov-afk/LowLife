# -*- coding: utf-8 -*-

__title__ = u"Разрез по\nсемейству"
__author__ = "Pipers"

import traceback

from pyrevit import revit, forms, EXEC_PARAMS

from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter
from Autodesk.Revit.Exceptions import OperationCanceledException

doc = revit.doc
uidoc = revit.uidoc

TITLE = u"Разрез по семейству"


class _SectionableFilter(ISelectionFilter):
    """Семейства и системные элементы (лотки, короба, трубы, стены...)."""

    def AllowElement(self, elem):
        from lowlife import family_section
        return family_section.is_sectionable(elem)

    def AllowReference(self, reference, position):
        return False


def _collect_instances():
    from lowlife import family_section

    selected = [doc.GetElement(i) for i in uidoc.Selection.GetElementIds()]
    instances = [el for el in selected if family_section.is_sectionable(el)]
    if instances:
        return instances

    try:
        refs = uidoc.Selection.PickObjects(
            ObjectType.Element, _SectionableFilter(),
            u"Выберите элементы для разреза и нажмите «Готово»"
        )
    except OperationCanceledException:
        return []
    return [doc.GetElement(r.ElementId) for r in refs]


def main():
    from lowlife import family_section, family_section_settings as fss

    try:
        config_mode = bool(EXEC_PARAMS.config_mode)
    except Exception:
        config_mode = False

    if config_mode or not fss.is_configured():
        edited = fss.get_settings_interactive(doc)
        if config_mode:
            forms.alert(
                u"Отменено, настройки не изменены." if edited is None
                else u"Настройки сохранены.", title=TITLE
            )
            return
        if edited is None:
            return

    settings = fss.get_settings_silent()

    warnings = []

    section_type = family_section.find_by_name(
        family_section.list_section_types(doc), settings[fss.TYPE_KEY])
    if section_type is None:
        if settings[fss.TYPE_KEY]:
            warnings.append(u"Типоразмер разреза «{}» не найден — взят тип по умолчанию.".format(
                settings[fss.TYPE_KEY]))
        section_type = family_section.default_section_type(doc)
    if section_type is None:
        forms.alert(u"В проекте нет ни одного типоразмера разреза.", title=TITLE, exitscript=True)

    template = None
    if settings[fss.TEMPLATE_KEY]:
        template = family_section.find_by_name(
            family_section.list_section_templates(doc), settings[fss.TEMPLATE_KEY])
        if template is None:
            warnings.append(u"Шаблон вида «{}» не найден — разрез создан без шаблона.".format(
                settings[fss.TEMPLATE_KEY]))

    instances = _collect_instances()
    if not instances:
        return

    taken_names = family_section.existing_view_names(doc)
    results = []

    with revit.Transaction(TITLE):
        for el in instances:
            results.append(family_section.create_family_section(
                doc, el, section_type, template, settings[fss.NAME_MASK_KEY],
                settings[fss.SIDE_KEY], settings[fss.FRONT_KEY], settings[fss.BACK_KEY],
                taken_names, flip=settings[fss.FLIP_KEY]
            ))

    created = [r for r in results if r.view is not None]
    failed = [r for r in results if r.view is None]

    if created and settings[fss.OPEN_VIEW_KEY]:
        try:
            uidoc.ActiveView = created[-1].view
        except Exception:
            pass

    for r in results:
        for w in r.warnings:
            warnings.append(u"Id {}: {}".format(r.element.Id.IntegerValue, w))

    if failed or warnings or len(created) > 1:
        lines = [u"Создано разрезов: {}".format(len(created))]
        lines.extend(u"  • {}".format(r.name) for r in created)
        if failed:
            lines.append(u"")
            lines.append(u"Не удалось построить:")
            lines.extend(u"  • Id {}: {}".format(r.element.Id.IntegerValue, r.error) for r in failed)
        if warnings:
            lines.append(u"")
            lines.append(u"Предупреждения:")
            lines.extend(u"  • {}".format(w) for w in warnings)
        forms.alert(u"\n".join(lines), title=TITLE)


try:
    main()
except SystemExit:
    pass
except Exception:
    forms.alert(
        u"Сбой в «{}»:\n\n{}".format(TITLE, traceback.format_exc()),
        title=TITLE
    )
