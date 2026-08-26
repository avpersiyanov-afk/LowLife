# -*- coding: utf-8 -*-
"""
Общая логика кнопок «Маршрут цепи» (временная линия по маршруту выбранной
цепи — для визуальной проверки, что маршрут выбран правильно). Используется
СКС и СКУД (ShowCircuitRoute на SCS.panel/SKUD.panel) — обе дисциплины
хранят маршрут одинаково: текст "F1.2 -> F1.3 -> F1.4" в параметре цепи
«Маршрут цепи» (scs_circuits.parse_route_path), адреса ссылаются на
отдельные элементы узлов маршрута/стояков (ADDR_PARAM). СПС (шлейфы)
устроена иначе — маршрут там список рёбер между самими устройствами, а не
через отдельные узлы-маркеры — и использует эти хелперы только для
пикинга цепи и отрисовки/выделения, разбирает свой текст маршрута сама
(см. SPS.panel/ShowCircuitRoute, fire_alarm_loops.parse_route_edges).
"""

import time

from Autodesk.Revit.DB import BuiltInCategory, BuiltInParameter, ElementId, Line, Transaction
from Autodesk.Revit.DB import FilteredElementCollector
from Autodesk.Revit.UI.Selection import ObjectType
from Autodesk.Revit.Exceptions import OperationCanceledException
from System.Collections.Generic import List

from pyrevit import forms

from lowlife.params import get_string_param

# Сколько секунд держать линию предпросмотра маршрута на виде, прежде чем
# она удалит себя сама (см. schedule_preview_cleanup) — достаточно, чтобы
# рассмотреть маршрут, но не настолько долго, чтобы линия успела помешать
# следующему действию в модели.
DEFAULT_PREVIEW_LIFETIME_SECONDS = 6.0

# Метка во встроенном параметре "Комментарии" временных линий, которые
# рисует эта кнопка — BuiltInParameter, а не имя параметра текстом, чтобы
# поиск/удаление прошлых линий не зависел от языка интерфейса Revit.
# Общая для всех дисциплин: одна кнопка (независимо от того, СКС это,
# СКУД или СПС) должна убирать за собой линии, оставленные любой другой,
# иначе на одном виде могут накапливаться "хвосты" от разных дисциплин.
MARKER_TEXT = u"LowLife_RoutePreview"


def find_old_preview_line_ids(doc, view):
    """ElementId всех временных линий предпросмотра маршрута на активном виде (см. MARKER_TEXT)."""
    ids = []
    collector = FilteredElementCollector(doc, view.Id) \
        .OfCategory(BuiltInCategory.OST_Lines) \
        .WhereElementIsNotElementType()

    for e in collector:
        try:
            p = e.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
            if p and p.HasValue and p.AsString() == MARKER_TEXT:
                ids.append(e.Id)
        except:
            continue

    return ids


def pick_circuit(uidoc, doc, prompt, circuit_panel_param):
    """
    Просит выбрать элемент, входящий в интересующую электрическую цепь.
    Если у элемента несколько цепей — предлагает выбрать нужную из списка
    (подписанного панелью + именем + ID, чтобы отличить их друг от друга).

    Возвращает (picked_element, circuit) — circuit is None и скрипт уже
    остановлен через forms.alert(exitscript=True), если у элемента нет
    цепей или пользователь отменил выбор.
    """
    try:
        ref = uidoc.Selection.PickObject(ObjectType.Element, prompt)
    except OperationCanceledException:
        forms.alert(u"Операция отменена.", exitscript=True)
        return None, None

    picked = doc.GetElement(ref)

    mep_model = getattr(picked, "MEPModel", None)
    systems = []
    if mep_model is not None:
        try:
            systems = list(mep_model.GetElectricalSystems())
        except:
            systems = []

    if not systems:
        forms.alert(
            u"У выбранного элемента нет электрических цепей (или это не "
            u"устройство, а, например, узел маршрута/панель). Выберите "
            u"устройство, подключённое к нужной цепи.",
            exitscript=True
        )
        return picked, None

    if len(systems) == 1:
        return picked, systems[0]

    labels = []
    by_label = {}
    for s in systems:
        label = u"{} — {} (ID {})".format(
            get_string_param(s, circuit_panel_param) or u"без панели",
            (s.Name or u"?"),
            s.Id.IntegerValue
        )
        labels.append(label)
        by_label[label] = s

    selected_label = forms.SelectFromList.show(
        labels,
        title=u"У устройства несколько цепей — выберите нужную",
        button_name=u"Показать",
        multiselect=False
    )
    if not selected_label:
        forms.alert(u"Операция отменена.", exitscript=True)
        return picked, None

    return picked, by_label[selected_label]


