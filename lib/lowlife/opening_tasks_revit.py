# -*- coding: utf-8 -*-
"""VIS drafts, immutable model releases and KR native openings. Transactions belong to UI."""
try:
    unicode
except NameError:
    unicode = str

import copy
from lowlife.i18n import tr
import math
from datetime import datetime
from Autodesk.Revit.DB import (BuiltInCategory, CurveArray, ElementTransformUtils, FamilyInstance, CategoryType, IndependentTag, Dimension, FilteredElementCollector,
                               Floor, RoofBase, Line, LocationPoint, Opening, Options, RevitLinkInstance, StorageType,
                               SubTransaction, TransactionStatus, ViewDetailLevel, Wall, XYZ, Outline)
from lowlife.opening_tasks_journal import windows_user
from lowlife import opening_tasks_core as core
from lowlife import opening_tasks_storage as store
from lowlife import tray_boxes as boxes
from lowlife import tray_boxes_core as geometry
from lowlife import tray_boxes_settings as tray_cfg


def now():
    return datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')


def metadata(element):
    data = store.read(element)
    return data if data and data.get('role') == 'draft' else None


def read_size(inst, name):
    p = inst.LookupParameter(name) or inst.Symbol.LookupParameter(name)
    if p is None or p.StorageType != StorageType.Double:
        raise ValueError(tr(u'Нет параметра длины: ',u'Missing length parameter: ') + name)
    return p.AsDouble()


def host_geometry(inst, data, source):
    """Read actual box, including user edits; convert to ORIGINAL target model frame."""
    width, depth, height = [read_size(inst, name) for name in data['size_params']]
    center = inst.Location.Point
    if data['origin_bottom']:
        center = center.Add(XYZ(0, 0, height/2.0))
    direction = XYZ(math.cos(inst.Location.Rotation), math.sin(inst.Location.Rotation), 0)
    inverse = source.GetTotalTransform().Inverse
    local = inverse.OfPoint(center)
    xaxis = inverse.OfVector(direction)
    up = inverse.OfVector(XYZ.BasisZ)
    if abs(up.Z - 1.0) > 1e-6 or abs(xaxis.Z) > 1e-6:
        raise ValueError(tr(u'Наклонённая или перевёрнутая связь не поддерживается',u'Tilted or inverted link is unsupported'))
    result = dict(kind=data['kind'], center_mm=[boxes.mm(v) for v in boxes._t(local)],
                  x_dir=list(boxes._t(xaxis)), size_mm=[boxes.mm(v) for v in (width, depth, height)],
                  host_uid=data['host_uid'], host_model=data['host_model'])
    if data.get('host_category')=='roof':result['host_category']='roof'
    core.validate_geometry(result)
    return result


def coalesce_crossings(route, crossings):
    # Layers or voids may split one host into several solid-axis spans.
    # One source/host identity must produce one envelope, not overwrite its own draft.
    groups = {}
    start = route.Location.Curve.GetEndPoint(0)
    direction = route.Location.Curve.Direction
    for crossing in crossings:
        groups.setdefault(crossing.host.UniqueId,[]).append(crossing)
    result = []
    for parts in groups.values():
        distances = [boxes._xyz(p).Subtract(start).DotProduct(direction)
                     for part in parts for p in (part.start,part.end)]
        first = parts[0]
        result.append(boxes.Crossing(first.kind,
            boxes._t(start.Add(direction.Multiply(min(distances)))),
            boxes._t(start.Add(direction.Multiply(max(distances)))),
            first.host,first.link,first.wall_dir))
    return result


