# -*- coding: utf-8 -*-
"""Revit adapter for enclosure drawing, internal tray routing and marking.

Enclosures are rectangular DuctType or CableTrayType system families.
Model-specific parameter/type names live only in per-user settings.
Every route operation is atomic: a failed fitting rolls the entire operation back.
"""
import copy
import json
import math

from lowlife.i18n import tr
from lowlife import fire_boxes_core as core, fire_boxes_settings as cfg

try:
    unicode
except NameError:
    unicode = str

from Autodesk.Revit import DB
from Autodesk.Revit.DB.Electrical import CableTray, CableTrayType
from Autodesk.Revit.DB.Mechanical import Duct, DuctType, MechanicalSystemType
from Autodesk.Revit.UI.Selection import ISelectionFilter, ObjectType
from Autodesk.Revit.Exceptions import OperationCanceledException
from System import Guid, String
from System.Collections.Generic import List
from pyrevit import forms, script

SCHEMA_GUID = Guid('970ca558-37ef-49a1-8e41-d4e10e7ed6d4')
CURVE_CATS = (DB.BuiltInCategory.OST_DuctCurves, DB.BuiltInCategory.OST_CableTray)
FITTING_CATS = (DB.BuiltInCategory.OST_DuctFitting, DB.BuiltInCategory.OST_CableTrayFitting)


def eid(value):
    return value.Value if hasattr(value, 'Value') else value.IntegerValue


def xyz(point):
    return DB.XYZ(*point)


def coords(point):
    return (point.X, point.Y, point.Z)


def category(element):
    return eid(element.Category.Id) if element is not None and element.Category else None


def in_categories(element, categories):
    return category(element) in [int(c) for c in categories]


def is_duct_type(element):
    return isinstance(element, DuctType)


def type_label(element):
    if element is None:
        return u''
    name = DB.Element.Name.GetValue(element)
    family = getattr(element, 'FamilyName', u'')
    return u'{} : {} [{}]'.format(family, name, eid(element.Id))


def type_name(element):
    return DB.Element.Name.GetValue(element) if element is not None else u''


def type_options(doc, kind):
    types = []
    if kind in ('box', 'tray'):
        types.extend(DB.FilteredElementCollector(doc).OfClass(CableTrayType).ToElements())
    if kind == 'box':
        types.extend(t for t in DB.FilteredElementCollector(doc).OfClass(DuctType)
                     if t.Shape == DB.ConnectorProfileType.Rectangular)
    if kind == 'system':
        types.extend(DB.FilteredElementCollector(doc).OfClass(MechanicalSystemType).ToElements())
    return dict((type_label(t), t) for t in types)


def workset_options(doc):
    """Persist names rather than document-local workset ids."""
    if not doc.IsWorkshared:
        return {}
    return dict((unicode(w.Name), w.Id) for w in
                DB.FilteredWorksetCollector(doc).OfKind(DB.WorksetKind.UserWorkset))


def resolve_workset(doc, name):
    if not doc.IsWorkshared:
        return None
    if not name:
        return doc.GetWorksetTable().GetActiveWorksetId()
    workset = workset_options(doc).get(name)
    if workset is None:
        raise ValueError(tr(u'Рабочий набор «{}» не найден. Выберите рабочий набор в настройках.',
                            u'Workset "{}" was not found. Select a workset in settings.').format(name))
    return workset


def assign_workset(element, workset_id):
    if workset_id is None:
        return
    parameter = element.get_Parameter(DB.BuiltInParameter.ELEM_PARTITION_PARAM)
    if (parameter is None or parameter.IsReadOnly or
            not parameter.Set(eid(workset_id))):
        raise ValueError(tr(u'Не удалось назначить рабочий набор элементу {}.',
                            u'Could not assign a workset to element {}.').format(eid(element.Id)))


def connectors(element):
    manager = getattr(element, 'ConnectorManager', None)
    if manager is None:
        model = getattr(element, 'MEPModel', None)
        manager = model.ConnectorManager if model is not None else None
    if manager is None:
        return []
    return [c for c in manager.Connectors if c.ConnectorType == DB.ConnectorType.End]


def fitting_members(fitting):
    """Revit can insert a transition directly between an elbow and a curve."""
    result, queue = {}, [fitting]
    while queue:
        element = queue.pop()
        key = eid(element.Id)
        if key in result:
            continue
        result[key] = element
        for connector in connectors(element):
            for ref in connector.AllRefs:
                if in_categories(ref.Owner, FITTING_CATS) and eid(ref.Owner.Id) not in result:
                    queue.append(ref.Owner)
    return result


