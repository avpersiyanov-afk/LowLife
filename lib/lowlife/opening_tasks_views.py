# -*- coding: utf-8 -*-
"""Managed local VIS control views, itemized schedules and parameter filters."""
from System.Collections.Generic import List
from Autodesk.Revit.DB import (Color, ElementId, ElementParameterFilter, FamilyInstance,
    FillPatternElement, FilteredElementCollector, LogicalAndFilter, ElementFilter,
    OverrideGraphicSettings, ParameterFilterElement, ParameterFilterRuleFactory,
    ScheduleFilter, ScheduleFilterType, StorageType, View3D, ViewFamily, ViewFamilyType, ViewSchedule)
from pyrevit import revit, forms, script
from lowlife.i18n import tr
from lowlife import opening_tasks_storage as store
from lowlife import opening_tasks_revit as api
from lowlife import opening_tasks_settings as cfg

STATUSES = [(u'Черновик',(130,130,130)),(u'Выдано',(45,165,80)),
            (u'Изменено после выдачи',(240,140,40)),(u'Отозвано',(220,55,55))]
KEYS = ['opening_status_param','opening_issue_param','opening_revision_param','opening_date_param','opening_json_param']


def unique_name(doc, base):
    from Autodesk.Revit.DB import View
    names = set(v.Name for v in FilteredElementCollector(doc).OfClass(View))
    name, i = base, 1
    while name in names:
        i += 1
        name = base + u' ({})'.format(i)
    return name