def place(doc, routes, source, symbol, settings, workset, progress=None):
    """Updates own drafts by source/host identity, never touches issued snapshots."""
    recipient = settings.get('opening_recipient','KR')
    core.validate_recipient(recipient)
    placer = boxes.BoxPlacer(doc, symbol, settings, workset)
    # Different recipients may need independent boxes at the same position.
    placer.existing = [inst for inst in placer.existing
                       if not metadata(inst) or metadata(inst).get('recipient','KR') == recipient]
    managed = {}
    for inst in FilteredElementCollector(doc).OfClass(FamilyInstance):
        data = metadata(inst)
        if data and data.get('owner_uid') == inst.UniqueId:
            key = (data['source_uid'], data['host_uid'], data['host_link_uid'],data.get('recipient','KR'))
            if key in managed:
                raise ValueError(tr(u'Найдены дубли идентификатора чернового задания',u'Duplicate managed draft identity'))
            managed[key] = (inst, data)
    options = Options()
    options.DetailLevel = ViewDetailLevel.Fine
    categories = boxes._host_categories(settings,include_roofs=True)
    src = boxes._Source(source.GetLinkDocument(), source)
    entries, errors = [], []
    issued_tasks=store.registry(doc)['tasks']
    issued_ids = set(issued_tasks)
    for index, route in enumerate(routes):
        if progress:
            progress(index+1, len(routes))
        try:
            crossings = coalesce_crossings(route,boxes.tray_crossings(route, [src], categories, options))
        except Exception as ex:
            errors.append((route.Id, unicode(ex)))
            continue
        for crossing in crossings:
            sub = SubTransaction(doc)
            count = len(placer.existing)
            filter_error_count = len(placer.result.filter_errors)
            try:
                box, reason = boxes.box_for(route, crossing, settings)
                if box is None:
                    raise ValueError(reason)
                if settings['opening_increase'] != 'none':
                    amount = (geometry.recommended_increase_mm(boxes.mm(max(geometry.opening_sides(box))))
                              if settings['opening_increase'] == 'auto' else float(settings['opening_increase']))
                    box = geometry.enlarge_opening(box, boxes.ft(amount))
                box=boxes.fit_vertical_host(box,crossing,src,options,boxes._t(route.Location.Curve.Direction),
                                            boxes.ft(settings.get('depth_extra_mm') or 0))
                scope_bounds=settings.get('_opening_scope_bounds')
                if scope_bounds and not any(Outline(bound.Min,bound.Max).Contains(
                        bound.Transform.Inverse.OfPoint(boxes._xyz(box.center)),1e-9) for bound in scope_bounds):
                    continue
                key = (route.UniqueId, crossing.host.UniqueId, source.UniqueId,settings.get('opening_recipient','KR'))
                previous = managed.get(key)
                level,level_info=placer.level_resolver.resolve(crossing)
                sub.Start()
                if previous:
                    inst, data = previous
                    if data.get('object_part') and data['object_part']!=settings.get('opening_object_part',''):
                        raise ValueError(tr(u'Бокс относится к другому корпусу',u'Draft belongs to another building number'))
                    if not isinstance(inst.Location, LocationPoint):
                        raise ValueError(tr(u'У бокса нет точки вставки',u'Draft has no point location'))
                    from lowlife.opening_levels import assign_level
                    assign_level(doc,inst,level)
                    target = boxes._xyz(box.origin(placer.at_bottom))
                    angle = box.angle() - inst.Location.Rotation
                    ElementTransformUtils.RotateElement(doc, inst.Id,
                        Line.CreateBound(inst.Location.Point, inst.Location.Point.Add(XYZ.BasisZ)), angle)
                    ElementTransformUtils.MoveElement(doc, inst.Id, target.Subtract(inst.Location.Point))
                else:
                    if placer._existing_at(boxes._xyz(box.origin(placer.at_bottom)), boxes._xyz(box.center)):
                        raise ValueError(tr(u'На пересечении уже есть бокс, не связанный с заданием',u'An unmanaged box already exists at this crossing'))
                    inst = placer._create(boxes._xyz(box.origin(placer.at_bottom)), box,level)
                    data = dict(schema=1, role='draft', task_id=core.guid(), owner_uid=inst.UniqueId)
                placer.result.missing_params.clear()
                placer._apply_sizes(inst, box)
                from lowlife.opening_levels import assign_level
                assign_level(doc,inst,level)
                if placer.result.missing_params:
                    raise ValueError(tr(u'Нет параметров размеров бокса',u'Missing box size parameters'))
                placer._set_host_filter(inst, crossing.kind,required=False)
                data = dict(data, level=level_info, object_part=settings.get('opening_object_part',''), recipient=settings.get('opening_recipient','KR'), source_model=store.model_id(doc), source_uid=route.UniqueId,
                            host_uid=crossing.host.UniqueId, host_model=store.model_id(source.GetLinkDocument()),
                            host_link_uid=source.UniqueId, kind=crossing.kind,
                            origin_bottom=placer.at_bottom,
                            size_params=[settings[k] for k in ('box_width_param','box_depth_param','box_height_param')])
                doc.Regenerate()
                actual = [read_size(inst,name) for name in data['size_params']]
                if any(abs(a-b)>1e-6 for a,b in zip(actual,(box.width,box.depth,box.height))):
                    raise ValueError(tr(u'Семейство не применило запрошенные размеры',u'Family did not apply the requested dimensions'))
                if boxes._id_int(crossing.host.Category.Id)==int(BuiltInCategory.OST_Roofs):
                    data['host_category']='roof'
                # Working updates never overwrite a released snapshot in the parameter.
                if data['task_id'] not in issued_ids:
                    store.set_parameter(inst, settings['opening_json_param'],
                        dict(data, status='draft', geometry=host_geometry(inst,data,source)))
                issued = issued_tasks.get(data['task_id'])
                visible_issue(inst,settings,issued, bool(issued and issued['status']=='issued' and
                    (not core.geometry_equal(issued['geometry'],host_geometry(inst,data,source)) or
                     issued.get('level')!=data.get('level') or issued.get('object_part','')!=data.get('object_part',''))))
                store.write(inst, data)
                if sub.Commit() != TransactionStatus.Committed:
                    raise ValueError(tr(u'Транзакция бокса не зафиксирована',u'Draft transaction was not committed'))
                managed[key] = (inst, data)
                entries.append((route.element, crossing, inst, box))
            except Exception as ex:
                if sub.GetStatus() == TransactionStatus.Started:
                    sub.RollBack()
                del placer.existing[count:]
                # Warnings from this attempt may reference instances destroyed
                # by rollback; keep only warnings for committed boxes.
                del placer.result.filter_errors[filter_error_count:]
                errors.append((route.Id, unicode(ex)))
    errors += [(inst.Id, err) for inst, err in placer.result.filter_errors]
    from lowlife.opening_tasks_views import sync_selection_filters
    sync_selection_filters(doc,settings)
    return entries, errors