def connected_curves(fitting):
    result = {}
    for element in fitting_members(fitting).values():
        for connector in connectors(element):
            for other in connector.AllRefs:
                if in_categories(other.Owner, CURVE_CATS):
                    result[eid(other.Owner.Id)] = other.Owner
    return result


def schema():
    from Autodesk.Revit.DB.ExtensibleStorage import Schema, SchemaBuilder, AccessLevel
    result = Schema.Lookup(SCHEMA_GUID)
    if result is None:
        builder = SchemaBuilder(SCHEMA_GUID)
        builder.SetSchemaName('LowLifeFireEnclosure')
        builder.SetReadAccessLevel(AccessLevel.Public)
        builder.SetWriteAccessLevel(AccessLevel.Public)
        builder.AddSimpleField('Data', String)
        result = builder.Finish()
    return result


def read_data(element):
    entity = element.GetEntity(schema())
    if not entity.IsValid():
        return None
    values = json.loads(entity.Get[String](schema().GetField('Data')))
    if values.get('owner_uid') != element.UniqueId:
        values.pop('tray_ids', None)  # copied enclosure, not its original contents
    return values


def write_data(element, values):
    from Autodesk.Revit.DB.ExtensibleStorage import Entity
    entity = Entity(schema())
    values = dict(values, owner_uid=element.UniqueId)
    entity.Set[String](schema().GetField('Data'), unicode(json.dumps(values, ensure_ascii=False)))
    element.SetEntity(entity)


def note_parameter(element, settings):
    name = settings.get('enclosure_note_param', '').strip()
    return element.LookupParameter(name) if name else element.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)


def note(element, settings):
    parameter = note_parameter(element, settings)
    if parameter is None or parameter.IsReadOnly or parameter.StorageType != DB.StorageType.String:
        raise ValueError(tr(u'У элемента {} нет доступного текстового параметра примечания.',
                            u'Element {} has no writable text note parameter.').format(eid(element.Id)))
    parameter.Set(core.merge_note(parameter.AsString(), core.description(settings)))


def mark(element, settings):
    name = settings.get('inside_flag_param', '').strip()
    parameter = element.LookupParameter(name) if name else None
    is_bool = False
    if parameter is not None:
        try:
            is_bool = parameter.Definition.GetDataType() == DB.SpecTypeId.Boolean.YesNo
        except AttributeError:
            is_bool = parameter.Definition.ParameterType == DB.ParameterType.YesNo
    if (parameter is None or parameter.IsReadOnly or parameter.StorageType != DB.StorageType.Integer or not is_bool):
        raise ValueError(tr(u'У элемента {} нет доступного параметра экземпляра Да/Нет «{}».',
                            u'Element {} has no writable instance Yes/No parameter "{}".').format(eid(element.Id), name))
    if not parameter.Set(1):
        raise ValueError(tr(u'Не удалось отметить элемент {}.', u'Could not mark element {}.').format(eid(element.Id)))


def size(element, width_mm, height_mm):
    is_tray = isinstance(element, CableTray)
    pairs = [(DB.BuiltInParameter.RBS_CABLETRAY_WIDTH_PARAM if is_tray else DB.BuiltInParameter.RBS_CURVE_WIDTH_PARAM, width_mm),
             (DB.BuiltInParameter.RBS_CABLETRAY_HEIGHT_PARAM if is_tray else DB.BuiltInParameter.RBS_CURVE_HEIGHT_PARAM, height_mm)]
    for key, value in pairs:
        parameter = element.get_Parameter(key)
        if parameter is None or parameter.IsReadOnly or not parameter.Set(float(value) / 304.8):
            raise ValueError(tr(u'Не удалось задать сечение элемента {}.', u'Could not set element {} cross-section.').format(eid(element.Id)))


def dimensions(element):
    if isinstance(element, CableTray):
        return (element.Width * 304.8, element.Height * 304.8)
    return (element.get_Parameter(DB.BuiltInParameter.RBS_CURVE_WIDTH_PARAM).AsDouble() * 304.8,
            element.get_Parameter(DB.BuiltInParameter.RBS_CURVE_HEIGHT_PARAM).AsDouble() * 304.8)


