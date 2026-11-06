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
from Autodesk.Revit.DB import (CurveArray, ElementTransformUtils, FamilyInstance, FilteredElementCollector,
                               Floor, Line, LocationPoint, Opening, Options, RevitLinkInstance, StorageType,
                               SubTransaction, TransactionStatus, ViewDetailLevel, Wall, XYZ)
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
    placer = boxes.BoxPlacer(doc, symbol, settings, workset)
    managed = {}
    for inst in FilteredElementCollector(doc).OfClass(FamilyInstance):
        data = metadata(inst)
        if data and data.get('owner_uid') == inst.UniqueId:
            key = (data['source_uid'], data['host_uid'], data['host_link_uid'])
            if key in managed:
                raise ValueError(tr(u'Найдены дубли идентификатора чернового задания',u'Duplicate managed draft identity'))
            managed[key] = (inst, data)
    options = Options()
    options.DetailLevel = ViewDetailLevel.Fine
    categories = boxes._host_categories(settings)
    src = boxes._Source(source.GetLinkDocument(), source)
    entries, errors = [], []
    issued_ids = set(store.registry(doc)['tasks'])
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
            try:
                box, reason = boxes.box_for(route, crossing, settings)
                if box is None:
                    raise ValueError(reason)
                if settings['opening_increase'] != 'none':
                    amount = (geometry.recommended_increase_mm(boxes.mm(max(geometry.opening_sides(box))))
                              if settings['opening_increase'] == 'auto' else float(settings['opening_increase']))
                    box = geometry.enlarge_opening(box, boxes.ft(amount))
                key = (route.UniqueId, crossing.host.UniqueId, source.UniqueId)
                previous = managed.get(key)
                sub.Start()
                if previous:
                    inst, data = previous
                    if not isinstance(inst.Location, LocationPoint):
                        raise ValueError(tr(u'У бокса нет точки вставки',u'Draft has no point location'))
                    target = boxes._xyz(box.origin(placer.at_bottom))
                    angle = box.angle() - inst.Location.Rotation
                    ElementTransformUtils.RotateElement(doc, inst.Id,
                        Line.CreateBound(inst.Location.Point, inst.Location.Point.Add(XYZ.BasisZ)), angle)
                    ElementTransformUtils.MoveElement(doc, inst.Id, target.Subtract(inst.Location.Point))
                else:
                    if placer._existing_at(boxes._xyz(box.origin(placer.at_bottom)), boxes._xyz(box.center)):
                        raise ValueError(tr(u'На пересечении уже есть бокс, не связанный с заданием',u'An unmanaged box already exists at this crossing'))
                    inst = placer._create(boxes._xyz(box.origin(placer.at_bottom)), box)
                    data = dict(schema=1, role='draft', task_id=core.guid(), owner_uid=inst.UniqueId)
                placer.result.missing_params.clear()
                placer._apply_sizes(inst, box)
                if placer.result.missing_params:
                    raise ValueError(tr(u'Нет параметров размеров бокса',u'Missing box size parameters'))
                placer._set_host_filter(inst, crossing.kind)
                data = dict(data, source_model=store.model_id(doc), source_uid=route.UniqueId,
                            host_uid=crossing.host.UniqueId, host_model=store.model_id(source.GetLinkDocument()),
                            host_link_uid=source.UniqueId, kind=crossing.kind,
                            origin_bottom=placer.at_bottom,
                            size_params=[settings[k] for k in ('box_width_param','box_depth_param','box_height_param')])
                doc.Regenerate()
                actual = [read_size(inst,name) for name in data['size_params']]
                if any(abs(a-b)>1e-6 for a,b in zip(actual,(box.width,box.depth,box.height))):
                    raise ValueError(tr(u'Семейство не применило запрошенные размеры',u'Family did not apply the requested dimensions'))
                # Working updates never overwrite a released snapshot in the parameter.
                if data['task_id'] not in issued_ids:
                    store.set_parameter(inst, settings['opening_json_param'],
                        dict(data, status='draft', geometry=host_geometry(inst,data,source)))
                store.write(inst, data)
                if sub.Commit() != TransactionStatus.Committed:
                    raise ValueError(tr(u'Транзакция бокса не зафиксирована',u'Draft transaction was not committed'))
                managed[key] = (inst, data)
                entries.append((route.element, crossing, inst, box))
            except Exception as ex:
                if sub.GetStatus() == TransactionStatus.Started:
                    sub.RollBack()
                del placer.existing[count:]
                errors.append((route.Id, unicode(ex)))
    errors += [(inst.Id, err) for inst, err in placer.result.filter_errors]
    return entries, errors