def prepare_drafts(doc, elements, settings):
    drafts = []
    for inst in elements:
        data = metadata(inst)
        if not data:
            raise ValueError(tr(u'Выберите только боксы заданий ВИС',u'Select only VIS opening drafts'))
        if data.get('recipient','KR') != settings.get('opening_recipient','KR'):
            raise ValueError(tr(u'Получатель бокса не совпадает с командой выдачи',u'Draft recipient does not match the issue command'))
        if data['owner_uid'] != inst.UniqueId or data['source_model'] != store.model_id(doc):
            raise ValueError(tr(u'Задание скопировано: создайте новый бокс командой расстановки',u'Copied task: create a new draft with the placement command'))
        if doc.GetElement(data['source_uid']) is None:
            raise ValueError(tr(u'Исходный элемент ВИС удалён: отзовите или пересоздайте задание',u'Source MEP element is missing; withdraw or regenerate the draft'))
        link = doc.GetElement(data['host_link_uid'])
        if link is None or link.GetLinkDocument() is None:
            raise ValueError(tr(u'Связь с конструкциями не загружена',u'Target structure link is not loaded'))
        if link.GetLinkDocument().GetElement(data['host_uid']) is None:
            raise ValueError(tr(u'Конструкция удалена: пересоздайте задание',u'Target host was deleted; regenerate the draft'))
        if data['host_model'] != store.model_id(link.GetLinkDocument()):
            raise ValueError(tr(u'Связь заменена: пересоздайте задание',u'Target link was replaced; regenerate the draft'))
        if data.get('object_part') and data['object_part']!=settings.get('opening_object_part',''):
            raise ValueError(tr(u'Бокс относится к другому корпусу',u'Draft belongs to another building number'))
        drafts.append(dict(level=data.get('level'), object_part=settings.get('opening_object_part',''), task_id=data['task_id'], source_model=data['source_model'], source_uid=data['source_uid'],
                           owner_uid=inst.UniqueId, recipient=data.get('recipient','KR'), geometry=host_geometry(inst,data,link)))
    return drafts


def publish(doc, elements, settings):
    drafts = prepare_drafts(doc,elements,settings)
    registry, changes = core.issue(store.registry(doc), drafts, settings['opening_project'],
                                   settings['opening_discipline'],doc.Application.Username,now(),settings.get('opening_recipient','KR'),windows_user=windows_user())
    by_id = {d['task_id']: e for d,e in zip(drafts,elements)}
    for record in changes:
        inst=by_id[record['task_id']]
        data=metadata(inst)
        data['object_part']=record.get('object_part','')
        store.write(inst,data)
        store.set_parameter(by_id[record['task_id']],settings['opening_json_param'],record)
        visible_issue(by_id[record['task_id']],settings,record)
    if changes:
        store.save_registry(doc,registry)
    from lowlife.opening_tasks_views import sync_selection_filters
    sync_selection_filters(doc,settings,registry)
    return changes


def retract(doc, task_ids, settings):
    registry, changes = core.withdraw(store.registry(doc),task_ids,doc.Application.Username,now(),windows_user=windows_user())
    for record in changes:
        inst = doc.GetElement(record['owner_uid'])
        if inst:
            store.set_parameter(inst,settings['opening_json_param'],record)
            visible_issue(inst,settings,record)
    if changes:
        store.save_registry(doc,registry)
    from lowlife.opening_tasks_views import sync_selection_filters
    sync_selection_filters(doc,settings,registry)
    return changes


def incoming(doc, project, recipient='KR'):
    """Only issued registry snapshots; NEVER the live linked box geometry."""
    core.validate_recipient(recipient)
    records = {}
    for link in FilteredElementCollector(doc).OfClass(RevitLinkInstance):
        linked = link.GetLinkDocument()
        if linked is None:
            continue
        for record in store.registry(linked)['tasks'].values():
            if (record['project'] != project or record.get('recipient','KR') != recipient or
                    record['geometry']['host_model'] != store.model_id(doc)):
                continue
            key = core.task_key(record)
            if key in records and records[key][0] != record:
                raise ValueError(tr(u'В связях найдены конфликтующие выпуски одной модели ВИС',u'Conflicting releases of a linked source model'))
            records[key] = (record, link)
    return list(records.values())