def create_curve(doc, element_type, system_type, level_id, start, end, width, height):
    if start.DistanceTo(end) < doc.Application.ShortCurveTolerance:
        raise ValueError(tr(u'Участок слишком короткий.', u'Route segment is too short.'))
    if isinstance(element_type, CableTrayType):
        result = CableTray.Create(doc, element_type.Id, start, end, level_id)
    elif isinstance(element_type, DuctType):
        if system_type is None or not isinstance(system_type, MechanicalSystemType):
            raise ValueError(tr(u'Выберите систему воздуховода в настройках.', u'Select a duct system in settings.'))
        result = Duct.Create(doc, system_type.Id, element_type.Id, level_id, start, end)
    else:
        raise ValueError(tr(u'Нужен прямоугольный тип воздуховода или кабельного лотка.',
                            u'Select a rectangular duct or cable tray type.'))
    size(result, width, height)
    return result


def nearest_connector(element, point):
    return min(connectors(element), key=lambda c: c.Origin.DistanceTo(point))


def align_tray_section(doc, element, start, end, target_up):
    doc.Regenerate()
    actual_up = connectors(element)[0].CoordinateSystem.BasisY
    tangent = (end - start).Normalize()
    angle = core.section_roll_angle(coords(tangent), coords(actual_up), target_up)
    if abs(angle) <= 1e-7:
        return
    if abs(tangent.Z) < 1e-6:
        # Revit reports this constraint only at Transaction.Commit, after rotate
        # and Regenerate have appeared to succeed. Reject it before that point.
        raise ValueError(tr(u'Сечение горизонтального короба повёрнуто вокруг оси. '
                            u'Выровняйте ширину короба по горизонтали: Revit не допускает боковой наклон горизонтального лотка.',
                            u'The horizontal enclosure cross-section is rolled. '
                            u'Align its width horizontally: Revit does not allow a horizontal tray to tilt sideways.'))
    DB.ElementTransformUtils.RotateElement(doc, element.Id,
                                           DB.Line.CreateUnbound(start, tangent), angle)


def join(doc, curves, point):
    """Pair the straight-through ports first, then branch ports for tees/crosses."""
    ports = [nearest_connector(el, point) for el in curves]
    if len(ports) not in (2, 3, 4):
        raise ValueError(tr(u'Поддерживаются узлы с 2, 3 или 4 соединениями.', u'Junctions must have 2, 3 or 4 ports.'))
    pair = min(((i, j) for i in range(len(ports)) for j in range(i+1, len(ports))),
               key=lambda ij: ports[ij[0]].CoordinateSystem.BasisZ.DotProduct(ports[ij[1]].CoordinateSystem.BasisZ))
    ports = [ports[pair[0]], ports[pair[1]]] + [p for i, p in enumerate(ports) if i not in pair]
    if len(ports) == 2:
        parallel = abs(ports[0].CoordinateSystem.BasisZ.DotProduct(ports[1].CoordinateSystem.BasisZ)) > 0.9999
        if parallel:
            if ports[0].Origin.DistanceTo(ports[1].Origin) < 1e-5 and abs(ports[0].Width - ports[1].Width) < 1e-6 and abs(ports[0].Height - ports[1].Height) < 1e-6:
                ports[0].ConnectTo(ports[1])
                doc.Regenerate()
                for ref in ports[0].AllRefs:
                    if in_categories(ref.Owner, FITTING_CATS):
                        return ref.Owner
                return None
            return doc.Create.NewTransitionFitting(ports[0], ports[1])
        return doc.Create.NewElbowFitting(ports[0], ports[1])
    if len(ports) == 3:
        return doc.Create.NewTeeFitting(*ports)
    return doc.Create.NewCrossFitting(*ports)


class RouteFilter(ISelectionFilter):
    def __init__(self, trays_only=False):
        self.cats = (DB.BuiltInCategory.OST_CableTray, DB.BuiltInCategory.OST_CableTrayFitting) if trays_only else CURVE_CATS + FITTING_CATS

    def AllowElement(self, element):
        return in_categories(element, self.cats)

    def AllowReference(self, reference, point):
        return False


def pick(uidoc, trays_only=False):
    selected = [uidoc.Document.GetElement(i) for i in uidoc.Selection.GetElementIds()]
    filter_ = RouteFilter(trays_only)
    result = [el for el in selected if filter_.AllowElement(el)]
    if result:
        return result
    refs = uidoc.Selection.PickObjects(ObjectType.Element, filter_,
            tr(u'Выберите участки и соединительные детали, затем Готово.', u'Select segments and fittings, then Finish.'))
    return [uidoc.Document.GetElement(ref) for ref in refs]


