# -*- coding: utf-8 -*-

__title__ = u"Разбить\nспецификацию"
__doc__ = u"Разбивает выбранную спецификацию на листе на участки и раскладывает их в ряд"
__author__ = "Pipers"

import math
import traceback

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
clr.AddReference('Microsoft.VisualBasic')

from System.Collections.Generic import List
from Microsoft.VisualBasic import Interaction
from Autodesk.Revit.DB import (
    ElementTransformUtils,
    FilteredElementCollector,
    ScheduleSheetInstance,
    ViewSchedule,
    XYZ,
)
from pyrevit import revit, forms


doc = revit.doc
uidoc = revit.uidoc

MM_IN_FOOT = 304.8

GAP_MM = 5.0
FALLBACK_STEP_MM = 300.0
MAX_SEGMENTS = 60

# Диагностика — показывается в итоговом окне и в сообщениях об ошибке
_debug = []


class Cancelled(Exception):
    pass


class Stop(Exception):
    pass


def dbg(msg):
    _debug.append(unicode(msg))


def is_num(x):
    return x is not None and not math.isinf(x) and not math.isnan(x)


def get_target_schedule():
    schedule_ids = set()
    picked = None
    picked_inst = None

    for el_id in uidoc.Selection.GetElementIds():
        el = doc.GetElement(el_id)
        if isinstance(el, ScheduleSheetInstance):
            sched = doc.GetElement(el.ScheduleId)
            if isinstance(sched, ViewSchedule):
                schedule_ids.add(sched.Id.IntegerValue)
                picked = sched
                picked_inst = el
        elif isinstance(el, ViewSchedule):
            schedule_ids.add(el.Id.IntegerValue)
            picked = el

    return picked, picked_inst, len(schedule_ids)


def ask(prompt, default):
    answer = Interaction.InputBox(prompt, u"Разбить спецификацию", unicode(default))
    if answer is None or not answer.strip():
        raise Cancelled()
    return answer


def to_float_mm(raw):
    raw = raw.strip().lower().replace(",", ".")
    for suffix in (u"мм", u"mm", u"м"):
        if raw.endswith(suffix):
            raw = raw[:-len(suffix)].strip()
            break
    try:
        v = float(raw)
    except ValueError:
        raise Stop(u"Не понял число: «{}».".format(raw))
    if v <= 0:
        raise Stop(u"Значение должно быть больше нуля.")
    return v


def parse_request(raw):
    u"""('count', N) — N равных участков; ('mm', высота_фт) — по высоте."""
    low = raw.strip().lower()
    is_mm = any(low.endswith(s) for s in (u"мм", u"mm", u"м"))
    value_mm = to_float_mm(raw)

    if is_mm:
        return "mm", value_mm / MM_IN_FOOT

    count = int(round(value_mm))
    if count < 2:
        raise Stop(u"Участков должно быть хотя бы 2.")
    if count > MAX_SEGMENTS:
        raise Stop(u"{} участков — слишком много.".format(count))
    return "count", count


def merge_back(sched):
    u"""Собрать разбитую спеку в одну, не завися от сигнатуры MergeSegments."""
    guard = 0
    while sched.GetSegmentCount() > 1 and guard < MAX_SEGMENTS:
        before = sched.GetSegmentCount()
        try:
            sched.MergeSegments()
        except Exception:
            try:
                sched.MergeSegments(0)
            except Exception as ex:
                dbg(u"merge_back не смог: {}".format(ex))
                return
        if sched.GetSegmentCount() >= before:
            dbg(u"merge_back застрял на {} сегм.".format(sched.GetSegmentCount()))
            return
        guard += 1