def create_native_opening(doc, g):
    """Rectangular native wall/floor opening. Host identity is from the issued snapshot."""
    core.validate_geometry(g)
    if g['host_model'] != store.model_id(doc):
        raise ValueError(tr(u'Отверстие адресовано другой модели-получателю',u'Opening belongs to another recipient model'))
    host = doc.GetElement(g['host_uid'])
    center = boxes._xyz([boxes.ft(v) for v in g['center_mm']])
    x = boxes._xyz(g['x_dir'])
    w,d,h = [boxes.ft(v) for v in g['size_mm']]
    if g['kind'] == 'wall':
        if not isinstance(host,Wall) or not isinstance(host.Location.Curve,Line):
            raise ValueError(tr(u'Нужна прямая стена',u'A straight wall is required'))
        if hasattr(host,'CrossSection') and unicode(host.CrossSection) != 'Vertical':
            raise ValueError(tr(u'Наклонные стены требуют ручной проверки',u'Slanted/tapered walls require manual review'))
        normal = host.Orientation
        if abs(normal.DotProduct(x)) > 1e-5 or abs(normal.Z) > 1e-5:
            raise ValueError(tr(u'Ориентация стены изменилась: перевыдайте задание',u'Wall orientation changed; reissue the task'))
        bb = host.get_BoundingBox(None)
        loc = host.Location.Curve.Project(center)
        if loc is not None and not host.Location.Curve.GetEndParameter(0) <= loc.Parameter <= host.Location.Curve.GetEndParameter(1):
            raise ValueError(tr(u'Отверстие находится за пределами стены',u'Opening lies beyond the wall ends'))
        if loc is None or loc.XYZPoint.DistanceTo(XYZ(center.X,center.Y,loc.XYZPoint.Z)) > host.Width/2.0 + d/2.0:
            raise ValueError(tr(u'Стена переместилась относительно выданного отверстия',u'Wall moved away from issued opening'))
        if bb is None or center.Z+h/2 < bb.Min.Z or center.Z-h/2 > bb.Max.Z:
            raise ValueError(tr(u'Отверстие не пересекает стену по высоте',u'Opening does not overlap the wall vertically'))
        return doc.Create.NewOpening(host,center.Subtract(x.Multiply(w/2)).Subtract(XYZ(0,0,h/2)),
                                     center.Add(x.Multiply(w/2)).Add(XYZ(0,0,h/2)))
    if not isinstance(host,(Floor,RoofBase)):
        raise ValueError(tr(u'Нужно перекрытие или кровля',u'A floor or roof is required'))
    bb = host.get_BoundingBox(None)
    if bb is None or center.Z+h/2 < bb.Min.Z or center.Z-h/2 > bb.Max.Z:
        raise ValueError(tr(u'Перекрытие переместилось относительно выданного отверстия',u'Floor moved away from issued opening'))
    y = XYZ(-x.Y,x.X,0)
    points = [center.Add(x.Multiply(a*w/2)).Add(y.Multiply(b*d/2))
              for a,b in ((-1,-1),(1,-1),(1,1),(-1,1))]
    profile = CurveArray()
    for i in range(4):
        profile.Append(Line.CreateBound(points[i],points[(i+1)%4]))
    # False means vertical, True means perpendicular to the host face.
    return doc.Create.NewOpening(host,profile,False)


def protected_annotations(doc, opening):
    """Find explicit annotations that cannot safely survive delete/recreate."""
    result=set()
    for eid in opening.GetDependentElements(None):
        el=doc.GetElement(eid)
        if el is not None and el.Category is not None and el.Category.CategoryType==CategoryType.Annotation:
            result.add(eid)
    for tag in FilteredElementCollector(doc).OfClass(IndependentTag):
        if opening.Id in list(tag.GetTaggedLocalElementIds()):
            result.add(tag.Id)
    for dimension in FilteredElementCollector(doc).OfClass(Dimension):
        try:
            if any(ref.ElementId==opening.Id for ref in dimension.References):
                result.add(dimension.Id)
        except Exception:
            # Dependency enumeration above still protects owned dimensions.
            pass
    return result


def annotation_states(doc):
    result={}
    for cls in (Dimension,IndependentTag):
        for el in FilteredElementCollector(doc).OfClass(cls):
            values=[]
            for name in ('IsOrphaned','AreReferencesAvailable','NumberOfSegments','ValueString'):
                try:
                    values.append(getattr(el,name,None))
                except Exception:
                    values.append(None)
            result[el.Id]=tuple(values)
    return result


