# -*- coding: utf-8 -*-

__title__ = u"Разбить\nспецификацию"
__doc__ = u"Разбивает выбранную спецификацию на листе на участки заданной высоты"
__author__ = "Pipers"

import math
import traceback

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
clr.AddReference('Microsoft.VisualBasic')

from System.Collections.Generic import List
from Microsoft.VisualBasic import Interaction
from Autodesk.Revit.DB import ScheduleSheetInstance, ViewSchedule
from pyrevit import revit, forms


doc = revit.doc
uidoc = revit.uidoc

MM_IN_FOOT = 304.8

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


def placed_height_ft(inst):
    u"""
    Высота размещённого на листе экземпляра спецификации, в футах.
    0.0 — если измерить не удалось (например, выбрана сама спека, а не её
    экземпляр на листе). GetSegmentHeight здесь бесполезен: у неразбитой
    спеки он возвращает бесконечность.
    """
    if inst is None:
        return 0.0

    sheet = doc.GetElement(inst.OwnerViewId)
    try:
        bbox = inst.get_BoundingBox(sheet)
    except Exception:
        bbox = None

    if bbox is None:
        return 0.0

    h = bbox.Max.Y - bbox.Min.Y
    if math.isinf(h) or math.isnan(h) or h <= 0:
        return 0.0
    return h


def ask(prompt, default):
    u"""Простой ввод строки. Пустой ответ = отмена."""
    answer = Interaction.InputBox(prompt, u"Разбить спецификацию", unicode(default))
    if answer is None or not answer.strip():
        raise Cancelled()
    return answer


def parse_request(raw, total_ft):
    u"""
    Возвращает ('count', None, N)  — разбить на N равных участков, либо
             ('heights', [высоты кроме последнего в футах], N) — по высоте.
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
        if total_ft <= 0:
            raise Stop(
                u"Не удалось измерить высоту спецификации на листе. "
                u"Задайте вместо этого число участков — просто число."
            )
        seg_ft = value / MM_IN_FOOT
        count = int(math.ceil(total_ft / seg_ft - 1e-9))
        count = max(count, 2)
        if count > MAX_SEGMENTS:
            raise Stop(
                u"Получается {} участков — слишком много. "
                u"Увеличьте высоту участка.".format(count)
            )
        return "heights", [seg_ft] * (count - 1), count

    count = int(round(value))
    if count < 2:
        raise Stop(u"Участков должно быть хотя бы 2.")
    if count > MAX_SEGMENTS:
        raise Stop(u"{} участков — слишком много.".format(count))
    return "count", None, count


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

    total_ft = placed_height_ft(sched_inst)
    total_mm = total_ft * MM_IN_FOOT

    if total_ft > 0:
        size_line = u"Высота всей спецификации на листе — {:.0f} мм.".format(
            total_mm
        )
    else:
        size_line = u"Высоту спецификации измерить не удалось — задайте число участков."

    raw = ask(
        u"На сколько участков разбить спецификацию? (например  3)\n"
        u"Либо высота одного участка: число с «мм» (например  180мм).\n\n"
        + size_line,
        3
    )

    mode, heights_list, count = parse_request(raw, total_ft)

    with revit.Transaction(u"Разбить спецификацию на листе"):
        if already_split:
            merge_back(sched)
            if sched.GetSegmentCount() > 1:
                raise Stop(
                    u"Не удалось собрать спецификацию обратно в одну. "
                    u"Соберите участки вручную (перетаскиванием) и повторите."
                )

        if mode == "count":
            sched.Split(count)
        else:
            heights = List[float]()
            for h in heights_list:
                heights.Add(h)
            sched.Split(heights)

    final = sched.GetSegmentCount()
    tail = u""
    if mode == "heights":
        tail = u"\nВысота участка: {:.0f} мм".format(heights_list[0] * MM_IN_FOOT)

    forms.alert(
        u"Готово.\n\nУчастков: {}{}\n\n"
        u"Взаимное расположение участков на листе поправьте "
        u"перетаскиванием.".format(final, tail)
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
