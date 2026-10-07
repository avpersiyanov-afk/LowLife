# -*- coding: utf-8 -*-
"""
Перенос DWG-подложки в линии детализации и текст — кнопка
Tools.panel/DwgToDrafting («DWG → чертёжный вид»).

Линии, дуги, полилинии, эллипсы и сплайны берутся из геометрии самого
импорта (ImportInstance.get_Geometry) — с учётом слоёв, скрытых на виде.
Текст Revit API у DWG не отдаёт, поэтому он читается из DXF того же
чертежа (lowlife.dxf_text): DXF рядом с DWG, конвертация ODA File Converter
или файл, указанный вручную. Координаты DXF совмещаются с геометрией
импорта по габаритам (dxf_text.fit_mapping), так что текст встаёт туда же,
где он был на подложке.

Куда: в новый чертёжный вид (вид источника «разворачивается» в плоскость
XY: у плана координаты X/Y сохраняются) или на тот же вид, где лежит DWG
(линии проецируются в плоскость вида).
"""

import math
import os
import shutil
import tempfile

from Autodesk.Revit.DB import (
    Arc,
    BuiltInCategory,
    BuiltInParameter,
    CADLinkType,
    Curve,
    Element,
    ElementId,
    Ellipse,
    FilteredElementCollector,
    GeometryInstance,
    GraphicsStyleType,
    HorizontalTextAlignment,
    ImportInstance,
    Line,
    ModelPathUtils,
    Options,
    PolyLine,
    TextNote,
    TextNoteOptions,
    TextNoteType,
    Transform,
    VerticalTextAlignment,
    ViewDrafting,
    ViewFamily,
    ViewFamilyType,
    ViewPlan,
    XYZ,
)

from lowlife import dxf_text


FEET_TO_MM = 304.8
_BAD_NAME_CHARS = u"\\:{}[]|;<>?`~"


def element_name(el):
    try:
        return Element.Name.GetValue(el)
    except Exception:
        return u""


def clean_name(name):
    """Имя без символов, запрещённых Revit в именах стилей/типов/видов."""
    result = u"".join(u"_" if ch in _BAD_NAME_CHARS else ch for ch in (name or u""))
    return result.strip() or u"_"


# --- поиск импорта ----------------------------------------------------------

def find_imports(doc, view, selected_ids):
    """
    DWG/DXF-импорты для переноса: выделенные, иначе видимые на виде.
    """
    selected = [doc.GetElement(i) for i in selected_ids]
    picked = [el for el in selected if isinstance(el, ImportInstance)]
    if picked:
        return picked
    return [el for el in FilteredElementCollector(doc, view.Id).OfClass(ImportInstance)]


def import_label(doc, imp):
    cad_type = doc.GetElement(imp.GetTypeId())
    name = element_name(cad_type) if cad_type is not None else u""
    return name or u"Импорт {}".format(imp.Id.IntegerValue)


def import_file_path(doc, imp):
    """Полный путь к файлу связанного DWG/DXF или None (вставлен, не связан)."""
    cad_type = doc.GetElement(imp.GetTypeId())
    if not isinstance(cad_type, CADLinkType):
        return None
    try:
        ref = cad_type.GetExternalFileReference()
        path = ModelPathUtils.ConvertModelPathToUserVisiblePath(ref.GetAbsolutePath())
    except Exception:
        return None
    return path or None


def sibling_dxf(path):
    """DXF с тем же именем рядом с файлом (или сам файл, если это DXF)."""
    if not path:
        return None
    root, ext = os.path.splitext(path)
    if ext.lower() == ".dxf" and os.path.isfile(path):
        return path
    for candidate in (root + ".dxf", root + ".DXF"):
        if os.path.isfile(candidate):
            return candidate
    return None


# --- ODA File Converter ----------------------------------------------------

def find_oda_converter(hint=None):
    if hint and os.path.isfile(hint):
        return hint
    found = []
    for env in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)"):
        base = os.environ.get(env)
        oda = os.path.join(base, "ODA") if base else None
        if not oda or not os.path.isdir(oda):
            continue
        for name in os.listdir(oda):
            exe = os.path.join(oda, name, "ODAFileConverter.exe")
            if os.path.isfile(exe):
                found.append(exe)
    return sorted(found)[-1] if found else None