def assert_safe_replacement(doc, opening):
    opening_eid=opening.Id
    protected=protected_annotations(doc,opening)
    before=annotation_states(doc)
    probe=SubTransaction(doc)
    probe.Start()
    try:
        deleted=list(doc.Delete(opening_eid))
        doc.Regenerate()
        after=annotation_states(doc)
        protected.update(eid for eid,state in before.items() if after.get(eid)!=state)
    finally:
        probe.RollBack()
    for eid in deleted:
        el=doc.GetElement(eid)
        if eid!=opening_eid and el is not None and el.Category is not None and el.Category.CategoryType==CategoryType.Annotation:
            protected.add(eid)
    if protected:
        raise ValueError(tr(u'Замена/удаление отверстия Id {} остановлены: связанные марки/размеры {}. Сначала согласуйте ручное обновление оформления.',
                            u'Replacement/removal of opening Id {} blocked: linked tags/dimensions {}. Review annotation updates manually first.').format(
                                boxes._id_int(opening_eid),u', '.join(unicode(boxes._id_int(eid)) for eid in protected)))


def try_translate(doc, opening, previous, target):
    if not core.translation_only(previous['geometry'],target) or not opening_matches(opening,previous):
        return None
    annotation_ids=protected_annotations(doc,opening)
    all_before=annotation_states(doc)
    before={eid: (bool(getattr(doc.GetElement(eid),'IsOrphaned',False)),
                  bool(getattr(doc.GetElement(eid),'AreReferencesAvailable',True)),
                  getattr(doc.GetElement(eid),'NumberOfSegments',0)) for eid in annotation_ids}
    sub=SubTransaction(doc)
    sub.Start()
    try:
        delta=boxes._xyz([boxes.ft(a-b) for a,b in zip(target['center_mm'],previous['geometry']['center_mm'])])
        if delta.GetLength()>1e-9:
            ElementTransformUtils.MoveElement(doc,opening.Id,delta)
        doc.Regenerate()
        if not opening_matches(opening,dict(previous,geometry=target)):
            raise ValueError('Updated opening geometry does not match the issued snapshot')
        all_after=annotation_states(doc)
        for eid,state in all_before.items():
            current=all_after.get(eid)
            if (current is None or (not state[0] and current[0]) or
                    (state[1] and not current[1]) or state[2]!=current[2]):
                raise ValueError('Opening translation would damage annotation references')
        for eid in annotation_ids:
            annotation=doc.GetElement(eid)
            if (annotation is None or (not before[eid][0] and bool(getattr(annotation,'IsOrphaned',False))) or
                    (before[eid][1] and not bool(getattr(annotation,'AreReferencesAvailable',True))) or
                    before[eid][2]!=getattr(annotation,'NumberOfSegments',0)):
                raise ValueError('Opening translation would orphan an annotation')
        if sub.Commit()!=TransactionStatus.Committed:
            return None
        return opening
    except Exception:
        if sub.GetStatus()==TransactionStatus.Started:
            sub.RollBack()
        return None


def accept(doc, records, settings):
    """One selected group -> one opening; replacements only after explicit UI confirmation."""
    core.check_recipient(records,settings.get('opening_recipient','KR'),settings['opening_project'],store.model_id(doc))
    registry = store.registry(doc)
    receipts=core.receipts(registry,settings.get('opening_recipient','KR'))
    core.common_part(records)
    keys = set(core.task_key(r) for r in records)
    if any(r['status'] != 'issued' for r in records):
        raise ValueError(tr(u'Нельзя принять отозванное задание',u'Withdrawn tasks cannot be accepted'))
    old_receipts = {receipts[key]['opening_uid']: receipts[key]
                    for key in keys if key in receipts and receipts[key].get('opening_uid')}
    for receipt in old_receipts.values():
        if not set(receipt['revisions']).issubset(keys):
            raise ValueError(tr(u'Выберите все задания существующего объединённого отверстия',u'Select every task belonging to the existing merged opening'))
    g = core.merge_geometry([r['geometry'] for r in records])
    if len(old_receipts) == 1:
        previous = list(old_receipts.values())[0]
        existing = doc.GetElement(previous['opening_uid'])
        if (existing and opening_matches(existing,previous) and previous['status'] == 'accepted' and
                previous['revisions'] == {core.task_key(r):r['revision'] for r in records} and
                core.geometry_equal(previous['geometry'],g)):
            return existing
    opening=None
    if len(old_receipts)==1:
        previous=list(old_receipts.values())[0]
        old=doc.GetElement(previous['opening_uid'])
        if old is not None and set(previous['revisions'])==keys:
            opening=try_translate(doc,old,previous,g)
    if opening is None:
        for uid in old_receipts:
            old=doc.GetElement(uid)
            if old:
                assert_safe_replacement(doc,old)
        for uid in old_receipts:
            old=doc.GetElement(uid)
            if old:
                doc.Delete(old.Id)
        opening=create_native_opening(doc,g)
    opening_id = (list(old_receipts.values())[0]['opening_id'] if len(old_receipts)==1 and
                  set(list(old_receipts.values())[0]['revisions'])==keys else core.guid())
    receipt = dict(schema=1,role='receipt',object_part=records[0].get('object_part',''),recipient=settings.get('opening_recipient','KR'),opening_id=opening_id, opening_uid=opening.UniqueId,
                   revisions={core.task_key(r):r['revision'] for r in records}, status='accepted',
                   geometry=g,issued_tasks=copy.deepcopy(records),project=settings['opening_project'],author=doc.Application.Username,revit_user=doc.Application.Username,windows_user=windows_user(),at=now())
    # Native Opening categories may not support project text parameters. ES is authoritative here.
    store.write(opening,receipt)
    param = opening.LookupParameter(settings['opening_json_param']) if settings.get('opening_json_param') else None
    if param is not None:
        store.set_parameter(opening,settings['opening_json_param'],receipt)
    for key in keys:
        receipts[key] = receipt
    registry.setdefault('decisions' if settings.get('opening_recipient','KR')=='KR' else 'ar_decisions',[]).append(copy.deepcopy(receipt))
    store.save_registry(doc,registry)
    return opening