def prepare_drafts(doc, elements, settings):
    drafts = []
    for inst in elements:
        data = metadata(inst)
        if not data:
            raise ValueError(tr(u'Выберите только боксы заданий ВИС',u'Select only VIS opening drafts'))
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
        drafts.append(dict(task_id=data['task_id'], source_model=data['source_model'], source_uid=data['source_uid'],
                           owner_uid=inst.UniqueId, geometry=host_geometry(inst,data,link)))
    return drafts


def publish(doc, elements, settings):
    drafts = prepare_drafts(doc,elements,settings)
    registry, changes = core.issue(store.registry(doc), drafts, settings['opening_project'],
                                   settings['opening_discipline'],doc.Application.Username,now())
    by_id = {d['task_id']: e for d,e in zip(drafts,elements)}
    for record in changes:
        store.set_parameter(by_id[record['task_id']],settings['opening_json_param'],record)
    if changes:
        store.save_registry(doc,registry)
    return changes


def retract(doc, task_ids, settings):
    registry, changes = core.withdraw(store.registry(doc),task_ids,doc.Application.Username,now())
    for record in changes:
        inst = doc.GetElement(record['owner_uid'])
        if inst:
            store.set_parameter(inst,settings['opening_json_param'],record)
    if changes:
        store.save_registry(doc,registry)
    return changes