def measure_total_height_ft(sched):
    u"""
    Полная высота тела спеки в футах, 0.0 если не вышло. Пробой: делим на 2
    равные части, предел первой = половина полной высоты, собираем обратно.
    Замер не теряем, даже если сборка обратно сбойнёт.
    """
    result = 0.0
    try:
        sched.Split(2)
        doc.Regenerate()
        h0 = sched.GetSegmentHeight(0)
        dbg(u"проба Split(2): GetSegmentHeight(0) = {}".format(h0))
        if is_num(h0) and h0 > 0:
            result = 2.0 * h0
    except Exception as ex:
        dbg(u"проба Split(2) сбой: {}".format(ex))

    try:
        merge_back(sched)
        doc.Regenerate()
    except Exception as ex:
        dbg(u"merge_back после пробы: {}".format(ex))

    return result


def collect_on_sheet(sched, sheet_id):
    by_seg = {}
    dups = []
    for inst in FilteredElementCollector(doc).OfClass(ScheduleSheetInstance):
        if inst.ScheduleId.IntegerValue != sched.Id.IntegerValue:
            continue
        if inst.OwnerViewId.IntegerValue != sheet_id.IntegerValue:
            continue
        si = inst.SegmentIndex
        if si in by_seg:
            dups.append(inst.Id)
        else:
            by_seg[si] = inst
    return by_seg, dups


def segment_width_ft(sched, sheet_id):
    sheet = doc.GetElement(sheet_id)
    best = 0.0
    for inst in FilteredElementCollector(doc).OfClass(ScheduleSheetInstance):
        if inst.ScheduleId.IntegerValue != sched.Id.IntegerValue:
            continue
        if inst.OwnerViewId.IntegerValue != sheet_id.IntegerValue:
            continue
        try:
            b = inst.get_BoundingBox(sheet)
        except Exception:
            b = None
        if b is None:
            continue
        w = b.Max.X - b.Min.X
        if is_num(w) and w > best:
            best = w
    return best


def arrange_in_row(sched, sheet_id, origin, count):
    doc.Regenerate()

    by_seg, dups = collect_on_sheet(sched, sheet_id)
    kill = list(dups)
    for si in list(by_seg.keys()):
        if si < 0 or si >= count:
            kill.append(by_seg[si].Id)

    removed = 0
    for eid in kill:
        try:
            doc.Delete(eid)
            removed += 1
        except Exception:
            pass
    if removed:
        doc.Regenerate()

    width_ft = segment_width_ft(sched, sheet_id)
    if is_num(width_ft) and width_ft > 0:
        step = width_ft + GAP_MM / MM_IN_FOOT
    else:
        step = FALLBACK_STEP_MM / MM_IN_FOOT

    by_seg, _ = collect_on_sheet(sched, sheet_id)
    created = 0
    moved = 0
    for k in range(count):
        target = XYZ(origin.X + step * k, origin.Y, origin.Z)
        inst = by_seg.get(k)
        if inst is None:
            try:
                ScheduleSheetInstance.Create(doc, sheet_id, sched.Id, target, k)
                created += 1
            except Exception as ex:
                dbg(u"Create сегм.{}: {}".format(k, ex))
            continue
        try:
            delta = target - inst.Point
            if delta.GetLength() > 1e-7:
                ElementTransformUtils.MoveElement(doc, inst.Id, delta)
                moved += 1
        except Exception as ex:
            dbg(u"MoveElement сегм.{}: {}".format(k, ex))

    return created, moved, removed, (width_ft * MM_IN_FOOT if width_ft else 0.0)


def resolve_count(sched, mode, amount):
    u"""Вернуть (count, seg_mm|None, total_mm|0). Меряет/спрашивает высоту."""
    if mode == "count":
        return amount, None, 0.0

    total_ft = measure_total_height_ft(sched)

    if total_ft <= 0:
        raw = ask(
            u"Не смог измерить высоту автоматически.\n"
            u"Введите примерную полную высоту всей спецификации в мм\n"
            u"(посмотрите по листу). Отмена — тогда задайте число участков.",
            2000
        )
        total_ft = to_float_mm(raw) / MM_IN_FOOT
        dbg(u"высота задана вручную: {:.0f} мм".format(total_ft * MM_IN_FOOT))

    count = int(math.ceil(total_ft / amount - 1e-9))
    count = max(count, 2)
    if count > MAX_SEGMENTS:
        raise Stop(
            u"Получается {} участков — слишком много. Увеличьте высоту "
            u"участка.".format(count)
        )
    return count, amount * MM_IN_FOOT, total_ft * MM_IN_FOOT