def reject(doc, records, settings, comment, grouped=False):
    core.check_recipient(records,settings.get('opening_recipient','KR'),settings['opening_project'],store.model_id(doc))
    registry = store.registry(doc)
    if grouped:
        from lowlife.opening_tasks_remarks import create
        registry,group=create(registry,records,settings['opening_project'],settings.get('opening_recipient','KR'),
                              store.model_id(doc),comment,doc.Application.Username,now(),windows_user())
        updated=set()
        for record in records:
            receipt=core.receipts(registry,settings.get('opening_recipient','KR'))[core.task_key(record)]
            uid=receipt.get('opening_uid')
            if not uid or uid in updated:continue
            opening=doc.GetElement(uid)
            if opening is not None:
                store.write(opening,receipt)
                name=settings.get('opening_json_param')
                if name and opening.LookupParameter(name) is not None:store.set_parameter(opening,name,receipt)
            updated.add(uid)
        store.save_registry(doc,registry)
        return group
    receipts=core.receipts(registry,settings.get('opening_recipient','KR'))
    for record in records:
        key = core.task_key(record)
        previous = receipts.get(key)
        if previous and previous.get('opening_uid'):
            raise ValueError(tr(u'Для реализованного отверстия нужно отдельное решение: отклонение его не удаляет',u'An implemented opening must be reviewed explicitly, not silently rejected'))
        receipt = dict(schema=1,status='rejected',object_part=record.get('object_part',''),recipient=settings.get('opening_recipient','KR'),revisions={key:record['revision']},comment=comment,
                       author=doc.Application.Username,revit_user=doc.Application.Username,windows_user=windows_user(),at=now(),project=settings['opening_project'])
        receipts[key] = receipt
        registry.setdefault('decisions' if settings.get('opening_recipient','KR')=='KR' else 'ar_decisions',[]).append(copy.deepcopy(receipt))
    store.save_registry(doc,registry)


def remove_withdrawn(doc, records, settings):
    core.check_recipient(records,settings.get('opening_recipient','KR'),settings['opening_project'],store.model_id(doc))
    registry = store.registry(doc)
    receipts=core.receipts(registry,settings.get('opening_recipient','KR'))
    selected = {core.task_key(r):r for r in records}
    if any(r['status'] != 'withdrawn' for r in records):
        raise ValueError(tr(u'Выберите только отозванные задания',u'Select withdrawn tasks only'))
    groups = {}
    for key in selected:
        receipt = receipts.get(key)
        if receipt and receipt.get('opening_uid'):
            groups[receipt['opening_uid']] = receipt
    for uid,receipt in groups.items():
        if not set(receipt['revisions']).issubset(set(selected)):
            raise ValueError(tr(u'Объединённое отверстие содержит другие задания: рассмотрите всю группу',u'Merged opening still includes other tasks; review the entire group'))
        element = doc.GetElement(uid)
        if element:
            assert_safe_replacement(doc,element)
            doc.Delete(element.Id)
        for key in receipt['revisions']:
            updated = dict(receipt,status='withdrawn',opening_uid=None,at=now(),author=doc.Application.Username,revit_user=doc.Application.Username,windows_user=windows_user(),
                           revisions={k:selected[k]['revision'] for k in receipt['revisions']})
            receipts[key] = updated
        registry.setdefault('decisions' if settings.get('opening_recipient','KR')=='KR' else 'ar_decisions',[]).append(updated)
    store.save_registry(doc,registry)


