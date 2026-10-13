# -*- coding: utf-8 -*-
"""
Виды по уровням — тело кнопки «Виды по уровням» (Tools.panel/LevelViews).

Для каждого выбранного уровня и каждой выбранной группы видов (настройки
кнопки, level_views_settings) — один план:
  1. создаётся ViewPlan.Create с типом вида группы (или берётся уже
     существующий план с тем же именем на том же уровне — повторный запуск
     обновляет виды, а не плодит копии);
  2. имя — по маске группы (level_views_core.build_view_name);
  3. назначается шаблон вида группы;
  4. секущий диапазон — смещения группы (верх — от следующего этажа,
     family_section.level_above с шаблоном имени уровня из настроек);
     если диапазон задаёт шаблон вида — не трогается, с пояснением;
  5. если в группе включено — связанные модели «По связанному виду»
     (View.SetLinkOverrides, Revit 2024+): в каждой подходящей связи
     берётся план того же вида (план этажа / потолка) на уровне,
     ближайшем по отметке к уровню вида (level_views_core.pick_link_view).
     Шаблон вида не должен управлять «Связями RVT» — иначе Revit не даст
     изменить их на виде, это попадёт в отчёт.

Всё — внутри одной транзакции кнопки; ошибки одного вида не отменяют
остальные, а пишутся в ViewResult.
"""

from Autodesk.Revit.DB import (
    FilteredElementCollector, Level, PlanViewPlane,
    PlanViewRange, RevitLinkInstance, View, ViewFamily, ViewFamilyType,
    ViewPlan, ViewType
)

from lowlife import family_section, geometry, view_range
from lowlife import level_views_core as core

MM_IN_FOOT = core.MM_IN_FOOT

# Семейства видов, из которых можно делать планы по уровню.
_PLAN_FAMILIES = (
    (ViewFamily.FloorPlan, u"План этажа"),
    (ViewFamily.CeilingPlan, u"План потолка"),
    (ViewFamily.StructuralPlan, u"План несущих конструкций"),
)

_PLAN_VIEW_TYPES = (ViewType.FloorPlan, ViewType.CeilingPlan, ViewType.EngineeringPlan)


def safe_name(el):
    return family_section.safe_name(el)


# --- справочники для окна настроек -------------------------------------------

def list_plan_types(doc):
    """
    [(подпись, ViewFamilyType)] типов планов — подпись «План этажа: Имя»
    (так она и хранится в настройках группы), по порядку семейств и имени.
    """
    result = []
    vfts = list(FilteredElementCollector(doc).OfClass(ViewFamilyType))
    for family, label in _PLAN_FAMILIES:
        items = []
        for vft in vfts:
            try:
                if vft.ViewFamily == family:
                    items.append((u"{}: {}".format(label, safe_name(vft)), vft))
            except Exception:
                continue
        result.extend(sorted(items, key=lambda it: it[0].lower()))
    return result


def list_plan_templates(doc):
    """Шаблоны видов для планов (этажа, потолка, несущих), по имени."""
    result = []
    for view in FilteredElementCollector(doc).OfClass(View):
        try:
            if view.IsTemplate and view.ViewType in _PLAN_VIEW_TYPES:
                result.append(view)
        except Exception:
            continue
    return sorted(result, key=lambda v: safe_name(v).lower())


def find_plan_type(doc, label, types=None):
    """ViewFamilyType по подписи из настроек; пусто — первый «План этажа»."""
    types = types if types is not None else list_plan_types(doc)
    label = (label or u"").strip()
    if not label:
        for lbl, vft in types:
            if vft.ViewFamily == ViewFamily.FloorPlan:
                return vft
        return None
    for lbl, vft in types:
        if lbl == label:
            return vft
    # Подпись могла сохраниться без «Семейство: » — ищем по имени типа.
    for lbl, vft in types:
        if safe_name(vft) == label:
            return vft
    return None


def find_template(templates, name):
    name = (name or u"").strip()
    if not name:
        return None
    for t in templates:
        if safe_name(t) == name:
            return t
    return None


# --- связанные модели ---------------------------------------------------------

class LinkInfo(object):
    """Загруженная связь: экземпляр, документ, имя, сдвиг по Z (мм)."""

    def __init__(self, instance, link_doc, name, dz_mm):
        self.instance = instance
        self.doc = link_doc
        self.name = name
        self.dz_mm = dz_mm
        self._plans = {}

    def plans(self, view_type):
        """[(имя плана, отметка уровня в координатах основной модели мм, Id)]."""
        if view_type not in self._plans:
            items = []
            for v in FilteredElementCollector(self.doc).OfClass(ViewPlan):
                try:
                    if v.IsTemplate or v.ViewType != view_type:
                        continue
                    lvl = v.GenLevel
                    if lvl is None:
                        continue
                    z = lvl.ProjectElevation * MM_IN_FOOT + self.dz_mm
                    items.append((safe_name(v), z, v.Id))
                except Exception:
                    continue
            self._plans[view_type] = items
        return self._plans[view_type]


