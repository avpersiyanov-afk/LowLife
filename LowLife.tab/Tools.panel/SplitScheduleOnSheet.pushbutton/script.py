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

# Зазор между участками при раскладке в ряд
GAP_MM = 5.0

# Ширина раскладки, если ширину участка измерить не удалось
FALLBACK_STEP_MM = 300.0

# Разумный предел, чтобы опечатка не наплодила сотни участков
MAX_SEGMENTS = 60


class Cancelled(Exception):
    u"""Пользователь отменил операцию — не показываем трейсбек."""
    pass


class Stop(Exception):
    u"""Понятное сообщение вместо трейсбека."""
    pass


def get_target_schedule():
    u"""
    (ViewSchedule, экземпляр на листе или None, число разных выбранных спек).
    """
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


def is_num(x):
    return x is not None and not math.isinf(x) and not math.isnan(x)


def ask(prompt, default):
    u"""Простой ввод строки. Пустой ответ = отмена."""
    answer = Interaction.InputBox(prompt, u"Разбить спецификацию", unicode(default))
    if answer is None or not answer.strip():
        raise Cancelled()
    return answer


def parse_request(raw):
    u"""
    ('count', N)  — разбить на N равных участков;
    ('mm', высота_участка_в_футах) — разбить по высоте участка.
    Ввод: просто число — число участков; число с «мм» — высота участка.
    """
    raw = raw.strip().lower().replace(",", ".")

    is_mm = False
    for suffix in (u"мм", u"mm", u"м"):
        if raw.endswith(suffix):
            raw = raw[:-len(suffix)].strip()
            is_mm = True
            break

    try:
        value = float(raw)
    except ValueError:
        raise Stop(u"Не понял ввод: «{}».".format(raw))

    if value <= 0:
        raise Stop(u"Значение должно быть больше нуля.")

    if is_mm:
        return "mm", value / MM_IN_FOOT

    count = int(round(value))
    if count < 2:
        raise Stop(u"Участков должно быть хотя бы 2.")
    if count > MAX_SEGMENTS:
        raise Stop(u"{} участков — слишком много.".format(count))
    return "count", count


def merge_back(sched):
    u"""Собрать разбитую спеку обратно в одну, независимо от сигнатуры
    MergeSegments в конкретной сборке Revit."""
    guard = 0
    while sched.GetSegmentCount() > 1 and guard < MAX_SEGMENTS:
        before = sched.GetSegmentCount()
        try:
            sched.MergeSegments()
        except TypeError:
            sched.MergeSegments(0)
        if sched.GetSegmentCount() >= before:
            break
        guard += 1


def measure_total_height_ft(sched):
    u"""
    Полная высота тела спецификации в футах. Меряем «пробой»: делим на 2
    равные части, читаем предел первой (= половина полной высоты), собираем
    обратно. GetSegmentHeight у неразбитой спеки возвращает бесконечность,
    габарит экземпляра на листе врёт — поэтому так.
    """
    try:
        sched.Split(2)
        doc.Regenerate()
        half = sched.GetSegmentHeight(0)
        merge_back(sched)
        doc.Regenerate()
        if is_num(half) and half > 0:
            return 2.0 * half
    except Exception:
        try:
            merge_back(sched)
            doc.Regenerate()
        except Exception:
            pass
    return 0.0


def collect_on_sheet(sched, sheet_id):
    u"""{SegmentIndex: instance} + [Id дублей] для спеки на листе."""
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
    u"""Ширина участка — максимум по габаритам размещённых сегментов."""
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
    u"""Разложить участки слева направо от origin. Дубли/лишние удалить,
    недостающие создать, имеющиеся передвинуть."""
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
            except Exception:
                pass
            continue
        try:
            delta = target - inst.Point
            if delta.GetLength() > 1e-7:
                ElementTransformUtils.MoveElement(doc, inst.Id, delta)
                moved += 1
        except Exception:
            pass

    return created, moved, removed, width_ft * MM_IN_FOOT


def main():
    sched, sched_inst, distinct = get_target_schedule()

    if sched is None:
        raise Stop(
            u"Сначала выберите на листе спецификацию (или саму спецификацию "
            u"в диспетчере проекта), потом запустите кнопку."
        )
    if distinct > 1:
        raise Stop(u"Выбрано несколько разных спецификаций. Оставьте одну.")
    if getattr(sched, "IsTitleblockRevisionSchedule", False):
        raise Stop(u"Спецификацию изменений в штампе разбить нельзя.")
    if sched_inst is None:
        raise Stop(
            u"Выберите экземпляр спецификации на листе (щёлкните по самой "
            u"таблице на листе), а не спецификацию в диспетчере проекта."
        )

    try:
        already_split = sched.IsSplit()
    except AttributeError:
        raise Stop(
            u"Эта сборка Revit не поддерживает разбиение спецификаций через API."
        )

    if already_split:
        go = forms.alert(
            u"Спецификация уже разбита на {} участков. Её нужно сначала "
            u"собрать обратно в одну.\n\nСобрать и разбить заново?".format(
                sched.GetSegmentCount()
            ),
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
        if already_split:
            merge_back(sched)
            if sched.GetSegmentCount() > 1:
                raise Stop(
                    u"Не удалось собрать спецификацию обратно в одну. "
                    u"Соберите участки вручную и повторите."
                )
            doc.Regenerate()

        if mode == "mm":
            total_ft = measure_total_height_ft(sched)
            if total_ft <= 0:
                raise Stop(
                    u"Не удалось измерить высоту спецификации. Задайте число "
                    u"участков вместо высоты."
                )
            count = int(math.ceil(total_ft / amount - 1e-9))
            count = max(count, 2)
            if count > MAX_SEGMENTS:
                raise Stop(
                    u"Получается {} участков — слишком много. Увеличьте "
                    u"высоту участка.".format(count)
                )
            heights = List[float]()
            for _ in range(count - 1):
                heights.Add(amount)
            sched.Split(heights)
            seg_mm = amount * MM_IN_FOOT
            total_mm = total_ft * MM_IN_FOOT
        else:
            count = amount
            sched.Split(count)
            seg_mm = None
            total_mm = 0.0

        doc.Regenerate()
        created, moved, removed, width_mm = arrange_in_row(
            sched, sheet_id, origin, count
        )

    final = sched.GetSegmentCount()

    lines = [u"Готово.", u"", u"Участков: {}".format(final)]
    if seg_mm is not None:
        lines.append(u"Высота участка: {:.0f} мм".format(seg_mm))
        lines.append(u"Измеренная высота всей спеки: {:.0f} мм".format(total_mm))
    lines.append(
        u"Раскладка: создано {}, передвинуто {}, удалено лишних {}".format(
            created, moved, removed
        )
    )
    lines.append(u"Ширина участка для раскладки: {:.0f} мм".format(width_mm))
    forms.alert(u"\n".join(lines))


try:
    main()
except Cancelled:
    pass
except Stop as ex:
    forms.alert(unicode(ex))
except Exception:
    forms.alert(
        u"Сбой при разбиении спецификации:\n\n{}".format(traceback.format_exc()),
        title=u"Разбить спецификацию"
    )