def opening_matches(opening, receipt, tolerance_mm=1.0):
    """Detect manual changes to native openings before confirming a KR result."""
    try:
        if not isinstance(opening,Opening):
            return False
        points = list(opening.BoundaryRect) if opening.IsRectBoundary else [
            curve.GetEndPoint(i) for curve in opening.BoundaryCurves for i in (0,1)]
        if not points:
            return False
        g = receipt['geometry']
        x = g['x_dir']
        y = [-x[1],x[0],0]
        axes = [x,y,[0,0,1]]
        coords = [[sum(v*a for v,a in zip(boxes._t(p),axis))*boxes.FT_TO_MM for p in points] for axis in axes]
        center = [sum(v*a for v,a in zip(g['center_mm'],axis)) for axis in axes]
        indices = (0,2) if g['kind']=='wall' else (0,1)
        for i in indices:
            if abs((max(coords[i])+min(coords[i]))/2-center[i])>tolerance_mm:
                return False
            if abs(max(coords[i])-min(coords[i])-g['size_mm'][i])>tolerance_mm:
                return False
        return True
    except Exception:
        return False


def structural_results(doc, project, recipient='KR'):
    local = store.registry(doc)
    results = []
    for link in FilteredElementCollector(doc).OfClass(RevitLinkInstance):
        kr_doc = link.GetLinkDocument()
        if kr_doc is None:
            continue
        for tid,task in local['tasks'].items():
            if task.get('recipient','KR')!=recipient or task['project'] != project or task['status'] != 'issued' or task['geometry']['host_model'] != store.model_id(kr_doc):
                continue
            receipt = core.receipts(store.registry(kr_doc),recipient).get(core.task_key(task))
            if not receipt or receipt['status'] != 'accepted':
                continue
            if receipt['revisions'].get(core.task_key(task)) != task['revision']:
                continue
            opening = kr_doc.GetElement(receipt['opening_uid'])
            if opening is not None and opening_matches(opening,receipt):
                results.append((task,receipt,link))
    return results


def confirm_results(doc, results, settings):
    registry = store.registry(doc)
    for task,receipt,link in results:
        if registry['tasks'][task['task_id']]['revision'] != task['revision']:
            raise ValueError(tr(u'Ревизия задания изменилась',u'Task revision changed'))
        confirmation = dict(object_part=task.get('object_part',''),recipient=task.get('recipient','KR'),task_id=task['task_id'],revision=task['revision'],
                            opening_id=receipt['opening_id'],kr_model=store.model_id(link.GetLinkDocument()),
                            author=doc.Application.Username,revit_user=doc.Application.Username,windows_user=windows_user(),at=now())
        registry['tasks'][task['task_id']]['confirmation'] = confirmation
        registry.setdefault('confirmations',[]).append(copy.deepcopy(confirmation))
        inst = doc.GetElement(task['owner_uid'])
        if inst:
            store.set_parameter(inst,settings['opening_json_param'],registry['tasks'][task['task_id']])
    store.save_registry(doc,registry)


def visible_issue(inst, settings, record=None, changed=False):
    # Values written into the model are data, never translated.
    values = {
        'opening_status_param': (u'Изменено после выдачи' if changed else
            u'Отозвано' if record and record['status']=='withdrawn' else
            u'Выдано' if record else u'Черновик'),
        'opening_issue_param': unicode(record.get('issue_number',record['issue_id'])) if record else u'',
        'opening_revision_param': unicode(record['revision']) if record else u'',
        'opening_date_param': record['issued_at'] if record else u'',
    }
    for key,value in values.items():
        name = settings.get(key)
        if not name:
            continue
        param = inst.LookupParameter(name)
        if param is None or param.IsReadOnly or param.StorageType != StorageType.String:
            raise ValueError(tr(u'Нужен текстовый параметр экземпляра: {}',u'Text instance parameter required: {}').format(name))
        param.Set(value)