def resolve_route(elements):
    curves = dict((eid(e.Id), e) for e in elements if in_categories(e, CURVE_CATS))
    explicit = dict((eid(e.Id), e) for e in elements if in_categories(e, FITTING_CATS))
    for fitting in explicit.values():
        curves.update(connected_curves(fitting))
    fittings = {}
    for fitting in explicit.values():
        fittings.update(fitting_members(fitting))
    for curve in list(curves.values()):
        for connector in connectors(curve):
            for ref in connector.AllRefs:
                owner = ref.Owner
                if in_categories(owner, FITTING_CATS):
                    neighbors = connected_curves(owner)
                    if neighbors and all(key in curves for key in neighbors):
                        fittings.update(fitting_members(owner))
    return curves, fittings


def _route_frames(curves, fittings):
    """Orient each connected run consistently regardless of stored curve direction.

    Parallel transport across horizontal/vertical elbows preserves tray lane
    identity. For branching runs the spanning tree is checked at every junction.
    """
    ends = dict((key, [coords(el.Location.Curve.GetEndPoint(i)) for i in (0, 1)]) for key, el in curves.items())
    adjacency = dict((key, []) for key in curves)
    for fitting in fittings.values():
        neighbors = list(connected_curves(fitting))
        for key in neighbors:
            for other in neighbors:
                if key != other:
                    adjacency[key].append((other, fitting))
    frames, directions = {}, {}
    for root in sorted(curves):
        if root in frames:
            continue
        directions[root] = core.unit(core.sub(ends[root][1], ends[root][0]))
        reference = core.frame(*ends[root])
        port = connectors(curves[root])[0]
        axes = (coords(port.CoordinateSystem.BasisX), coords(port.CoordinateSystem.BasisY))
        frames[root] = tuple(core.mul(vector, -1 if core.dot(vector, expected) < 0 else 1)
                             for vector, expected in zip(axes, reference))
        queue = [root]
        while queue:
            parent = queue.pop(0)
            for child, fitting in adjacency[parent]:
                if child in frames:
                    continue
                pc = min(connectors(fitting), key=lambda c: min(c.Origin.DistanceTo(xyz(p)) for p in ends[parent]))
                cc = min(connectors(fitting), key=lambda c: min(c.Origin.DistanceTo(xyz(p)) for p in ends[child]))
                pidx = min((0, 1), key=lambda i: xyz(ends[parent][i]).DistanceTo(pc.Origin))
                cidx = min((0, 1), key=lambda i: xyz(ends[child][i]).DistanceTo(cc.Origin))
                incoming = core.unit(core.sub(ends[parent][pidx], ends[parent][1-pidx]))
                outgoing = core.unit(core.sub(ends[child][1-cidx], ends[child][cidx]))
                axis = core.cross(incoming, outgoing)
                sine = math.sqrt(core.dot(axis, axis))
                cosine = core.dot(incoming, outgoing)
                if cosine < -0.9999:
                    raise ValueError(tr(u'Разворот на 180° требует отдельного участка.', u'A 180 degree turn needs an intermediate segment.'))
                def rotate(vector):
                    if sine < 1e-8:
                        return vector
                    normal = core.mul(axis, 1 / sine)
                    return core.add(core.add(core.mul(vector, cosine), core.mul(core.cross(normal, vector), sine)),
                                    core.mul(normal, core.dot(normal, vector) * (1 - cosine)))
                frames[child] = tuple(rotate(vector) for vector in frames[parent])
                directions[child] = outgoing
                queue.append(child)
    return ends, frames


