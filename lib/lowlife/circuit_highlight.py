# -*- coding: utf-8 -*-
"""
Подсветка на активном виде элементов с электрическими коннекторами, у
которых ещё нет ни одной электрической цепи (кнопка «Подсветить без
цепи» на CircuitsDelete.panel).

Подсветка — это OverrideGraphicSettings вида, а не блокировка/изменение
самих элементов, поэтому она не мешает тут же создавать цепи как через
другие кнопки LowLife, так и штатной командой Revit «Создать электрическую
цепь». Как только у подсвеченного элемента появляется цепь, оверрайд с
него снимается сам — без повторного запуска кнопки: см.
install_idling_watch (подписка на UIApplication.Idling, как в
route_preview.schedule_preview_cleanup — Idling, а не DocumentChanged,
потому что события DocumentChanged срабатывают ещё внутри чужой
транзакции и менять документ оттуда небезопасно/может зациклиться, а
Idling — специально безопасный момент между действиями пользователя).
"""

from Autodesk.Revit.DB import (
    BuiltInCategory, Color, ElementId, FilteredElementCollector, FillPatternElement,
    OverrideGraphicSettings, Transaction
)

from lowlife.electrical_circuits import count_electrical_connectors

HIGHLIGHT_COLOR = Color(255, 0, 0)
LINE_WEIGHT = 6

# Электрооборудование (панели/изоляторы) в этом проекте всегда ИСТОЧНИК
# цепи (system.SelectPanel), а не её член — GetElectricalSystems() на
# панели пуст, даже когда от неё заведено много цепей, поэтому панели
# исключаются из кандидатов, иначе подсвечивались бы всегда.
# Обобщённые модели (линии проводки и т.п., см. fire_alarm_wire_marks) —
# не устройства, подсвечивать их не нужно, даже если у семейства случайно
# есть электрический коннектор.
_EXCLUDED_CATEGORY_IDS = set([
    int(BuiltInCategory.OST_ElectricalEquipment),
    int(BuiltInCategory.OST_GenericModel),
])

# {(doc_key, view_id_int): set(element_id_int)} — что подсвечено этой
# кнопкой и где; doc_key нужен, чтобы Idling-проверка (она видит только
# АКТИВНЫЙ документ) не трогала записи других открытых документов, приняв
# их view.Id за "вид не найден" и удалив.
_highlighted_by_view = {}

_idling_installed = False


def _doc_key(doc):
    try:
        return doc.PathName or doc.Title
    except:
        return u""


def has_circuit(el):
    mep_model = getattr(el, "MEPModel", None)
    if mep_model is None:
        return False
    try:
        return len(list(mep_model.GetElectricalSystems())) > 0
    except:
        return False


def _find_solid_fill_pattern_id(doc):
    try:
        for p in FilteredElementCollector(doc).OfClass(FillPatternElement):
            try:
                if p.GetFillPattern().IsSolidFill:
                    return p.Id
            except:
                continue
    except:
        pass
    return None


def _build_overrides(doc):
    ogs = OverrideGraphicSettings()

    try:
        ogs.SetProjectionLineColor(HIGHLIGHT_COLOR)
        ogs.SetProjectionLineWeight(LINE_WEIGHT)
        ogs.SetCutLineColor(HIGHLIGHT_COLOR)
        ogs.SetCutLineWeight(LINE_WEIGHT)
    except:
        pass

    # Заливка — необязательное усиление подсветки для "объёмных" семейств
    # (у которых обводка почти не видна); при любой несовместимости с
    # версией API просто остаёмся с одной обводкой линий.
    solid_id = _find_solid_fill_pattern_id(doc)
    if solid_id is not None:
        try:
            ogs.SetSurfaceForegroundPatternId(solid_id)
            ogs.SetSurfaceForegroundPatternColor(HIGHLIGHT_COLOR)
            ogs.SetSurfaceForegroundPatternVisible(True)
            ogs.SetCutForegroundPatternId(solid_id)
            ogs.SetCutForegroundPatternColor(HIGHLIGHT_COLOR)
            ogs.SetCutForegroundPatternVisible(True)
        except:
            pass

    return ogs


def collect_elements_without_circuit(doc, view):
    """Элементы вида с электрическими коннекторами, но без цепи."""
    candidates = FilteredElementCollector(doc, view.Id).WhereElementIsNotElementType().ToElements()

    result = []
    for el in candidates:
        try:
            if el.Category is not None and el.Category.Id.IntegerValue in _EXCLUDED_CATEGORY_IDS:
                continue
            if count_electrical_connectors(el) > 0 and not has_circuit(el):
                result.append(el)
        except:
            continue

    return result


def highlight_elements_without_circuit(doc, view):
    """
    Подсвечивает на view все элементы без цепи (см.
    collect_elements_without_circuit), снимая предыдущую подсветку этой
    кнопки на этом же виде. Возвращает число подсвеченных элементов.
    Вызывать внутри revit.Transaction.
    """
    view_key = (_doc_key(doc), view.Id.IntegerValue)

    for eid in _highlighted_by_view.pop(view_key, set()):
        try:
            view.SetElementOverrides(ElementId(eid), OverrideGraphicSettings())
        except:
            pass

    without_circuit = collect_elements_without_circuit(doc, view)
    ogs = _build_overrides(doc)

    marked_ids = set()
    for el in without_circuit:
        try:
            view.SetElementOverrides(el.Id, ogs)
            marked_ids.add(el.Id.IntegerValue)
        except:
            pass

    if marked_ids:
        _highlighted_by_view[view_key] = marked_ids

    return len(marked_ids)


def _recheck_and_clear(doc):
    """
    Снимает подсветку с элементов, у которых уже появилась цепь — только
    по видам ТЕКУЩЕГО активного документа (записи других открытых
    документов не трогаем: у них другая нумерация ElementId, и приняли бы
    чужой вид за отсутствующий).
    """
    current_doc_key = _doc_key(doc)
    emptied_views = []

    for view_key, ids in list(_highlighted_by_view.items()):
        doc_key, view_id_int = view_key
        if doc_key != current_doc_key:
            continue

        view = doc.GetElement(ElementId(view_id_int))
        if view is None:
            emptied_views.append(view_key)
            continue

        still_pending = set()
        for eid in ids:
            el = doc.GetElement(ElementId(eid))
            if el is None:
                continue
            if has_circuit(el):
                try:
                    view.SetElementOverrides(ElementId(eid), OverrideGraphicSettings())
                except:
                    pass
            else:
                still_pending.add(eid)

        if still_pending:
            _highlighted_by_view[view_key] = still_pending
        else:
            emptied_views.append(view_key)

    for view_key in emptied_views:
        _highlighted_by_view.pop(view_key, None)


def install_idling_watch(uiapp):
    """
    Подписывается на UIApplication.Idling один раз за сеанс (идемпотентно
    на уровне процесса — модуль переиспользуется между запусками кнопки
    в пределах одного pyRevit engine). Каждый тик, пока есть что
    перепроверять, снимает подсветку с элементов, у которых уже появилась
    цепь.
    """
    global _idling_installed
    if _idling_installed:
        return

    def _on_idling(sender, args):
        if not _highlighted_by_view:
            return

        doc = sender.ActiveUIDocument.Document if sender.ActiveUIDocument else None
        if doc is None:
            return

        t = Transaction(doc, u"Снять подсветку без цепи")
        try:
            t.Start()
            _recheck_and_clear(doc)
            t.Commit()
        except:
            try:
                t.RollBack()
            except:
                pass

    try:
        uiapp.Idling += _on_idling
        _idling_installed = True
    except:
        pass
