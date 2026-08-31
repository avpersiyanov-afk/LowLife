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

# Разумный предел, чтобы опечатка в высоте не наплодила сотни участков
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
    же спеки не считается ошибкой.
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


def total_body_height_ft(sched, inst):
    u"""
    Высота спецификации в футах. Сначала по API сегментов, а если он на
    неразбитой спеке молчит — по габариту размещённого на листе экземпляра.
    """
    try:
        h = sched.GetSegmentHeight(0)
        if h and h > 0:
            return h
    except Exception:
        pass

    if inst is not None:
        sheet = doc.GetElement(inst.OwnerViewId)
        bbox = inst.get_BoundingBox(sheet)
        if bbox is not None:
            return bbox.Max.Y - bbox.Min.Y

    return 0.0


def ask(prompt, default):
    u"""Простой ввод строки. Пустой ответ = отмена."""
    answer = Interaction.InputBox(prompt, u"Разбить спецификацию", unicode(default))
    if answer is None or not answer.strip():
        raise Cancelled()
    return answer


def parse_request(raw, total_ft):
    u"""
    По вводу пользователя возвращает (список высот сегментов кроме последнего
    в футах, высота участка в мм для отчёта).
    Ввод: число мм — высота участка; число со знаком x/х/* — число участков.
    """
    raw = raw.strip().lower().replace(",", ".")

    is_count = False
    for suffix in (u"x", u"х", u"*"):
        if raw.endswith(suffix):
            raw = raw[:-len(suffix)].strip()
            is_count = True
            break

    try:
        value = float(raw)
    except ValueError:
        raise Stop(u"Не понял ввод: «{}».".format(raw))

    if value <= 0:
        raise Stop(u"Значение должно быть больше нуля.")

    if is_count:
        count = int(round(value))
        if count < 2:
            raise Stop(u"Участков должно быть хотя бы 2.")
        seg_ft = total_ft / count
    else:
        seg_ft = value / MM_IN_FOOT
        count = int(math.ceil(total_ft / seg_ft - 1e-9))
        count = max(count, 2)

    if count > MAX_SEGMENTS:
        raise Stop(
            u"Получается {} участков — слишком много. "
            u"Увеличьте высоту участка.".format(count)
        )

    return [seg_ft] * (count - 1), seg_ft * MM_IN_FOOT


def merge_back(sched):
    u"""Собрать разбитую спеку обратно в одну. Сигнатура MergeSegments в
    разных сборках Revit отличается, поэтому пробуем оба варианта."""
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

    total_ft = total_body_height_ft(sched, sched_inst)
    if total_ft <= 0:
        raise Stop(
            u"Не удалось определить высоту спецификации. Убедитесь, что она "
            u"размещена на листе."
        )

    total_mm = total_ft * MM_IN_FOOT

    raw = ask(
        u"Высота одного участка в мм.\n"
        u"Либо число участков со знаком x (например  4x).\n\n"
        u"Сейчас вся спецификация — {:.0f} мм.".format(total_mm),
        int(round(total_mm / 2.0))
    )

    seg_heights_ft, seg_height_mm = parse_request(raw, total_ft)

    heights = List[float]()
    for h in seg_heights_ft:
        heights.Add(h)

    with revit.Transaction(u"Разбить спецификацию на листе"):
        if already_split:
            merge_back(sched)
            if sched.GetSegmentCount() > 1:
                raise Stop(
                    u"Не удалось собрать спецификацию обратно в одну. "
                    u"Соберите участки вручную (перетаскиванием) и повторите."
                )
        sched.Split(heights)

    forms.alert(
        u"Готово.\n\n"
        u"Участков: {}\n"
        u"Высота участка: {:.0f} мм\n\n"
        u"Взаимное расположение участков на листе поправьте "
        u"перетаскиванием.".format(sched.GetSegmentCount(), seg_height_mm)
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
