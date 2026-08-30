# -*- coding: utf-8 -*-

__title__ = u"Разбить\nспецификацию"
__doc__ = u"Разбивает выбранную спецификацию на листе на участки заданной высоты"
__author__ = "Pipers"

import math

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import ScheduleSheetInstance
from pyrevit import revit, forms


doc = revit.doc
uidoc = revit.uidoc

MM_IN_FOOT = 304.8

# Разумный предел, чтобы опечатка в высоте не наплодила сотни участков
MAX_SEGMENTS = 60


def get_selected_schedule_instance():
    u"""Единственный ScheduleSheetInstance среди выбранных элементов."""
    found = []

    for el_id in uidoc.Selection.GetElementIds():
        el = doc.GetElement(el_id)
        if isinstance(el, ScheduleSheetInstance):
            found.append(el)

    return found


def total_height_ft(inst):
    u"""Суммарная высота содержимого по всем текущим участкам, в футах."""
    return sum(
        inst.GetSegmentHeight(i) for i in range(inst.SegmentCount)
    )


def ask_float_mm(prompt, default):
    u"""Спросить число в мм, вернуть футы. None — отмена."""
    raw = forms.ask_for_string(
        default=str(default),
        prompt=prompt,
        title=u"Разбить спецификацию"
    )

    if raw is None:
        return None

    raw = raw.strip().replace(",", ".")

    try:
        value_mm = float(raw)
    except ValueError:
        forms.alert(u"Не число: «{}».".format(raw), exitscript=True)

    if value_mm <= 0:
        forms.alert(u"Значение должно быть больше нуля.", exitscript=True)

    return value_mm / MM_IN_FOOT


def split_to_count(inst, target_count, gap_ft):
    u"""Довести число участков до target_count, деля каждый раз самый высокий."""
    while inst.SegmentCount < target_count:
        heights = [inst.GetSegmentHeight(i) for i in range(inst.SegmentCount)]
        tallest = heights.index(max(heights))
        inst.Split(tallest, gap_ft)


def apply_heights(inst, target_ft):
    u"""
    Задать всем участкам, кроме последнего, высоту target_ft.
    Последний подстраивается под остаток автоматически.
    Возвращает список номеров участков, которым высоту задать не удалось.
    """
    failed = []
    count = inst.SegmentCount

    for i in range(count - 1):
        try:
            if inst.CanSetSegmentHeight(i, target_ft):
                inst.SetSegmentHeight(i, target_ft)
            else:
                failed.append(i + 1)
        except Exception:
            failed.append(i + 1)

    return failed


# ------------------------------------------------------------
# ОСНОВНОЙ КОД
# ------------------------------------------------------------

instances = get_selected_schedule_instance()

if not instances:
    forms.alert(
        u"Сначала выберите на листе одну спецификацию, потом запустите кнопку.",
        exitscript=True
    )

if len(instances) > 1:
    forms.alert(
        u"Выбрано несколько спецификаций. Оставьте одну.",
        exitscript=True
    )

inst = instances[0]

if getattr(inst, "IsTitleblockRevisionSchedule", False):
    forms.alert(
        u"Это спецификация изменений в штампе — её разбить нельзя.",
        exitscript=True
    )

try:
    start_count = inst.SegmentCount
except AttributeError:
    forms.alert(
        u"Эта версия Revit не поддерживает программное разбиение спецификаций "
        u"(нужен Revit 2022 или новее).",
        exitscript=True
    )

total_ft = total_height_ft(inst)
total_mm = total_ft * MM_IN_FOOT

target_ft = ask_float_mm(
    u"Высота одного участка спецификации, мм\n"
    u"(вся спецификация сейчас — {:.0f} мм)".format(total_mm),
    default=int(round(total_mm / 2.0))
)

if target_ft is None:
    forms.alert(u"Операция отменена.", exitscript=True)

gap_ft = ask_float_mm(
    u"Зазор между участками, мм",
    default=8
)

if gap_ft is None:
    forms.alert(u"Операция отменена.", exitscript=True)

# Сколько участков нужно, чтобы каждый (кроме последнего) был не выше заданного
needed = int(math.ceil(total_ft / target_ft - 1e-9))
needed = max(needed, 1)

if needed > MAX_SEGMENTS:
    forms.alert(
        u"Получается {} участков — слишком много. "
        u"Увеличьте высоту участка.".format(needed),
        exitscript=True
    )

if start_count > 1 and needed <= start_count:
    forms.alert(
        u"Спецификация уже разбита на {} участков, а для заданной высоты "
        u"хватило бы {}. Объединить участки обратно из скрипта нельзя — "
        u"сначала соберите спецификацию в одну (перетащите ручки вручную), "
        u"потом запустите кнопку снова.".format(start_count, needed),
        exitscript=True
    )

failed = []

with revit.Transaction(u"Разбить спецификацию на листе"):
    split_to_count(inst, needed, gap_ft)
    failed = apply_heights(inst, target_ft)

final_count = inst.SegmentCount

msg = (
    u"Готово.\n\n"
    u"Участков: {}\n"
    u"Высота участка: {:.0f} мм\n"
    u"Зазор: {:.0f} мм"
).format(final_count, target_ft * MM_IN_FOOT, gap_ft * MM_IN_FOOT)

if failed:
    msg += (
        u"\n\nНе удалось задать высоту участкам: {}\n"
        u"Скорее всего, заданная высота меньше шапки с одной строкой."
    ).format(u", ".join(str(n) for n in failed))

forms.alert(msg)