def _junctions(curves, fittings, shifted):
    nodes = []
    processed = set()
    for fitting in fittings.values():
        if eid(fitting.Id) in processed:
            continue
        members = fitting_members(fitting)
        processed.update(members)
        neighbors = connected_curves(fitting)
        if len(neighbors) not in (2, 3, 4):
            raise ValueError(tr(u'Не поддерживается деталь {}: требуется 2–4 патрубка.',
                                u'Unsupported fitting {}: expected 2–4 ports.').format(eid(fitting.Id)))
        pairs = []
        for key in neighbors:
            source = curves[key]
            port = min([c for member in members.values() for c in connectors(member)],
                       key=lambda c: min(c.Origin.DistanceTo(source.Location.Curve.GetEndPoint(i)) for i in (0, 1)))
            index = min((0, 1), key=lambda i: port.Origin.DistanceTo(source.Location.Curve.GetEndPoint(i)))
            pairs.append((key, index))
        intersection = None
        for i in range(len(pairs)):
            for j in range(i+1, len(pairs)):
                ak, ai = pairs[i]
                bk, bi = pairs[j]
                da = core.sub(shifted[ak][1], shifted[ak][0])
                db = core.sub(shifted[bk][1], shifted[bk][0])
                if abs(core.dot(core.unit(da), core.unit(db))) < 0.9999:
                    intersection = core.line_intersection(shifted[ak][ai], da, shifted[bk][bi], db, 0.5/304.8)
                    break
            if intersection is not None:
                break
        if intersection is None:
            ak, ai = pairs[0]
            bk, bi = pairs[1]
            # Reducers keep both original endpoints and get a transition fitting.
            nodes.append((pairs, core.mul(core.add(shifted[ak][ai], shifted[bk][bi]), 0.5)))
            continue
        for key, index in pairs:
            line = shifted[key]
            direction = core.unit(core.sub(line[1], line[0]))
            distance = core.cross(core.sub(intersection, line[0]), direction)
            if math.sqrt(core.dot(distance, distance)) > 0.5/304.8:
                raise ValueError(tr(u'Смещения лотков не сходятся в детали {}. Разделите трассу на участки.',
                                    u'Tray offsets do not meet in fitting {}. Split the run into sections.').format(eid(fitting.Id)))
            line[index] = intersection
        nodes.append((pairs, intersection))
    # Direct curve-to-curve connections (without a family fitting).
    seen = set()
    for key, curve in curves.items():
        for port in connectors(curve):
            for ref in port.AllRefs:
                other = eid(ref.Owner.Id)
                pair = tuple(sorted((key, other)))
                if other not in curves or other == key or pair in seen:
                    continue
                seen.add(pair)
                i = min((0, 1), key=lambda n: curve.Location.Curve.GetEndPoint(n).DistanceTo(port.Origin))
                j = min((0, 1), key=lambda n: curves[other].Location.Curve.GetEndPoint(n).DistanceTo(ref.Origin))
                point = core.line_intersection(shifted[key][i], core.sub(shifted[key][1], shifted[key][0]),
                                               shifted[other][j], core.sub(shifted[other][1], shifted[other][0]), 0.5/304.8)
                shifted[key][i], shifted[other][j] = point, point
                nodes.append(([(key, i), (other, j)], point))
    return nodes