def list_links(doc):
    """Загруженные связи (LinkInfo), по имени."""
    result = []
    for inst in FilteredElementCollector(doc).OfClass(RevitLinkInstance):
        try:
            link_doc = inst.GetLinkDocument()
        except Exception:
            link_doc = None
        if link_doc is None:
            continue
        link_type = doc.GetElement(inst.GetTypeId())
        name = safe_name(link_type) if link_type is not None else safe_name(inst)
        try:
            dz_mm = inst.GetTotalTransform().Origin.Z * MM_IN_FOOT
        except Exception:
            dz_mm = 0.0
        result.append(LinkInfo(inst, link_doc, name, dz_mm))
    return sorted(result, key=lambda l: l.name.lower())


def link_overrides_supported():
    try:
        from Autodesk.Revit.DB import RevitLinkGraphicsSettings, LinkVisibility  # noqa: F401
    except Exception:
        return False
    return hasattr(View, "SetLinkOverrides")


def _set_link_by_linked_view(view, link, linked_view_id):
    from Autodesk.Revit.DB import RevitLinkGraphicsSettings, LinkVisibility

    settings = RevitLinkGraphicsSettings()
    settings.LinkVisibilityType = LinkVisibility.ByLinkView
    settings.LinkedViewId = linked_view_id
    try:
        view.SetLinkOverrides(link.instance.Id, settings)
    except Exception:
        # Если экземпляр не принимается — настройка на тип связи.
        view.SetLinkOverrides(link.instance.GetTypeId(), settings)


# --- построение ---------------------------------------------------------------

class ViewResult(object):
    """Итог по одному виду: action — «создан»/«обновлён», error — причина сбоя."""

    def __init__(self, level, group, name):
        self.level = level
        self.group = group
        self.name = name
        self.view = None
        self.action = None
        self.error = None
        self.notes = []
        self.links = []  # [(имя связи, имя вида связи)]


class Context(object):
    """Всё, что общее для прогона: справочники, занятые имена, связи."""

    def __init__(self, doc, level_template):
        self.doc = doc
        self.level_template = level_template
        self.types = list_plan_types(doc)
        self.templates = list_plan_templates(doc)
        self._links = None
        self.links_supported = link_overrides_supported()
        self.existing = {}
        for v in FilteredElementCollector(doc).OfClass(ViewPlan):
            try:
                if not v.IsTemplate:
                    self.existing[(v.ViewType, safe_name(v))] = v
            except Exception:
                continue

    def links(self):
        if self._links is None:
            self._links = list_links(self.doc)
        return self._links


def level_values(level, level_template):
    """Подстановки маски для уровня."""
    name = geometry.level_name(level)
    parsed = family_section.parse_level_name(level, level_template)
    return core.level_tokens(name, level.Elevation * MM_IN_FOOT, parsed)


def _same_id(a, b):
    try:
        return a.Equals(b)
    except Exception:
        return a == b


def _apply_template(ctx, view, group, result):
    name = group[core.G_TEMPLATE]
    if not name:
        return
    template = find_template(ctx.templates, name)
    if template is None:
        result.notes.append(u"шаблон «{}» не найден в проекте — не назначен".format(name))
        return
    try:
        view.ViewTemplateId = template.Id
    except Exception as ex:
        result.notes.append(u"шаблон «{}» не назначен: {}".format(name, ex))


def _apply_range(ctx, view, level, group, result):
    plan = core.range_plan(group)
    if not plan:
        return
    template_name = view_range.range_controlled_by_template(ctx.doc, view)
    if template_name is not None:
        result.notes.append(u"секущий диапазон задаёт шаблон «{}» — не менялся".format(
            template_name))
        return

    above = None
    height_mm = None
    if "top" in plan:
        above, note = family_section.level_above(ctx.doc, level, ctx.level_template)
        if note:
            result.notes.append(note)
        if above is not None:
            height_mm = (above.ProjectElevation - level.ProjectElevation) * MM_IN_FOOT

    problem = core.range_problem(plan, height_mm)
    if problem:
        result.notes.append(u"секущий диапазон не задан: " + problem)
        return

    vr = view.GetViewRange()
    for key, plane in (("cut", PlanViewPlane.CutPlane),
                       ("bottom", PlanViewPlane.BottomClipPlane),
                       ("depth", PlanViewPlane.ViewDepthPlane)):
        if key in plan:
            vr.SetLevelId(plane, level.Id)
            vr.SetOffset(plane, plan[key] / MM_IN_FOOT)
    if "top" in plan:
        if above is not None:
            vr.SetLevelId(PlanViewPlane.TopClipPlane, above.Id)
            vr.SetOffset(PlanViewPlane.TopClipPlane, plan["top"] / MM_IN_FOOT)
        else:
            vr.SetLevelId(PlanViewPlane.TopClipPlane, PlanViewRange.Unlimited)
            vr.SetOffset(PlanViewPlane.TopClipPlane, 0.0)
    try:
        view.SetViewRange(vr)
    except Exception as ex:
        result.notes.append(u"Revit не принял секущий диапазон: {}".format(ex))


