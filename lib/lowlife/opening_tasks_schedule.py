# -*- coding: utf-8 -*-
"""One native itemized register of all local task boxes."""
from Autodesk.Revit.DB import (ElementId, ViewSchedule, ScheduleFieldType,
    ScheduleFilter, ScheduleFilterType, ScheduleSortGroupField, ScheduleSortOrder)
from lowlife.i18n import tr
from lowlife import opening_tasks_revit as api
from lowlife.loi_check import _schedulable_index, _first_by_bips, _add_field, _LEVEL_BIPS


def build(doc, settings, elements, registry):
    """Called in a subtransaction; one box per row, never grouped."""
    from lowlife.opening_tasks_views import unique_name
    managed=registry.setdefault('control_views',{})
    key=settings['opening_project']+'/register'
    categories=set(inst.Category.Id for inst in elements)
    category=next(iter(categories)) if len(categories)==1 else ElementId.InvalidElementId
    schedule=doc.GetElement(managed[key]) if key in managed else None
    if schedule is None and len(categories)==1:
        legacy=settings['opening_project']+'/'+str(api.boxes._id_int(category))+'/schedule'
        schedule=doc.GetElement(managed[legacy]) if legacy in managed else None
    if schedule is not None and not isinstance(schedule,ViewSchedule):
        raise ValueError(tr(u'Сохранённый реестр имеет неверный тип.',u'Stored register has an invalid type.'))
    if schedule is None or schedule.Definition.CategoryId!=category:
        schedule=ViewSchedule.CreateSchedule(doc,category)
    title=tr(u'LowLife | {} | Сводный реестр боксов',u'LowLife | {} | Consolidated box register').format(settings['opening_project'])
    if schedule.Name!=title:
        schedule.Name=unique_name(doc,title)
    definition=schedule.Definition
    by_id,_by_name=_schedulable_index(doc,definition)
    for i in reversed(range(definition.GetFilterCount())):
        definition.RemoveFilter(i)
    for i in reversed(range(definition.GetSortGroupFieldCount())):
        definition.RemoveSortGroupField(i)
    definition.ClearFields()
    fields={}
    sorting=[]
    for key_name,bips,heading in [
        ('type',('ELEM_FAMILY_AND_TYPE_PARAM','ELEM_TYPE_PARAM'),tr(u'Семейство и тип',u'Family and type')),
        ('mark',('ALL_MODEL_MARK',),tr(u'Марка',u'Mark')),
        ('level',_LEVEL_BIPS,tr(u'Уровень',u'Level'))]:
        sf=_first_by_bips(by_id,bips)
        if sf is not None:
            field=_add_field(definition,sf,heading)
            if key_name in ('type','level'):
                sorting.append(field.FieldId)
    for key_name,heading,required in [
        ('box_width_param',tr(u'Ширина',u'Width'),True),
        ('box_depth_param',tr(u'Глубина',u'Depth'),True),
        ('box_height_param',tr(u'Высота',u'Height'),True),
        ('opening_status_param',tr(u'Статус',u'Status'),True),
        ('opening_issue_param',tr(u'Выпуск',u'Issue'),False),
        ('opening_revision_param',tr(u'Ревизия',u'Revision'),False),
        ('opening_date_param',tr(u'Дата выдачи',u'Issue date'),False)]:
        name=settings.get(key_name,'')
        if not name and not required:
            continue
        parameter_ids=set()
        for inst in elements:
            param=(inst.LookupParameter(name) or inst.Symbol.LookupParameter(name)) if name else None
            if param is None:
                raise ValueError(tr(u'У одного из боксов отсутствует параметр: {}.',u'A box is missing parameter: {}.').format(name or key_name))
            parameter_ids.add(str(param.Id))
        if len(parameter_ids)!=1 or next(iter(parameter_ids)) not in by_id:
            raise ValueError(tr(u'Параметр «{}» должен иметь одно общее определение и быть доступен для спецификации всех боксов. Используйте общий параметр.',
                               u'Parameter "{}" must share one definition and be schedulable for all boxes. Use a shared parameter.').format(name))
        fields[key_name]=_add_field(definition,by_id[next(iter(parameter_ids))],heading)
    # Status is the dedicated box marker; never filter multiline JSON.
    status_field=fields['opening_status_param'].FieldId
    if not definition.CanFilterByValue(status_field):
        raise ValueError(tr(u'Для фильтра реестра нужен обычный текстовый параметр статуса.',u'The register filter requires a single-line text status parameter.'))
    definition.AddFilter(ScheduleFilter(status_field,ScheduleFilterType.NotEqual,u''))
    count=definition.AddField(ScheduleFieldType.Count)
    count.ColumnHeading=tr(u'Количество',u'Count')
    definition.IsItemized=True
    definition.ShowGrandTotal=True
    definition.ShowGrandTotalCount=True
    definition.ShowGrandTotalTitle=True
    definition.GrandTotalTitle=tr(u'Итого боксов',u'Total boxes')
    sorting.append(status_field)
    for field_id in sorting:
        definition.AddSortGroupField(ScheduleSortGroupField(field_id,ScheduleSortOrder.Ascending))
    # Older boxes may not yet have a displayed status; keep them in the register.
    for inst in elements:
        status=inst.LookupParameter(settings['opening_status_param'])
        if not (status.AsString() or '').strip():
            data=api.metadata(inst)
            record=registry['tasks'].get(data['task_id'])
            api.visible_issue(inst,{'opening_status_param':settings['opening_status_param']},record)
    managed[key]=schedule.UniqueId
    return schedule
