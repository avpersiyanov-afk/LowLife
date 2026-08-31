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
    Спека берётся из выбранного на листе экземпляра спецификации или из
    напрямую выбранной спецификации; выбор нескольких сегментов одной и той
    же спеки ошибкой не считается.
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


def instance_size_ft(inst):
    u"""
    (ширина, высота) экземпляра спецификации на листе в футах, либо (0, 0).
    GetSegmentHeight здесь бесполезен: у неразбитой спеки он даёт бесконечность.
    """
    if inst is None:
        return 0.0, 0.0

    sheet = doc.GetElement(inst.OwnerViewId)
    try:
        bbox = inst.get_BoundingBox(sheet)
    except Exception:
        bbox = None

    if bbox is None:
        return 0.0, 0.0

    w = bbox.Max.X - bbox.Min.X
    h = bbox.Max.Y - bbox.Min.Y
    if math.isinf(w) or math.isnan(w) or w <= 0:
        w = 0.0
    if math.isinf(h) or math.isnan(h) or h <= 0:
        h = 0.0
    return w, h


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
    u"""Собрать разбитую спеку обратно в одну. Сигнатура MergeSegments в
    разных сборках Revit отличается — пробуем оба варианта."""
    try:
        sched.MergeSegments()
    except TypeError:
        guard = 0
        while sched.GetSegmentCount() > 1 and guard < MAX_SEGMENTS:
            sched.MergeSegments(0)
            guard += 1


def arrange_in_row(sched, sheet_id, origin, width_ft, count):
    u"""
    Разложить участки спеки на листе sheet_id в один ряд слева направо от
    origin. Недостающие создаём, лишние по месту двигаем.
    Возвращает (создано, передвинуто).
    """
    doc.Regenerate()

    by_seg = {}
    for inst in FilteredElementCollector(doc).OfClass(ScheduleSheetInstance):
        if inst.ScheduleId.IntegerValue != sched.Id.IntegerValue:
            continue
        if inst.OwnerViewId.IntegerValue != sheet_id.IntegerValue:
            continue
        by_seg[inst.SegmentIndex] = inst

    step = width_ft + GAP_MM / MM_IN_FOOT
    created = 0
    moved = 0

    for k in range(count):
        target = XYZ(origin.X + step * k, origin.Y, origin.Z)
        inst = by_seg.get(k)

        if inst is None:
            ScheduleSheetInstance.Create(doc, sheet_id, sched.Id, target, k)
            created += 1
            continue

        try:
            delta = target - inst.Point
            if delta.GetLength() > 1e-7:
                ElementTransformUtils.MoveElement(doc, inst.Id, delta)
                moved += 1
        except Exception:
            pass

    return created, moved


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
            u"таблице на листе), а не спецификацию в диспетчере проекта — "
            u"иначе некуда раскладывать участки."
        )

    try:
        already_split = sched.IsSplit()
    except AttributeError:
        raise Stop(
            u"Эта сборка Revit не поддерживает разбиение спецификаций через API."
        )

    if already_split:
        go = forms.alert(
            u"Спецификация уже разбита на {} участков. Revit умеет делить "
            u"спеку только один раз, поэтому её нужно сначала собрать обратно "
            u"в одну.\n\nСобрать сейчас и разбить заново?".format(
                sched.GetSegmentCount()
            ),
            yes=True, no=True
        )
        if not go:
            raise Cancelled()

    _, hint_h = instance_size_ft(sched_inst)
    if hint_h > 0 and not already_split:
        size_line = u"Высота всей спецификации на листе — {:.0f} мм.".format(
            hint_h * MM_IN_FOOT
        )
    else:
        size_line = u"Число участков — просто число."

    raw = ask(
        u"На сколько участков разбить спецификацию? (например  3)\n"
        u"Либо высота одного участка: число с «мм» (например  180мм).\n\n"
        + size_line,
        3
    )
    mode, amount = parse_request(raw)

    sheet_id = sched_inst.OwnerViewId

    with revit.Transaction(u"Разбить спецификацию на листе"):
        if already_split:
            merge_back(sched)
            if sched.GetSegmentCount() > 1:
                raise Stop(
                    u"Не удалось собрать спецификацию обратно в одну. "
                    u"Соберите участки вручную (перетаскиванием) и повторите."
                )
            doc.Regenerate()

        # Замер после возможной сборки — тут спека точно цельная
        width_ft, total_ft = instance_size_ft(sched_inst)
        origin = sched_inst.Point

        if mode == "mm":
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
        else:
            count = amount
            sched.Split(count)
            seg_mm = None

        if width_ft <= 0:
            width_ft = 0.0  # раскладка вплотную, если ширину не измерили

        created, moved = arrange_in_row(
            sched, sheet_id, origin, width_ft, count
        )

    final = sched.GetSegmentCount()
    tail = u""
    if seg_mm is not None:
        tail = u"\nВысота участка: {:.0f} мм".format(seg_mm)

    forms.alert(
        u"Готово.\n\nУчастков: {}{}\nРазложено в ряд на листе: {} "
        u"(создано {}, передвинуто {}).".format(
            final, tail, created + moved, created, moved
        )
    )


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