def incoming(doc, project):
    """Only issued registry snapshots; NEVER the live linked box geometry."""
    records = {}
    for link in FilteredElementCollector(doc).OfClass(RevitLinkInstance):
        linked = link.GetLinkDocument()
        if linked is None:
            continue
        for record in store.registry(linked)['tasks'].values():
            if (record['project'] != project or record['recipient'] != 'KR' or
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
        raise ValueError(tr(u'Отверстие адресовано другой модели КР',u'Opening belongs to another structural model'))
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
    if not isinstance(host,Floor):
        raise ValueError(tr(u'Нужно перекрытие',u'A floor is required'))
    bb = host.get_BoundingBox(None)
    if bb is None or center.Z+h/2 < bb.Min.Z or center.Z-h/2 > bb.Max.Z:
        raise ValueError(tr(u'Перекрытие переместилось относительно выданного отверстия',u'Floor moved away from issued opening'))
    y = XYZ(-x.Y,x.X,0)
    points = [center.Add(x.Multiply(a*w/2)).Add(y.Multiply(b*d/2))
              for a,b in ((-1,-1),(1,-1),(1,1),(-1,1))]
    profile = CurveArray()
    for i in range(4):
        profile.Append(Line.CreateBound(points[i],points[(i+1)%4]))
    return doc.Create.NewOpening(host,profile,True)


def accept(doc, records, settings):
    """One selected group -> one opening; replacements only after explicit UI confirmation."""
    registry = store.registry(doc)
    keys = set(core.task_key(r) for r in records)
    if any(r['status'] != 'issued' for r in records):
        raise ValueError(tr(u'Нельзя принять отозванное задание',u'Withdrawn tasks cannot be accepted'))
    old_receipts = {registry['receipts'][key]['opening_uid']: registry['receipts'][key]
                    for key in keys if key in registry['receipts'] and registry['receipts'][key].get('opening_uid')}
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
    for uid in old_receipts:
        old = doc.GetElement(uid)
        if old:
            doc.Delete(old.Id)
    opening = create_native_opening(doc,g)
    opening_id = (list(old_receipts.values())[0]['opening_id'] if len(old_receipts)==1 and
                  set(list(old_receipts.values())[0]['revisions'])==keys else core.guid())
    receipt = dict(schema=1,role='receipt',opening_id=opening_id, opening_uid=opening.UniqueId,
                   revisions={core.task_key(r):r['revision'] for r in records}, status='accepted',
                   geometry=g,issued_tasks=copy.deepcopy(records),project=settings['opening_project'],author=doc.Application.Username,at=now())
    # Native Opening categories may not support project text parameters. ES is authoritative here.
    store.write(opening,receipt)
    param = opening.LookupParameter(settings['opening_json_param']) if settings.get('opening_json_param') else None
    if param is not None:
        store.set_parameter(opening,settings['opening_json_param'],receipt)
    for key in keys:
        registry['receipts'][key] = receipt
    registry.setdefault('decisions',[]).append(copy.deepcopy(receipt))
    store.save_registry(doc,registry)
    return opening


def reject(doc, records, settings, comment):
    registry = store.registry(doc)
    for record in records:
        key = core.task_key(record)
        previous = registry['receipts'].get(key)
        if previous and previous.get('opening_uid'):
            raise ValueError(tr(u'Для реализованного отверстия нужно отдельное решение: отклонение его не удаляет',u'An implemented opening must be reviewed explicitly, not silently rejected'))
        receipt = dict(schema=1,status='rejected',revisions={key:record['revision']},comment=comment,
                       author=doc.Application.Username,at=now(),project=settings['opening_project'])
        registry['receipts'][key] = receipt
        registry.setdefault('decisions',[]).append(copy.deepcopy(receipt))
    store.save_registry(doc,registry)


def remove_withdrawn(doc, records, settings):
    registry = store.registry(doc)
    selected = {core.task_key(r):r for r in records}
    if any(r['status'] != 'withdrawn' for r in records):
        raise ValueError(tr(u'Выберите только отозванные задания',u'Select withdrawn tasks only'))
    receipts = {}
    for key in selected:
        receipt = registry['receipts'].get(key)
        if receipt and receipt.get('opening_uid'):
            receipts[receipt['opening_uid']] = receipt
    for uid,receipt in receipts.items():
        if not set(receipt['revisions']).issubset(set(selected)):
            raise ValueError(tr(u'Объединённое отверстие содержит другие задания: рассмотрите всю группу',u'Merged opening still includes other tasks; review the entire group'))
        element = doc.GetElement(uid)
        if element:
            doc.Delete(element.Id)
        for key in receipt['revisions']:
            updated = dict(receipt,status='withdrawn',opening_uid=None,at=now(),author=doc.Application.Username,
                           revisions={k:selected[k]['revision'] for k in receipt['revisions']})
            registry['receipts'][key] = updated
        registry.setdefault('decisions',[]).append(updated)
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


def structural_results(doc, project):
    local = store.registry(doc)
    results = []
    for link in FilteredElementCollector(doc).OfClass(RevitLinkInstance):
        kr_doc = link.GetLinkDocument()
        if kr_doc is None:
            continue
        for tid,task in local['tasks'].items():
            if task['project'] != project or task['status'] != 'issued' or task['geometry']['host_model'] != store.model_id(kr_doc):
                continue
            receipt = store.registry(kr_doc)['receipts'].get(core.task_key(task))
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
        confirmation = dict(task_id=task['task_id'],revision=task['revision'],
                            opening_id=receipt['opening_id'],kr_model=store.model_id(link.GetLinkDocument()),
                            author=doc.Application.Username,at=now())
        registry['tasks'][task['task_id']]['confirmation'] = confirmation
        registry.setdefault('confirmations',[]).append(copy.deepcopy(confirmation))
        inst = doc.GetElement(task['owner_uid'])
        if inst:
            store.set_parameter(inst,settings['opening_json_param'],registry['tasks'][task['task_id']])
    store.save_registry(doc,registry)