def convert_with_oda(exe, dwg_path, timeout_ms=180000):
    """
    DWG → DXF (ASCII, AutoCAD 2018) во временной папке. Возвращает
    (путь к DXF, папка для удаления) или бросает RuntimeError.
    """
    from System.Diagnostics import Process, ProcessStartInfo

    work = tempfile.mkdtemp(prefix="lowlife_dwg_")
    src_dir = os.path.join(work, "in")
    out_dir = os.path.join(work, "out")
    os.makedirs(src_dir)
    os.makedirs(out_dir)
    name = os.path.basename(dwg_path)
    shutil.copy2(dwg_path, os.path.join(src_dir, name))

    info = ProcessStartInfo()
    info.FileName = exe
    info.Arguments = u'"{}" "{}" "ACAD2018" "DXF" "0" "1" "{}"'.format(src_dir, out_dir, name)
    info.UseShellExecute = False
    info.CreateNoWindow = True
    proc = Process.Start(info)
    if not proc.WaitForExit(timeout_ms):
        try:
            proc.Kill()
        except Exception:
            pass
        raise RuntimeError(u"ODA File Converter не ответил за {} с.".format(timeout_ms // 1000))

    for fname in os.listdir(out_dir):
        if fname.lower().endswith(".dxf"):
            return os.path.join(out_dir, fname), work
    raise RuntimeError(u"ODA File Converter не создал DXF (код выхода {}).".format(proc.ExitCode))


# --- геометрия импорта -------------------------------------------------------

class ImportGeometry(object):
    def __init__(self):
        self.items = []          # [(кривая в координатах модели, категория слоя или None)]
        self.top_transform = None  # символ импорта → модель
        self.symbol_extents = None
        self.symbol_z = 0.0
        self.hidden_skipped = 0


def _layer_category(doc, geom_obj):
    try:
        style = doc.GetElement(geom_obj.GraphicsStyleId)
    except Exception:
        return None
    if style is None:
        return None
    try:
        return style.GraphicsStyleCategory
    except Exception:
        return None


def _extend(geo, pts):
    for p in pts:
        e = geo.symbol_extents
        if e is None:
            geo.symbol_extents = (p.X, p.Y, p.X, p.Y)
            geo.symbol_z = p.Z
        else:
            geo.symbol_extents = (min(e[0], p.X), min(e[1], p.Y), max(e[2], p.X), max(e[3], p.Y))


def _curve_points(curve):
    try:
        return list(curve.Tessellate())
    except Exception:
        return []


def _walk_symbol(doc, view, geom, to_symbol, geo):
    """to_symbol — из координат geom в координаты символа верхнего экземпляра."""
    for obj in geom:
        if isinstance(obj, GeometryInstance):
            _walk_symbol(doc, view, obj.GetSymbolGeometry(), to_symbol.Multiply(obj.Transform), geo)
            continue
        if isinstance(obj, PolyLine):
            pts = list(obj.GetTransformed(to_symbol).GetCoordinates())
            curves = [Line.CreateBound(a, b) for a, b in zip(pts, pts[1:]) if a.DistanceTo(b) > 1e-9]
        elif isinstance(obj, Curve):
            curves = [obj.CreateTransformed(to_symbol)]
            pts = _curve_points(curves[0])
        else:
            continue  # тела, сетки, заливки — не переносятся
        _extend(geo, pts)
        cat = _layer_category(doc, obj)
        if cat is not None and view is not None:
            try:
                if view.GetCategoryHidden(cat.Id):
                    geo.hidden_skipped += len(curves)
                    continue
            except Exception:
                pass
        for c in curves:
            geo.items.append((c, cat))


def collect_geometry(doc, imp, view):
    """
    Кривые импорта в координатах модели (без слоёв, скрытых на view) +
    габарит всей геометрии в координатах символа и преобразование символ → модель.
    """
    geom = None
    try:
        opts = Options()
        opts.View = view
        geom = imp.get_Geometry(opts)
    except Exception:
        geom = None
    if geom is None:
        geom = imp.get_Geometry(Options())
    geo = ImportGeometry()
    objs = list(geom) if geom is not None else []
    top = None
    for obj in objs:
        if isinstance(obj, GeometryInstance):
            top = obj.Transform
            break
    geo.top_transform = top if top is not None else Transform.Identity
    inv = geo.top_transform.Inverse
    for obj in objs:
        if isinstance(obj, GeometryInstance):
            _walk_symbol(doc, view, obj.GetSymbolGeometry(), inv.Multiply(obj.Transform), geo)
        else:
            _walk_symbol(doc, view, [obj], inv, geo)
    top = geo.top_transform
    geo.items = [(c.CreateTransformed(top), cat) for c, cat in geo.items]
    return geo


# --- куда переносить ----------------------------------------------------------

class Placement(object):
    """
    Перевод точек/кривых модели в плоскость целевого вида.

    to_target — поворот (система вида-источника → XY для чертёжного вида,
    тождество для того же вида); затем проекция вдоль normal на плоскость
    через origin. right/up — оси целевого вида для угла текста.
    """

    def __init__(self, to_target, origin, normal, right, up, view):
        self.to_target = to_target
        self.origin = origin
        self.normal = normal
        self.right = right
        self.up = up
        self.view = view

    def _shift(self, p):
        return self.normal.Multiply(-(p - self.origin).DotProduct(self.normal))

    def point(self, p):
        q = self.to_target.OfPoint(p)
        return q + self._shift(q)

    def vector(self, v):
        return self.to_target.OfVector(v)

    def angle(self, v):
        d = self.vector(v)
        return math.atan2(d.DotProduct(self.up), d.DotProduct(self.right))

    def curves(self, curve):
        """Кривая в плоскости вида (одна) или ломаная — список кривых."""
        c = curve
        if not self.to_target.IsIdentity:
            c = c.CreateTransformed(self.to_target)
        try:
            ref = c.Evaluate(0.0, True) if c.IsBound else c.Evaluate(0.0, False)
        except Exception:
            ref = None
        if ref is not None:
            shift = self._shift(ref)
            if shift.GetLength() > 1e-9:
                c = c.CreateTransformed(Transform.CreateTranslation(shift))
        return [_bounded(c)]

    def polyline(self, curve):
        """Запасной вариант: кривая как ломаная, каждая точка — проекцией."""
        pts = [self.point(p) for p in _curve_points(curve)]
        return [Line.CreateBound(a, b) for a, b in zip(pts, pts[1:]) if a.DistanceTo(b) > 1e-6]


def _bounded(c):
    if c.IsBound:
        return c
    if isinstance(c, Arc):
        return Arc.Create(c.Center, c.Radius, 0.0, 2 * math.pi, c.XDirection, c.YDirection)
    if isinstance(c, Ellipse):
        return Ellipse.CreateCurve(c.Center, c.RadiusX, c.RadiusY, c.XDirection, c.YDirection,
                                   0.0, 2 * math.pi)
    return c


def _frame_inverse(right, up, normal):
    t = Transform.Identity
    t.BasisX = XYZ(right.X, up.X, normal.X)
    t.BasisY = XYZ(right.Y, up.Y, normal.Y)
    t.BasisZ = XYZ(right.Z, up.Z, normal.Z)
    t.Origin = XYZ.Zero
    return t


def view_plane_origin(view):
    try:
        sp = view.SketchPlane
        if sp is not None:
            return sp.GetPlane().Origin
    except Exception:
        pass
    if isinstance(view, ViewPlan) and view.GenLevel is not None:
        return XYZ(0, 0, view.GenLevel.ProjectElevation)
    return view.Origin


def placement_same_view(view):
    return Placement(Transform.Identity, view_plane_origin(view), view.ViewDirection,
                     view.RightDirection, view.UpDirection, view)


def placement_drafting(source_view, target_view):
    t = _frame_inverse(source_view.RightDirection, source_view.UpDirection,
                       source_view.ViewDirection)
    return Placement(t, XYZ.Zero, XYZ.BasisZ, XYZ.BasisX, XYZ.BasisY, target_view)


def unique_view_name(doc, base):
    names = set(element_name(v) for v in FilteredElementCollector(doc).OfClass(ViewDrafting))
    base = clean_name(base)
    name = base
    k = 2
    while name in names:
        name = u"{} ({})".format(base, k)
        k += 1
    return name


def create_drafting_view(doc, name, scale):
    vft = None
    for t in FilteredElementCollector(doc).OfClass(ViewFamilyType):
        if t.ViewFamily == ViewFamily.Drafting:
            vft = t
            break
    if vft is None:
        raise RuntimeError(u"В проекте нет типа чертёжного вида.")
    view = ViewDrafting.Create(doc, vft.Id)
    view.Name = unique_view_name(doc, name)
    try:
        view.Scale = scale
    except Exception:
        pass
    return view


# --- стили линий -----------------------------------------------------------------

def _lines_category(doc):
    return doc.Settings.Categories.get_Item(BuiltInCategory.OST_Lines)


def find_line_style(doc, name):
    """GraphicsStyle стиля линий по имени (без учёта регистра) или None."""
    want = (name or u"").strip().lower()
    for sub in _lines_category(doc).SubCategories:
        if sub.Name.strip().lower() == want:
            return sub.GetGraphicsStyle(GraphicsStyleType.Projection)
    return None


class LayerStyles(object):
    """Стили линий по слоям DWG: «<префикс><слой>», создаются по мере надобности."""

    def __init__(self, doc, prefix):
        self.doc = doc
        self.prefix = prefix or u""
        self.cache = {}
        self.created = []
        cat = _lines_category(doc)
        self.existing = dict((sub.Name.lower(), sub) for sub in cat.SubCategories)

    def style_for(self, layer_cat):
        layer = layer_cat.Name if layer_cat is not None else u"0"
        if layer in self.cache:
            return self.cache[layer]
        name = clean_name(self.prefix + layer)
        sub = self.existing.get(name.lower())
        if sub is None:
            cats = self.doc.Settings.Categories
            sub = cats.NewSubcategory(_lines_category(self.doc), name)
            self.existing[name.lower()] = sub
            self.created.append(name)
            if layer_cat is not None:
                _copy_layer_look(layer_cat, sub)
        style = sub.GetGraphicsStyle(GraphicsStyleType.Projection)
        self.cache[layer] = style
        return style


def _copy_layer_look(src, dst):
    try:
        color = src.LineColor
        if color is not None and color.IsValid:
            dst.LineColor = color
    except Exception:
        pass
    try:
        weight = src.GetLineWeight(GraphicsStyleType.Projection)
        if weight:
            dst.SetLineWeight(weight, GraphicsStyleType.Projection)
    except Exception:
        pass
    try:
        pattern = src.GetLinePatternId(GraphicsStyleType.Projection)
        if pattern is not None and pattern != ElementId.InvalidElementId:
            dst.SetLinePatternId(pattern, GraphicsStyleType.Projection)
    except Exception:
        pass


# --- типы текста ----------------------------------------------------------------

def find_text_type(doc, name):
    want = (name or u"").strip().lower()
    for t in FilteredElementCollector(doc).OfClass(TextNoteType):
        if element_name(t).strip().lower() == want:
            return t
    return None


def default_text_type(doc):
    from Autodesk.Revit.DB import ElementTypeGroup
    tid = doc.GetDefaultElementTypeId(ElementTypeGroup.TextNoteType)
    t = doc.GetElement(tid) if tid != ElementId.InvalidElementId else None
    if t is None:
        t = FilteredElementCollector(doc).OfClass(TextNoteType).FirstElement()
    return t


class TextTypes(object):
    """Типы текста нужной высоты (на бумаге, мм) и сжатия — копии исходного."""

    def __init__(self, doc, base_type, prefix):
        self.doc = doc
        self.base = base_type
        self.prefix = prefix or u""
        self.cache = {}
        self.created = []
        self.by_name = dict((element_name(t), t)
                            for t in FilteredElementCollector(doc).OfClass(TextNoteType))

    def type_for(self, height_mm, width_factor):
        h = max(0.1, round(height_mm, 1))
        w = round(width_factor, 2) if abs(width_factor - 1.0) > 0.005 else 1.0
        key = (h, w)
        if key in self.cache:
            return self.cache[key]
        name = u"{}{:.1f} мм".format(self.prefix, float(h))
        if w != 1.0:
            name += u" x{:.2f}".format(float(w))
        name = clean_name(name)
        t = self.by_name.get(name)
        if t is None:
            t = self.base.Duplicate(name)
            self.by_name[name] = t
            self.created.append(name)
            t.get_Parameter(BuiltInParameter.TEXT_SIZE).Set(h / FEET_TO_MM)
            try:
                t.get_Parameter(BuiltInParameter.TEXT_WIDTH_SCALE).Set(w)
            except Exception:
                pass
            try:
                # прозрачный фон — чтобы текст не перекрывал линии
                t.get_Parameter(BuiltInParameter.TEXT_BACKGROUND).Set(1)
            except Exception:
                pass
        self.cache[key] = t
        return t


_HALIGN = {
    dxf_text.HALIGN_LEFT: HorizontalTextAlignment.Left,
    dxf_text.HALIGN_CENTER: HorizontalTextAlignment.Center,
    dxf_text.HALIGN_RIGHT: HorizontalTextAlignment.Right,
}
_VALIGN = {
    dxf_text.VALIGN_BOTTOM: VerticalTextAlignment.Bottom,
    dxf_text.VALIGN_MIDDLE: VerticalTextAlignment.Middle,
    dxf_text.VALIGN_TOP: VerticalTextAlignment.Top,
}


# --- перенос -------------------------------------------------------------------

class TransferResult(object):
    def __init__(self):
        self.lines = 0
        self.lines_failed = 0
        self.texts = 0
        self.texts_failed = 0
        self.texts_hidden = 0
        self.errors = []

    def error(self, message):
        if len(self.errors) < 10 and message not in self.errors:
            self.errors.append(message)


def _hidden_layer_names(doc, imp, view):
    """Имена слоёв импорта, скрытых на виде-источнике (в верхнем регистре)."""
    hidden = set()
    cat = imp.Category
    if cat is None or view is None:
        return hidden
    try:
        whole = view.GetCategoryHidden(cat.Id)
    except Exception:
        whole = False
    for sub in cat.SubCategories:
        try:
            if whole or view.GetCategoryHidden(sub.Id):
                hidden.add(sub.Name.upper())
        except Exception:
            pass
    return hidden


def transfer_lines(doc, geo, placement, style_for, result):
    """style_for(категория слоя) → GraphicsStyle или None (стиль по умолчанию)."""
    short = doc.Application.ShortCurveTolerance
    view = placement.view
    for curve, layer_cat in geo.items:
        try:
            pieces = placement.curves(curve)
        except Exception:
            pieces = None
        style = style_for(layer_cat)
        made = _make_detail_curves(doc, view, pieces, style, short)
        if made is None:
            try:
                made = _make_detail_curves(doc, view, placement.polyline(curve), style, short)
            except Exception as err:
                result.error(u"{}".format(err))
                made = None
        if made is None:
            result.lines_failed += 1
        else:
            result.lines += made


def _make_detail_curves(doc, view, curves, style, short):
    if not curves:
        return None
    made = 0
    created = []
    try:
        for c in curves:
            if c.Length < short:
                continue
            dc = doc.Create.NewDetailCurve(view, c)
            created.append(dc)
            if style is not None:
                dc.LineStyle = style
            made += 1
    except Exception:
        for dc in created:
            try:
                doc.Delete(dc.Id)
            except Exception:
                pass
        return None
    return made


def transfer_texts(doc, imp, source_view, geo, drawing, mapping, placement, text_types, result):
    scale, ox, oy = mapping
    top = geo.top_transform
    hidden = _hidden_layer_names(doc, imp, source_view)
    view = placement.view
    view_scale = float(view.Scale or 1)
    model_scale = top.Scale if top is not None else 1.0

    for t in drawing.texts:
        if t.layer.upper() in hidden:
            result.texts_hidden += 1
            continue
        try:
            p_model = top.OfPoint(XYZ(t.x * scale + ox, t.y * scale + oy, geo.symbol_z))
            direction = top.OfVector(XYZ(math.cos(t.angle), math.sin(t.angle), 0))
            height_ft = t.height * scale * model_scale
            text_type = text_types.type_for(height_ft / view_scale * FEET_TO_MM, t.width_factor)

            opts = TextNoteOptions(text_type.Id)
            opts.HorizontalAlignment = _HALIGN[t.halign]
            try:
                opts.VerticalAlignment = _VALIGN[t.valign]
            except Exception:
                pass
            opts.Rotation = placement.angle(direction)
            try:
                opts.KeepRotatedTextReadable = False
            except Exception:
                pass
            TextNote.Create(doc, view.Id, placement.point(p_model), t.text.replace(u"\n", u"\r"), opts)
            result.texts += 1
        except Exception as err:
            result.texts_failed += 1
            result.error(u"Текст «{}»: {}".format(t.text[:30], err))