def main():
    sched, sched_inst, distinct = get_target_schedule()

    if sched is None:
        raise Stop(
            u"Сначала выберите на листе спецификацию, потом запустите кнопку."
        )
    if distinct > 1:
        raise Stop(u"Выбрано несколько разных спецификаций. Оставьте одну.")
    if getattr(sched, "IsTitleblockRevisionSchedule", False):
        raise Stop(u"Спецификацию изменений в штампе разбить нельзя.")
    if sched_inst is None:
        raise Stop(
            u"Выберите экземпляр спецификации на листе (щёлкните по таблице "
            u"на листе), а не спецификацию в диспетчере проекта."
        )

    try:
        already_split = sched.IsSplit()
    except AttributeError:
        raise Stop(
            u"Эта сборка Revit не поддерживает разбиение спецификаций через API."
        )

    if already_split:
        go = forms.alert(
            u"Спецификация уже разбита на {} участков. Собрать обратно "
            u"и разбить заново?".format(sched.GetSegmentCount()),
            yes=True, no=True
        )
        if not go:
            raise Cancelled()

    raw = ask(
        u"На сколько участков разбить спецификацию? (например  3)\n"
        u"Либо высота одного участка: число с «мм» (например  180мм).",
        3
    )
    mode, amount = parse_request(raw)

    sheet_id = sched_inst.OwnerViewId
    origin = sched_inst.Point

    with revit.Transaction(u"Разбить спецификацию на листе"):
        if sched.GetSegmentCount() > 1:
            merge_back(sched)
            doc.Regenerate()
            if sched.GetSegmentCount() > 1:
                raise Stop(
                    u"Не удалось собрать спецификацию обратно в одну "
                    u"(сейчас {} участков). Соберите вручную и повторите.\n\n"
                    u"{}".format(sched.GetSegmentCount(), u"\n".join(_debug))
                )

        count, seg_mm, total_mm = resolve_count(sched, mode, amount)

        if sched.GetSegmentCount() > 1:
            merge_back(sched)
            doc.Regenerate()

        if mode == "mm":
            heights = List[float]()
            for _ in range(count - 1):
                heights.Add(amount)
            sched.Split(heights)
        else:
            sched.Split(count)

        doc.Regenerate()
        created, moved, removed, width_mm = arrange_in_row(
            sched, sheet_id, origin, count
        )

    final = sched.GetSegmentCount()

    lines = [u"Готово.", u"", u"Участков: {}".format(final)]
    if seg_mm is not None:
        lines.append(u"Высота участка: {:.0f} мм".format(seg_mm))
        lines.append(u"Высота всей спеки: {:.0f} мм".format(total_mm))
    lines.append(
        u"Раскладка: создано {}, передвинуто {}, удалено лишних {}".format(
            created, moved, removed
        )
    )
    lines.append(u"Ширина участка: {:.0f} мм".format(width_mm))
    if _debug:
        lines.append(u"")
        lines.append(u"Диагностика:")
        lines.extend(_debug)
    forms.alert(u"\n".join(lines))


try:
    main()
except Cancelled:
    pass
except Stop as ex:
    forms.alert(unicode(ex))
except Exception:
    tail = (u"\n\nДиагностика:\n" + u"\n".join(_debug)) if _debug else u""
    forms.alert(
        u"Сбой при разбиении спецификации:\n\n{}{}".format(
            traceback.format_exc(), tail
        ),
        title=u"Разбить спецификацию"
    )