def recipient_feedback(doc, project, registry=None):
    """Read each linked registry once. Missing/replaced/unloaded models stay unavailable."""
    from lowlife import opening_tasks_feedback as feedback
    local=registry if registry is not None else store.registry(doc)
    tasks=[task for task in local['tasks'].values() if task['project']==project]
    needed=set(task['geometry']['host_model'] for task in tasks)
    models={}
    for link in FilteredElementCollector(doc).OfClass(RevitLinkInstance):
        linked=link.GetLinkDocument()
        if linked is not None:
            model=store.model_id(linked)
            if model in needed and model not in models:
                models[model]=(linked,store.registry(linked))
    from lowlife import opening_tasks_remarks as remarks
    group_maps={}
    for model,(linked,remote) in models.items():
        for recipient in ('KR','AR'):
            group_maps[(model,recipient)]=remarks.latest_by_task(remote,project,recipient)
    known={core.task_key(t):t for t in tasks}
    checked={}
    group_states={}
    def inspect(model,linked,reply):
        if not reply or not reply.get('opening_uid'):return None,False
        identity=(model,reply['opening_uid'],core.dumps(reply.get('geometry',{})))
        if identity not in checked:
            opening=linked.GetElement(reply['opening_uid'])
            checked[identity]=(opening,bool(opening is not None and opening_matches(opening,reply)))
        return checked[identity]
    result={}
    for task in tasks:
        target=models.get(task['geometry']['host_model'])
        receipt=None
        opening=None
        matches=False
        if target:
            linked,registry=target
            receipt=core.receipts(registry,task.get('recipient','KR')).get(core.task_key(task))
            if receipt and receipt.get('project')!=project:
                receipt=None
            opening,matches=inspect(task['geometry']['host_model'],linked,receipt)
        state=feedback.evaluate(task,receipt,bool(target),opening is not None,matches)
        label,action=feedback.describe(state)
        confirmation=task.get('confirmation',{})
        if state=='accepted' and confirmation.get('revision')==task['revision'] and confirmation.get('opening_id')==receipt.get('opening_id'):
            label=tr(u'Результат подтверждён ВИС',u'Result confirmed by VIS')
            action=tr(u'Действий не требуется',u'No action required')
        group=group_maps.get((task['geometry']['host_model'],task.get('recipient','KR')),{}).get(core.task_key(task))
        remark_state=remarks.state(task,receipt,group) if group else ''
        if group:
            group_key=(task['geometry']['host_model'],group['id'])
            if group_key not in group_states:
                group_states[group_key]=remarks.group_state(group,core.receipts(target[1],task.get('recipient','KR')),known,
                    verified=lambda reply:inspect(task['geometry']['host_model'],target[0],reply)[1])
            if state in ('missing','modified'):remark_state='correction'
        if remark_state=='review':
            label=tr(u'Исправлено, ожидает проверки',u'Corrected, awaiting review')
        result[core.task_key(task)]=dict(feedback_available=bool(target),
            remark_group_id=group['id'] if group else '',remark_number=group['number'] if group else '',
            remark_state=remark_state,remark_group_state=group_states[group_key] if group else '',
            result=label,next_action=action,
            comment=group['comment'] if group else receipt.get('comment','') if receipt else '',
            reply_revision=unicode(receipt.get('revisions',{}).get(core.task_key(task),'')) if receipt else '',
            attention=state not in ('accepted','withdrawn'))
    return result


def delete_boxes(doc, elements):
    """Delete validated original local boxes atomically; keep issued snapshots."""
    from System.Collections.Generic import List
    from Autodesk.Revit.DB import ElementId
    unique={inst.UniqueId:inst for inst in elements}
    for inst in unique.values():
        data=metadata(inst)
        if inst.Document!=doc or not data or data.get('owner_uid')!=inst.UniqueId:
            raise ValueError(tr(u'Удалять можно только собственные боксы заданий текущей модели.',
                               u'Only original task boxes in the current model can be deleted.'))
    if unique:
        doc.Delete(List[ElementId]([inst.Id for inst in unique.values()]))
    return len(unique)


def change_building(doc, elements, value, settings):
    """Change working metadata only; a later issue records a new revision."""
    from lowlife import opening_tasks_parts as parts
    parts.require_choice(settings['opening_project'],value)
    registry=store.registry(doc)
    prepared=[]
    for inst in {el.UniqueId:el for el in elements if el is not None}.values():
        data=metadata(inst)
        if inst.Document!=doc or not data or data.get('owner_uid')!=inst.UniqueId or data.get('source_model')!=store.model_id(doc):
            raise ValueError(tr(u'Выберите собственные боксы текущей модели.',u'Select original boxes in the current model.'))
        record=registry['tasks'].get(data['task_id'])
        if record and record['project']!=settings['opening_project']:
            raise ValueError(tr(u'Бокс выдан в другом объекте.',u'Box was issued for another project.'))
        if data.get('object_part','')==value:
            continue
        working=None
        if record is None:
            param=inst.LookupParameter(settings['opening_json_param'])
            if param is None or param.StorageType!=StorageType.String:
                raise ValueError(tr(u'У бокса нет текстового JSON-параметра задания.',u'Box has no text task JSON parameter.'))
            working=core.loads(param.AsString())
            working['object_part']=value
        prepared.append((inst,dict(data,object_part=value),record,working))
    for inst,data,record,working in prepared:
        store.write(inst,data)
        if working is not None:
            store.set_parameter(inst,settings['opening_json_param'],working)
        visible_issue(inst,{'opening_status_param':settings.get('opening_status_param','')},record,
                      bool(record and record['status']=='issued'))
    from lowlife.opening_tasks_views import sync_selection_filters
    sync_selection_filters(doc,settings,registry)
    return len(prepared)
