# -*- coding: utf-8 -*-
"""
Выравнивание секущего диапазона планов — тело кнопки «Секущий диапазон»
(Tools.panel/AlignViewRange).

Диапазон задаётся так:
  - низ и глубина вида — уровень плана, смещение 0;
  - секущая плоскость — уровень плана, смещение 1200 мм;
  - верх — следующий этаж, смещение -200 мм.

Следующий этаж ищется так же, как верх подрезки у «Разреза по семейству»:
family_section.level_above по шаблону имени уровня из настроек той кнопки
(тот же корпус, другой этаж, основной уровень этажа без комментария). Если
выше уровней нет — верх «Неограниченно».

Планы потолков пропускаются (у них диапазон смотрит вверх, смысл другой);
планы, у которых диапазон задаёт шаблон вида, — тоже, с пояснением: Revit
не даст изменить диапазон такого вида.
"""

from Autodesk.Revit.DB import (
    BuiltInParameter, ElementId, PlanViewPlane, PlanViewRange, ViewPlan,
    ViewType
)

from lowlife import family_section, geometry

MM_IN_FOOT = 304.8

BOTTOM_OFFSET_MM = 0.0
CUT_OFFSET_MM = 1200.0
TOP_OFFSET_MM = -200.0

_SUPPORTED_TYPES = (ViewType.FloorPlan, ViewType.EngineeringPlan, ViewType.AreaPlan)


class RangeResult(object):
    """Итог по одному виду: error — причина пропуска (или None)."""

    def __init__(self, view):
        self.view = view
        self.top_level = None
        self.error = None
        self.note = None

    def view_name(self):
        try:
            return self.view.Name
        except Exception:
            return unicode(self.view.Id.IntegerValue)


def is_plan(view):
    """План, к которому применимо выравнивание (не шаблон, не потолок)."""
    return (isinstance(view, ViewPlan) and not view.IsTemplate
            and view.ViewType in _SUPPORTED_TYPES)


def _range_controlled_by_template(doc, view):
    """Имя шаблона вида, если он задаёт секущий диапазон, иначе None."""
    tid = view.ViewTemplateId
    if tid is None or tid == ElementId.InvalidElementId:
        return None
    template = doc.GetElement(tid)
    if template is None:
        return None
    range_id = ElementId(BuiltInParameter.PLAN_VIEW_RANGE)
    try:
        free = template.GetNonControlledTemplateParameterIds()
        if any(i == range_id for i in free):
            return None
    except Exception:
        pass
    try:
        return template.Name
    except Exception:
        return u"?"


def align_view_range(doc, view, level_template=None):
    """
    Выставляет диапазон вида (внутри транзакции). Возвращает RangeResult;
    ошибка не бросается, а пишется в result.error.
    """
    result = RangeResult(view)

    level = view.GenLevel
    if level is None:
        result.error = u"у вида нет уровня"
        return result

    template_name = _range_controlled_by_template(doc, view)
    if template_name is not None:
        result.error = u"секущий диапазон задаёт шаблон вида «{}»".format(template_name)
        return result

    above, note = family_section.level_above(doc, level, level_template)
    result.top_level = above
    result.note = note

    vr = view.GetViewRange()
    vr.SetLevelId(PlanViewPlane.BottomClipPlane, level.Id)
    vr.SetOffset(PlanViewPlane.BottomClipPlane, BOTTOM_OFFSET_MM / MM_IN_FOOT)
    vr.SetLevelId(PlanViewPlane.ViewDepthPlane, level.Id)
    vr.SetOffset(PlanViewPlane.ViewDepthPlane, BOTTOM_OFFSET_MM / MM_IN_FOOT)
    vr.SetLevelId(PlanViewPlane.CutPlane, level.Id)
    vr.SetOffset(PlanViewPlane.CutPlane, CUT_OFFSET_MM / MM_IN_FOOT)
    if above is not None:
        vr.SetLevelId(PlanViewPlane.TopClipPlane, above.Id)
        vr.SetOffset(PlanViewPlane.TopClipPlane, TOP_OFFSET_MM / MM_IN_FOOT)
    else:
        vr.SetLevelId(PlanViewPlane.TopClipPlane, PlanViewRange.Unlimited)
        vr.SetOffset(PlanViewPlane.TopClipPlane, 0.0)

    try:
        view.SetViewRange(vr)
    except Exception as ex:
        result.error = u"Revit не принял диапазон: {}".format(ex)
        if above is not None:
            height_mm = (above.ProjectElevation - level.ProjectElevation) * MM_IN_FOOT
            if height_mm + TOP_OFFSET_MM <= CUT_OFFSET_MM:
                result.error = (u"до уровня «{}» всего {:.0f} мм — секущая плоскость "
                                u"{:.0f} мм выше верха диапазона".format(
                                    geometry.level_name(above), float(height_mm),
                                    CUT_OFFSET_MM))
    return result
