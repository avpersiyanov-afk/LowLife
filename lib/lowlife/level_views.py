# -*- coding: utf-8 -*-
"""
Виды по уровням — тело кнопки «Виды по уровням» (Tools.panel/LevelViews).

Для каждого выбранного шаблона вида и каждого уровня модели — один план
(ViewPlan.Create) с этим шаблоном; имя — по маске (level_views_core).
Тип плана берётся по виду шаблона: шаблон плана этажа → первый тип «План
этажа», плана потолка → «План потолка», несущих конструкций → «План
несущих конструкций». Всё остальное (секущий диапазон, связи, видимость)
задаёт сам шаблон.

План с тем же именем на том же уровне не создаётся заново — ему только
назначается шаблон. Имя, занятое видом другого уровня, — ошибка в отчёте.
"""

from Autodesk.Revit.DB import (
    FilteredElementCollector, Level, View, ViewFamily, ViewFamilyType,
    ViewPlan, ViewType
)

from lowlife import family_section, geometry
from lowlife import level_views_core as core

_FAMILY_BY_VIEW_TYPE = {
    ViewType.FloorPlan: ViewFamily.FloorPlan,
    ViewType.CeilingPlan: ViewFamily.CeilingPlan,
    ViewType.EngineeringPlan: ViewFamily.StructuralPlan,
}

KIND_LABELS = {
    ViewType.FloorPlan: u"План этажа",
    ViewType.CeilingPlan: u"План потолка",
    ViewType.EngineeringPlan: u"План несущих конструкций",
}


def safe_name(el):
    return family_section.safe_name(el)


def list_plan_templates(doc):
    """Шаблоны видов для планов (этажа, потолка, несущих), по имени."""
    result = []
    for view in FilteredElementCollector(doc).OfClass(View):
        try:
            if view.IsTemplate and view.ViewType in _FAMILY_BY_VIEW_TYPE:
                result.append(view)
        except Exception:
            continue
    return sorted(result, key=lambda v: safe_name(v).lower())


def document_levels(doc):
    return sorted(FilteredElementCollector(doc).OfClass(Level),
                  key=lambda l: l.ProjectElevation)


def level_values(level, level_template):
    """Подстановки маски для уровня."""
    parsed = family_section.parse_level_name(level, level_template)
    return core.level_tokens(geometry.level_name(level),
                             level.Elevation * core.MM_IN_FOOT, parsed)


def _plan_types(doc):
    """{ViewFamily: первый по имени ViewFamilyType}."""
    found = {}
    for vft in FilteredElementCollector(doc).OfClass(ViewFamilyType):
        try:
            family = vft.ViewFamily
        except Exception:
            continue
        if family in _FAMILY_BY_VIEW_TYPE.values():
            found.setdefault(family, []).append(vft)
    return dict((f, sorted(items, key=lambda t: safe_name(t).lower())[0])
                for f, items in found.items())


class ViewResult(object):
    """Итог по одному виду: action — «создан»/«обновлён», error — причина сбоя."""

    def __init__(self, level, template, name):
        self.level = level
        self.template = template
        self.name = name
        self.view = None
        self.action = None
        self.error = None
        self.range_note = None  # секущий диапазон не выровнен — почему


def build_views(doc, levels, items, mask, level_template):
    """
    Создаёт виды (внутри транзакции). items — [(шаблон вида, значение)].
    Возвращает [ViewResult]: шаблоны по порядку, уровни снизу вверх.
    """
    plan_types = _plan_types(doc)
    existing = {}
    for v in FilteredElementCollector(doc).OfClass(ViewPlan):
        try:
            if not v.IsTemplate:
                existing[(v.ViewType, safe_name(v))] = v
        except Exception:
            continue

    taken = set()
    levels = sorted(levels, key=lambda l: l.ProjectElevation)
    values_by_level = [(l, level_values(l, level_template)) for l in levels]
    results = []
    for template, value in items:
        view_type = template.ViewType
        vft = plan_types.get(_FAMILY_BY_VIEW_TYPE.get(view_type))
        for level, values in values_by_level:
            name = core.build_view_name(mask, values, safe_name(template), value)
            result = ViewResult(level, template, name)
            results.append(result)
            try:
                _build_one(doc, level, template, vft, view_type, name, existing, taken,
                           result)
            except Exception as ex:
                result.error = u"{}".format(ex)
    return results


def _build_one(doc, level, template, vft, view_type, name, existing, taken, result):
    if not name:
        result.error = u"по маске получилось пустое имя"
        return
    if vft is None:
        result.error = u"в проекте нет типа вида «{}»".format(KIND_LABELS.get(view_type, u"?"))
        return

    key = (view_type, name)
    if key in taken:
        result.error = (u"такое имя уже получил другой вид в этом запуске — добавьте в "
                        u"маску {Группа вида и назначение} или {Шаблон}")
        return
    taken.add(key)
    view = existing.get(key)
    if view is not None:
        gen = view.GenLevel
        if gen is None or not gen.Id.Equals(level.Id):
            result.error = u"имя занято видом другого уровня ({})".format(
                geometry.level_name(gen) if gen is not None else u"?")
            return
        result.action = u"обновлён"
    else:
        view = ViewPlan.Create(doc, vft.Id, level.Id)
        try:
            view.Name = name
        except Exception as ex:
            doc.Delete(view.Id)
            result.error = u"не удалось задать имя: {}".format(ex)
            return
        existing[key] = view
        result.action = u"создан"

    result.view = view
    try:
        view.ViewTemplateId = template.Id
    except Exception as ex:
        result.error = u"вид {}, но шаблон не назначен: {}".format(result.action, ex)


def align_ranges(doc, results, level_template):
    """
    Секущий диапазон созданных/обновлённых видов — как у кнопки «Секущий
    диапазон» (view_range.align_view_range, внутри транзакции). Почему не
    выровнен — в result.range_note (планы потолков, диапазон задаёт шаблон,
    Revit не принял).
    """
    from lowlife import view_range

    for result in results:
        view = result.view
        if view is None:
            continue
        if not view_range.is_plan(view):
            result.range_note = u"план потолка — диапазон не выравнивается"
            continue
        try:
            aligned = view_range.align_view_range(doc, view, level_template)
            result.range_note = aligned.error
        except Exception as ex:
            result.range_note = u"{}".format(ex)