def _apply_links(ctx, view, level, group, values, result):
    if not group[core.G_LINKS]:
        return
    if not ctx.links_supported:
        result.notes.append(u"связи «По связанному виду» задаются из скрипта только "
                            u"в Revit 2024 и новее — пропущено")
        return
    filters = core.split_filters(group[core.G_LINK_FILTER])
    links = [l for l in ctx.links() if core.name_matches_any(l.name, filters)]
    if not links:
        result.notes.append(u"нет загруженных связей{}".format(
            u" с «{}» в имени".format(group[core.G_LINK_FILTER]) if filters else u""))
        return

    view_filter = core.link_view_filter_text(group, values)
    level_z = level.ProjectElevation * MM_IN_FOOT
    for link in links:
        picked, note = core.pick_link_view(link.plans(view.ViewType), level_z, view_filter)
        if picked is None:
            result.notes.append(u"связь «{}»: {}".format(link.name, note))
            continue
        try:
            _set_link_by_linked_view(view, link, picked[2])
        except Exception as ex:
            result.notes.append(
                u"связь «{}»: не удалось задать «По связанному виду» ({}) — "
                u"возможно, шаблон вида управляет связями RVT".format(link.name, ex))
            continue
        result.links.append((link.name, picked[0]))
        if note:
            result.notes.append(u"связь «{}»: {}".format(link.name, note))


def build_view(ctx, level, group, taken):
    """
    Создаёт/обновляет вид группы на уровне (внутри транзакции). taken —
    множество (ViewType, имя) видов, уже созданных этим прогоном: второй
    вид с тем же именем — ошибка (маска без {Уровень}/{Группа}).
    """
    values = level_values(level, ctx.level_template)
    name = core.build_view_name(group, values)
    result = ViewResult(level, group, name)
    try:
        if not name:
            result.error = u"по маске «{}» получилось пустое имя".format(group[core.G_NAME_MASK])
            return result

        vft = find_plan_type(ctx.doc, group[core.G_VIEW_TYPE], ctx.types)
        if vft is None:
            result.error = u"тип вида «{}» не найден в проекте".format(
                group[core.G_VIEW_TYPE] or u"План этажа")
            return result
        view_type = {
            ViewFamily.FloorPlan: ViewType.FloorPlan,
            ViewFamily.CeilingPlan: ViewType.CeilingPlan,
            ViewFamily.StructuralPlan: ViewType.EngineeringPlan,
        }.get(vft.ViewFamily, ViewType.FloorPlan)

        key = (view_type, name)
        if key in taken:
            result.error = (u"имя «{}» уже получил другой вид в этом запуске — "
                            u"добавьте в маску {{Уровень}} или {{Группа}}".format(name))
            return result

        view = ctx.existing.get(key)
        if view is not None:
            if view.GenLevel is None or not _same_id(view.GenLevel.Id, level.Id):
                result.error = u"имя «{}» уже занято видом другого уровня ({})".format(
                    name, geometry.level_name(view.GenLevel) if view.GenLevel else u"?")
                return result
            result.action = u"обновлён"
        else:
            view = ViewPlan.Create(ctx.doc, vft.Id, level.Id)
            try:
                view.Name = name
            except Exception as ex:
                ctx.doc.Delete(view.Id)
                result.error = u"не удалось задать имя «{}»: {}".format(name, ex)
                return result
            ctx.existing[key] = view
            result.action = u"создан"
        taken.add(key)
        result.view = view

        _apply_template(ctx, view, group, result)
        _apply_range(ctx, view, level, group, result)
        _apply_links(ctx, view, level, group, values, result)
    except Exception as ex:
        result.error = u"{}".format(ex)
    return result


def build_views(doc, levels, groups, level_template):
    """Все виды: уровни снизу вверх, внутри уровня — группы по порядку."""
    ctx = Context(doc, level_template)
    taken = set()
    results = []
    for level in sorted(levels, key=lambda l: l.ProjectElevation):
        for group in groups:
            results.append(build_view(ctx, level, group, taken))
    return results


def document_levels(doc):
    return sorted(FilteredElementCollector(doc).OfClass(Level),
                  key=lambda l: l.ProjectElevation)