def add_trays(doc, elements, fallback, tray_type=None):
    # Newly created contents always use the current choice, even for old boxes.
    workset_id = resolve_workset(doc, fallback.get('tray_workset_name', ''))
    curves, fittings = resolve_route(elements)
    if not curves:
        raise ValueError(tr(u'Выберите короб или его соединительные детали.', u'Select an enclosure or its fittings.'))
    configs = {}
    for key, curve in curves.items():
        if not isinstance(curve.Location.Curve, DB.Line):
            raise ValueError(tr(u'Поддерживаются прямые участки с соединительными деталями.', u'Use straight segments connected by fittings.'))
        metadata = read_data(curve)
        configured_type = doc.GetElement(fallback['box_type_uid']) if fallback.get('box_type_uid') else None
        if not metadata and (configured_type is None or curve.GetTypeId() != configured_type.Id):
            raise ValueError(tr(u'Участок {} не относится к типу короба из настроек.',
                                u'Segment {} does not use the configured enclosure type.').format(key))
        configs[key] = copy.deepcopy(metadata['settings'] if metadata else fallback)
        configs[key]['inside_flag_param'] = fallback['inside_flag_param']
        configs[key]['enclosure_note_param'] = fallback['enclosure_note_param']
        for index, row in enumerate(configs[key]['trays']):
            uid = row.get('tray_type_uid')
            if not uid and index < len(fallback.get('trays', [])):
                uid = fallback['trays'][index].get('tray_type_uid')
            uid = uid or configs[key].get('tray_type_uid') or fallback.get('tray_type_uid') or (tray_type.UniqueId if tray_type is not None else '')
            element_type = doc.GetElement(uid) if uid else None
            if not isinstance(element_type, CableTrayType):
                raise ValueError(tr(u'Выберите тип для лотка №{} в настройках.',
                                    u'Select the type for tray #{} in settings.').format(index+1))
            row['tray_type_uid'] = uid
        if metadata and metadata.get('tray_ids'):
            if any(doc.GetElement(uid) is not None for uid in metadata['tray_ids']):
                raise ValueError(tr(u'В коробе {} уже созданы лотки. Повторная вставка остановлена.',
                                    u'Enclosure {} already has generated trays. Duplicate insertion stopped.').format(key))
        if not core.fits(*(dimensions(curve) + (configs[key],))):
            raise ValueError(tr(u'Короб {} меньше расчётного сечения. Измените размеры или настройки.',
                                u'Enclosure {} is smaller than the required section. Resize it or edit settings.').format(key))
    signature = lambda settings: (settings['product'], settings['rating'], settings['arrangement'],
                                  settings['gap_mm'], settings['clearance_mm'], settings['trays'],
                                  settings.get('support_bottom_mm'))
    sample = configs[next(iter(configs))]
    if any(signature(c) != signature(sample) for c in configs.values()):
        raise ValueError(tr(u'Выберите короба с одинаковым составом лотков и огнестойкостью.',
                            u'Select enclosures with the same tray layout and fire resistance.'))
    ends, frames = _route_frames(curves, fittings)
    created, by_source = [], dict((key, []) for key in curves)
    section = core.layout(sample)
    for row in section['trays']:
        row_type = doc.GetElement(row['tray_type_uid'])
        shifted = {}
        for key in curves:
            right, up = frames[key]
            port = connectors(curves[key])[0]
            actual_w, actual_h = dimensions(curves[key])
            if not core.section_fits_axes(row, right, up, coords(port.CoordinateSystem.BasisX),
                                          coords(port.CoordinateSystem.BasisY),
                                          actual_w - (2*section['wall'] if section['wall'] is not None else section['allowance_width']),
                                          actual_h - (2*section['wall'] if section['wall'] is not None else section['allowance_height'])):
                raise ValueError(tr(u'В участке {} повёрнуто сечение короба: лотки выходят за внутренний габарит. Разделите трассу или выровняйте сечения.',
                                    u'Enclosure {} has a rolled cross-section: trays exceed its inner bounds. Split the run or align the sections.').format(key))
            offset = core.add(core.mul(right, row['x']/304.8), core.mul(up, row['z']/304.8))
            shifted[key] = [core.add(p, offset) for p in ends[key]]
        nodes = _junctions(curves, fittings, shifted)
        lane = {}
        for key, source in curves.items():
            # A fitting must not extend a shifted segment through its opposite end.
            if core.dot(core.sub(shifted[key][1], shifted[key][0]), core.sub(ends[key][1], ends[key][0])) <= 0:
                raise ValueError(tr(u'Слишком короткий участок {} для выбранного расположения лотков.',
                                    u'Segment {} is too short for this tray arrangement.').format(key))
            level = source.ReferenceLevel
            lane[key] = create_curve(doc, row_type, None, level.Id, xyz(shifted[key][0]), xyz(shifted[key][1]), row['width'], row['height'])
            assign_workset(lane[key], workset_id)
            align_tray_section(doc, lane[key], xyz(shifted[key][0]), xyz(shifted[key][1]), frames[key][1])
            mark(lane[key], fallback)
            created.append(lane[key])
            by_source[key].append(lane[key].UniqueId)
        doc.Regenerate()
        for pairs, point in nodes:
            fitting = join(doc, [lane[key] for key, _index in pairs], xyz(point))
            if fitting is not None:
                doc.Regenerate()
                for member in fitting_members(fitting).values():
                    assign_workset(member, workset_id)
                    mark(member, fallback)
                    created.append(member)
                    for key, _index in pairs:
                        by_source[key].append(member.UniqueId)
    doc.Regenerate()
    for key, source in curves.items():
        note(source, configs[key])
        write_data(source, dict(version=1, settings=configs[key], tray_ids=by_source[key]))
    for fitting in fittings.values():
        note(fitting, sample)
        write_data(fitting, dict(version=1, settings=sample))
    return created


def geometry_solids(element):
    options = DB.Options()
    options.DetailLevel = DB.ViewDetailLevel.Fine
    result = []

    def visit(objects):
        if objects is None:
            return
        for obj in objects:
            if isinstance(obj, DB.Solid) and obj.Volume > 1e-9:
                result.append(obj)
            elif isinstance(obj, DB.GeometryInstance):
                visit(obj.GetInstanceGeometry())
    visit(element.get_Geometry(options))
    return result