def create_route_line_segments(doc, view, segments):
    """
    Удаляет прошлые временные линии предпросмотра на активном виде и
    строит новые — по одному отрезку Detail Line на каждую пару (p1, p2)
    из segments (не обязательно связную цепочку — например у СПС маршрут
    шлейфа это дерево из отдельных рёбер родитель->устройство, а не один
    непрерывный путь). Пары с None или совпадающими точками пропускаются.
    Вызывать внутри revit.Transaction. Возвращает список ElementId
    созданных линий.
    """
    old_ids = find_old_preview_line_ids(doc, view)
    if old_ids:
        ids_to_delete = List[ElementId]()
        for eid in old_ids:
            ids_to_delete.Add(eid)
        try:
            doc.Delete(ids_to_delete)
        except:
            pass

    created_ids = []

    for p1, p2 in segments:
        if p1 is None or p2 is None:
            continue
        try:
            line = Line.CreateBound(p1, p2)
        except:
            continue
        try:
            curve_el = doc.Create.NewDetailCurve(view, line)
        except:
            continue

        try:
            p = curve_el.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
            if p and not p.IsReadOnly:
                p.Set(MARKER_TEXT)
        except:
            pass

        created_ids.append(curve_el.Id)

    return created_ids


def create_route_lines(doc, view, points):
    """
    Удаляет прошлые временные линии предпросмотра на активном виде и
    строит новые — по одному отрезку Detail Line между каждой соседней
    парой points (обычно устройство -> узлы/стояки -> панель, единая
    связная цепочка — см. create_route_line_segments для несвязного
    дерева рёбер). Вызывать внутри revit.Transaction. Возвращает список
    ElementId созданных линий.
    """
    return create_route_line_segments(doc, view, zip(points, points[1:]))


def select_elements(uidoc, elements, extra_ids=None):
    """Выделяет elements (список Element) и extra_ids (список ElementId, например созданных линий) в модели."""
    selection_ids = List[ElementId]()
    for el in elements:
        selection_ids.Add(el.Id)
    for eid in (extra_ids or []):
        selection_ids.Add(eid)

    try:
        uidoc.Selection.SetElementIds(selection_ids)
    except:
        pass


def schedule_preview_cleanup(uiapp, doc, created_ids, delay_seconds=DEFAULT_PREVIEW_LIFETIME_SECONDS):
    """
    Планирует самоудаление временных линий предпросмотра маршрута — Revit
    не умеет рисовать по-настоящему "временную", ничего не сохраняющую в
    документе графику для произвольного набора точек (в отличие от
    подсветки уже существующих элементов через OverrideGraphicSettings,
    здесь линии — это реальные DetailCurve, их всё равно нужно явно
    удалять). Вместо блокирующего ожидания подписывается на
    UIApplication.Idling — это событие Revit сам вызывает в перерывах
    между действиями пользователя, и как раз в этот момент безопасно
    менять документ. Пока не пройдёт delay_seconds (отсчёт стартует по
    факту — Idling не срабатывает, пока открыт модальный диалог), каждый
    тик просто выходит и ждёт следующего; как только время вышло — удаляет
    ИМЕННО эти created_ids (а не "текущие помеченные линии на виде" — если
    кнопку успели запустить повторно, старый предпросмотр к этому моменту
    уже мог быть удалён и заменён новым явным вызовом
    create_route_line(s), и трогать его нельзя) и отписывается.

    Не гарантирует удаление на 100% (документ/Revit может закрыться раньше
    delay_seconds) — это просто "лучшее, что можно сделать" без хрупких
    фоновых потоков; на случай пропуска остаётся штатная подстраховка:
    следующий запуск любой из кнопок «Маршрут цепи» всё равно подчищает
    прошлые линии по MARKER_TEXT (см. create_route_line_segments).
    """
    ids_snapshot = list(created_ids)
    if not ids_snapshot:
        return

    deadline = time.time() + delay_seconds

    def _on_idling(sender, args):
        if time.time() < deadline:
            return

        try:
            to_delete = List[ElementId]()
            for eid in ids_snapshot:
                try:
                    if doc.GetElement(eid) is not None:
                        to_delete.Add(eid)
                except:
                    pass

            if to_delete.Count > 0:
                t = Transaction(doc, u"Убрать временный маршрут цепи")
                t.Start()
                try:
                    doc.Delete(to_delete)
                    t.Commit()
                except:
                    t.RollBack()
        except:
            pass
        finally:
            try:
                sender.Idling -= _on_idling
            except:
                pass

    uiapp.Idling += _on_idling