def build(doc, settings):
    drafts = [e for e in FilteredElementCollector(doc).OfClass(FamilyInstance) if api.metadata(e)]
    if not drafts:
        raise ValueError(tr(u'В модели нет боксов заданий ВИС.',u'No VIS task boxes in the model.'))
    registry = store.registry(doc)
    managed = registry.setdefault('control_views',{})
    groups = {}
    for inst in drafts:
        groups.setdefault(inst.Category.Id,[]).append(inst)
    solid = next((p.Id for p in FilteredElementCollector(doc).OfClass(FillPatternElement)
                  if p.GetFillPattern().IsSolidFill),None)
    vft = next((t for t in FilteredElementCollector(doc).OfClass(ViewFamilyType)
                if t.ViewFamily == ViewFamily.ThreeDimensional),None)
    if vft is None:
        raise ValueError(tr(u'Не найден тип 3D-вида.',u'No 3D view type.'))
    output = []
    def existing(key, cls):
        el = doc.GetElement(managed[key]) if key in managed else None
        if el is not None and not isinstance(el,cls):
            raise ValueError(tr(u'Неверный тип сохранённого объекта контроля.',u'Invalid stored control object type.'))
        return el
    def remember(key, el):
        managed[key] = el.UniqueId
        return el
    for category, instances in groups.items():
        ids = {}
        for key in KEYS:
            for inst in instances:
                param = inst.LookupParameter(settings[key])
                if param is None or param.StorageType != StorageType.String:
                    raise ValueError(tr(u'Нужен текстовый параметр экземпляра: {}',u'Text instance parameter required: {}').format(settings[key]))
                if key in ids and ids[key] != param.Id:
                    raise ValueError(tr(u'Одно имя параметра соответствует разным определениям: {}',u'Parameter name maps to different definitions: {}').format(settings[key]))
                ids[key] = param.Id
        prefix = u'LowLife | {} | {}'.format(settings['opening_project'],instances[0].Category.Name)
        root = settings['opening_project'] + '/' + str(api.boxes._id_int(category))
        # A metadata condition prevents unrelated elements with the same status from matching.
        owner_rule = ParameterFilterRuleFactory.CreateContainsRule(ids['opening_json_param'],'task_id')
        def pf(key, label, status=None, invert=False):
            rules = [ElementParameterFilter(owner_rule)]
            if status is not None:
                rule = ParameterFilterRuleFactory.CreateEqualsRule(ids['opening_status_param'],status)
                rules.append(ElementParameterFilter(rule,invert))
            rule_filter = LogicalAndFilter(List[ElementFilter](rules)) if len(rules)>1 else rules[0]
            f = existing(root+key,ParameterFilterElement)
            if f is None:
                # Filter names share a separate namespace; use a GUID suffix on first creation.
                f = remember(root+key,ParameterFilterElement.Create(doc,prefix+u' | '+label+u' | '+api.core.guid()[:8],List[ElementId]([category]),rule_filter))
            else:
                f.SetElementFilter(rule_filter)
            return f
        colors = []
        for index,(status,rgb) in enumerate(STATUSES):
            f = pf('/color/'+str(index),status,status)
            ogs = OverrideGraphicSettings().SetProjectionLineColor(Color(*rgb)).SetCutLineColor(Color(*rgb))
            if solid:
                ogs.SetSurfaceForegroundPatternId(solid).SetSurfaceForegroundPatternColor(Color(*rgb))
                ogs.SetCutForegroundPatternId(solid).SetCutForegroundPatternColor(Color(*rgb))
            colors.append((f,ogs))
        for index,status in enumerate([None]+[s for s,rgb in STATUSES]):
            key = root+'/view/'+str(index)
            view = existing(key,View3D)
            if view is None:
                view = remember(key,View3D.CreateIsometric(doc,vft.Id))
                view.Name = unique_name(doc,prefix+u' | '+(status or u'Все задания'))
            for f,ogs in colors:
                if not view.IsFilterApplied(f.Id):
                    view.AddFilter(f.Id)
                view.SetFilterOverrides(f.Id,ogs)
                view.SetFilterVisibility(f.Id,True)
            if status is not None:
                hidden = pf('/hide/'+str(index),u'Скрыть остальные: '+status,status,True)
                if not view.IsFilterApplied(hidden.Id):
                    view.AddFilter(hidden.Id)
                view.SetFilterVisibility(hidden.Id,False)
            output.append(view)
        schedule = existing(root+'/schedule',ViewSchedule)
        fresh = schedule is None
        if fresh:
            schedule = remember(root+'/schedule',ViewSchedule.CreateSchedule(doc,category))
            schedule.Name = unique_name(doc,prefix+u' | Реестр выдачи')
        definition = schedule.Definition
        schedulable = {f.ParameterId:f for f in definition.GetSchedulableFields()}
        fields = {definition.GetField(fid).ParameterId:definition.GetField(fid) for fid in definition.GetFieldOrder()}
        for key in KEYS:
            pid = ids[key]
            if pid not in schedulable:
                raise ValueError(tr(u'Параметр недоступен для спецификации: {}',u'Parameter is not schedulable: {}').format(settings[key]))
            if pid not in fields:
                fields[pid] = definition.AddField(schedulable[pid])
        for key in ('box_width_param','box_depth_param','box_height_param'):
            name = settings.get(key)
            param = (instances[0].LookupParameter(name) or instances[0].Symbol.LookupParameter(name)) if name else None
            if param and param.Id in schedulable and param.Id not in fields:
                fields[param.Id] = definition.AddField(schedulable[param.Id])
        fields[ids['opening_json_param']].IsHidden = True
        definition.IsItemized = True
        for index in reversed(range(definition.GetFilterCount())):
            definition.RemoveFilter(index)
        definition.AddFilter(ScheduleFilter(fields[ids['opening_json_param']].FieldId,ScheduleFilterType.Contains,'task_id'))
        output.append(schedule)
    store.save_registry(doc,registry)
    return output


def run(config_mode=False):
    settings_form = cfg.make('VIS')
    if config_mode:
        settings_form.get_settings_interactive()
        return
    settings = settings_form.get_settings_silent()
    settings_form.require(settings,['opening_project']+KEYS)
    try:
        with revit.Transaction(tr(u'Контроль заданий ВИС',u'VIS task control')):
            views = build(revit.doc,settings)
        out = script.get_output()
        for view in views:
            out.print_md(u'- {}: {}'.format(view.Name,out.linkify(view.Id)))
        forms.alert(tr(u'Созданы/обновлены виды и спецификации: {}. Серый — черновик, зелёный — выдано, оранжевый — изменено, красный — отозвано.',
                       u'Views/schedules created or updated: {}. Gray: draft; green: issued; orange: changed; red: withdrawn.').format(len(views)))
    except Exception as ex:
        forms.alert(tr(u'Создание контроля отменено: {}',u'Control setup rolled back: {}').format(ex))