def mark_targets(doc, elements, settings):
    """Explicit trays, or complete tray solids inside selected enclosures.

    Sequential solid subtraction tests containment in the union of the box
    segments AND their fittings. Mere bounding-box intersections never qualify.
    """
    configured = doc.GetElement(settings['box_type_uid']) if settings.get('box_type_uid') else None
    def is_box(element):
        return bool(read_data(element)) or (configured is not None and element.GetTypeId() == configured.Id)
    boxes = [el for el in elements if is_box(el) and in_categories(el, CURVE_CATS + FITTING_CATS)]
    for el in elements:
        if in_categories(el, FITTING_CATS) and any(is_box(c) for c in connected_curves(el).values()):
            if el not in boxes:
                boxes.append(el)
    if not boxes:
        selected = [el for el in elements if in_categories(el, (DB.BuiltInCategory.OST_CableTray, DB.BuiltInCategory.OST_CableTrayFitting))]
        _curves, fittings = resolve_route(selected)
        return list(dict((eid(el.Id), el) for el in selected + list(fittings.values())).values())
    curves, fittings = resolve_route(boxes)
    enclosures = list(curves.values()) + list(fittings.values())
    volumes = [solid for enclosure in enclosures for solid in geometry_solids(enclosure)]
    if not volumes:
        raise ValueError(tr(u'У выбранного короба нет геометрии для проверки содержимого.',
                            u'The selected enclosure has no solids for containment testing.'))
    bounds = [el.get_BoundingBox(None) for el in enclosures]
    bounds = [box for box in bounds if box is not None]
    minimum = DB.XYZ(min(b.Min.X for b in bounds), min(b.Min.Y for b in bounds), min(b.Min.Z for b in bounds))
    maximum = DB.XYZ(max(b.Max.X for b in bounds), max(b.Max.Y for b in bounds), max(b.Max.Z for b in bounds))
    cats = List[DB.BuiltInCategory]([DB.BuiltInCategory.OST_CableTray, DB.BuiltInCategory.OST_CableTrayFitting])
    candidates = list(DB.FilteredElementCollector(doc).WherePasses(DB.ElementMulticategoryFilter(cats))
                      .WhereElementIsNotElementType().WherePasses(DB.BoundingBoxIntersectsFilter(DB.Outline(minimum, maximum))))
    excluded = set(eid(el.Id) for el in enclosures)
    result = []
    with forms.ProgressBar(title=tr(u'Проверка содержимого короба', u'Checking enclosure contents'), cancellable=True) as progress:
        for index, element in enumerate(candidates):
            if progress.cancelled:
                raise OperationCanceledException()
            progress.update_progress(index + 1, max(1, len(candidates)))
            if eid(element.Id) in excluded or is_box(element):
                continue
            solids = geometry_solids(element)
            if not solids:
                continue
            contained = True
            for solid in solids:
                remainder = solid
                tolerance = max(1e-8, solid.Volume * 1e-6)
                try:
                    for volume in volumes:
                        remainder = DB.BooleanOperationsUtils.ExecuteBooleanOperation(remainder, volume, DB.BooleanOperationsType.Difference)
                        if remainder.Volume <= tolerance:
                            break
                except Exception:
                    raise ValueError(tr(u'Не удалось проверить геометрию элемента {}. Выберите лотки и детали явно.',
                                        u'Could not check element {} geometry. Select the trays and fittings explicitly.').format(eid(element.Id)))
                if remainder.Volume > tolerance:
                    contained = False
                    break
            if contained:
                result.append(element)
    return result


def draw(doc, uidoc, settings):
    workset_id = resolve_workset(doc, settings.get('box_workset_name', ''))
    box_type = doc.GetElement(settings['box_type_uid'])
    system_type = doc.GetElement(settings['system_type_uid']) if settings.get('system_type_uid') else None
    if box_type is None:
        raise ValueError(tr(u'Выберите тип короба в настройках.', u'Select an enclosure type in settings.'))
    level = doc.ActiveView.GenLevel
    if level is None:
        raise ValueError(tr(u'Откройте план уровня для рисования короба.', u'Open a level plan to draw the enclosure.'))
    section = core.layout(settings)
    created, previous, last_point = [], None, None
    group = DB.TransactionGroup(doc, tr(u'Нарисовать огнезащитный короб', u'Draw fire enclosure'))
    group.Start()
    try:
        while True:
            try:
                point = uidoc.Selection.PickPoint(tr(u'Точка оси короба; Esc — закончить трассу.', u'Enclosure axis point; Esc finishes the route.'))
            except OperationCanceledException:
                break
            point = DB.XYZ(point.X, point.Y, level.Elevation + float(settings['elevation_mm'])/304.8)
            if last_point is None:
                last_point = point
                continue
            if last_point.DistanceTo(point) < doc.Application.ShortCurveTolerance:
                continue
            transaction = DB.Transaction(doc, tr(u'Участок короба', u'Enclosure segment'))
            transaction.Start()
            try:
                segment = create_curve(doc, box_type, system_type, level.Id, last_point, point, section['width'], section['height'])
                assign_workset(segment, workset_id)
                note(segment, settings)
                write_data(segment, dict(version=1, settings=settings))
                doc.Regenerate()
                if previous is not None:
                    fitting = join(doc, [previous, segment], last_point)
                    if fitting is not None:
                        doc.Regenerate()
                        for member in fitting_members(fitting).values():
                            assign_workset(member, workset_id)
                            note(member, settings)
                            write_data(member, dict(version=1, settings=settings))
                            created.append(member)
                if transaction.Commit() != DB.TransactionStatus.Committed:
                    raise ValueError(tr(u'Revit отменил построение участка.', u'Revit rolled back segment creation.'))
                created.append(segment)
                previous, last_point = segment, point
                uidoc.RefreshActiveView()
            except Exception:
                if transaction.GetStatus() == DB.TransactionStatus.Started:
                    transaction.RollBack()
                raise
        status = group.Assimilate() if created else group.RollBack()
        if created and status != DB.TransactionStatus.Committed:
            raise ValueError(tr(u'Revit отменил построение короба.', u'Revit rolled back enclosure creation.'))
    except Exception:
        if group.GetStatus() == DB.TransactionStatus.Started:
            group.RollBack()
        raise
    return created


def run(doc, uidoc, action):
    from pyrevit import EXEC_PARAMS
    from lowlife import fire_boxes_ui, select_list
    settings = cfg.load()
    try:
        if EXEC_PARAMS.config_mode:
            fire_boxes_ui.show(doc)
            return
        if action in ('draw', 'add') and (not settings.get('box_type_uid') or doc.GetElement(settings['box_type_uid']) is None):
            settings = fire_boxes_ui.show(doc)
            if settings is None:
                return
        if action in ('add', 'mark') and not settings.get('inside_flag_param'):
            settings = fire_boxes_ui.show(doc)
            if settings is None:
                return
        if action == 'draw':
            created = draw(doc, uidoc, settings)
        else:
            selected = pick(uidoc)
            if not selected:
                return
            if action == 'add':
                if any(not row.get('tray_type_uid') for row in settings['trays']):
                    settings = fire_boxes_ui.show(doc, settings)
                    if settings is None:
                        return
            targets = mark_targets(doc, selected, settings) if action == 'mark' else None
            if targets is not None and not targets:
                forms.alert(tr(u'Не найдены лотки и детали, полностью находящиеся в выбранном коробе.',
                               u'No trays or fittings fully contained in the selected enclosure were found.'))
                return
            transaction = DB.Transaction(doc, tr(u'Лотки в огнезащитном коробе', u'Trays in fire enclosure'))
            transaction.Start()
            try:
                if action == 'add':
                    created = add_trays(doc, selected, settings)
                else:
                    created = targets
                    for element in created:
                        mark(element, settings)
                if transaction.Commit() != DB.TransactionStatus.Committed:
                    raise ValueError(tr(u'Revit отменил операцию.', u'Revit rolled back the operation.'))
            except Exception:
                if transaction.GetStatus() == DB.TransactionStatus.Started:
                    transaction.RollBack()
                raise
        if created:
            uidoc.Selection.SetElementIds(List[DB.ElementId]([e.Id for e in created]))
            forms.alert(tr(u'Готово. Элементов: {}.', u'Done. Elements: {}.').format(len(created)))
    except OperationCanceledException:
        return
    except Exception as exc:
        script.get_logger().exception('Fire enclosure operation failed')
        forms.alert(tr(u'Операция не выполнена:\n{}\n\nПроверьте настройки типов, соединительных деталей и параметров.',
                       u'Operation failed:\n{}\n\nCheck type, fitting and parameter settings.').format(exc))
