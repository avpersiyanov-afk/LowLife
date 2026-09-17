# -*- coding: utf-8 -*-

__title__ = u"Проверка\nпараметров"
__doc__ = (
    u"Диагностика для «Зоны обзора» / «Навести на помещение»: выберите "
    u"одну камеру — кнопка прочитает ВСЕ параметры её экземпляра и типа и "
    u"проверит, какие из них подходят под роли, которые использует расчёт "
    u"зоны обзора (фокусное расстояние, формат матрицы, дальность, высота "
    u"установки, наклон, поворот).\n\n"
    u"Отчёт по каждой роли: задано ли её имя в настройках, найден ли такой "
    u"параметр на камере, подходит ли его тип данных, и какие ещё "
    u"параметры того же типа данных на ней есть — готовые кандидаты, если "
    u"нужный ещё не настроен. Отдельно — категория камеры и правило "
    u"«наклон обязан быть параметром экземпляра».\n\n"
    u"Ничего не пишет в модель и не меняет настройки."
)
__author__ = "Pipers"

from pyrevit import revit, forms, script

from Autodesk.Revit.UI.Selection import ObjectType
from Autodesk.Revit.Exceptions import OperationCanceledException

from lowlife import sot_fov

doc = revit.doc
uidoc = revit.uidoc


_STATUS_RU = {
    u"ok": u"OK",
    u"not_configured": u"— не настроено",
    u"not_found": u"FAIL — не найден на камере",
    u"wrong_kind": u"FAIL — не тот тип данных",
    u"tilt_not_instance": u"FAIL — только на типе (нужен экземпляр)",
    u"empty": u"~ пусто",
}


def _kind_label(kind):
    return sot_fov.PARAM_KIND_RU.get(kind, kind)


def _kinds_label(kinds):
    return u"/".join(_kind_label(k) for k in kinds)


def _entry_label(entry):
    if entry is None:
        return u"—"
    name, kind, level, value_text, has_value = entry
    val = value_text if has_value else u"пусто"
    return u"«{}» ({}, {}) = {}".format(name, _kind_label(kind), level, val)


def _candidates_label(cands, limit=5):
    if not cands:
        return u""
    shown = [u"«{}» ({})".format(c[0], c[2]) for c in cands[:limit]]
    tail = u" …+{}".format(len(cands) - limit) if len(cands) > limit else u""
    return u", ".join(shown) + tail


def _param_rows(params):
    rows = []
    for name, kind, level, value_text, has_value in sorted(params, key=lambda p: p[0].lower()):
        rows.append([name, _kind_label(kind), level, value_text if has_value else u"—"])
    return rows


# --- обычный запуск ------------------------------------------------------
settings = sot_fov.get_settings_silent()

try:
    ref = uidoc.Selection.PickObject(
        ObjectType.Element,
        u"Выберите ОДНУ камеру для проверки параметров её типа"
    )
except OperationCanceledException:
    forms.alert(u"Выбор отменён.", exitscript=True)

el = doc.GetElement(ref.ElementId)
if el is None:
    forms.alert(u"Не удалось получить выбранный элемент.", exitscript=True)

diag = sot_fov.diagnose_camera_params(doc, el, settings)

output = script.get_output()
output.print_md(u"# Проверка параметров камеры — отчёт")

cat_note = u"" if diag["category_ok"] else u"  (⚠ не входит в «Категории камер» из настроек «Зон обзора»)"
print(u"Семейство: {}".format(diag["family_name"] or u"—"))
print(u"Типоразмер: {}".format(diag["type_name"] or u"—"))
print(u"Категория: {}{}".format(diag["category_name"] or u"—", cat_note))

output.print_md(u"---")
output.print_md(u"## Роли параметров («Зоны обзора» / «Навести на помещение»)")
print(u"* — обязательная роль (без неё зона не построится).")

roles_table = []
for role in diag["roles"]:
    label = role["label"] + (u" *" if role["required"] else u"")
    if role["must_be_instance"]:
        label += u" (только экземпляр)"
    roles_table.append([
        label,
        role["configured_name"] or u"—",
        _STATUS_RU.get(role["status"], role["status"]),
        _entry_label(role["found"]),
        _kinds_label(role["expected_kinds"]),
    ])
output.print_table(
    table_data=roles_table,
    columns=[u"Роль", u"Настроено имя", u"Статус", u"Найдено на камере", u"Подходящий тип данных"]
)

need_action = [r for r in diag["roles"] if r["status"] != u"ok"]
if need_action:
    output.print_md(u"### Что делать")
    for role in need_action:
        cands = _candidates_label(role["candidates"])
        if cands:
            print(u"· {}: впишите в настройках одно из имён — {}.".format(role["label"], cands))
        elif role["status"] == u"not_configured" and not role["required"]:
            print(u"· {}: не обязательна, можно оставить пустой.".format(role["label"]))
        else:
            print(
                u"· {}: на камере нет ни одного параметра типа «{}» — "
                u"нужно ДОБАВИТЬ такой параметр в семейство.".format(
                    role["label"], _kinds_label(role["expected_kinds"])
                )
            )

output.print_md(u"---")
output.print_md(u"## Все параметры экземпляра ({})".format(len(diag["instance_params"])))
if diag["instance_params"]:
    output.print_table(
        table_data=_param_rows(diag["instance_params"]),
        columns=[u"Имя", u"Тип данных", u"Уровень", u"Значение"]
    )
else:
    print(u"(нет)")

output.print_md(u"## Все параметры типа ({})".format(len(diag["type_params"])))
if diag["type_params"]:
    output.print_table(
        table_data=_param_rows(diag["type_params"]),
        columns=[u"Имя", u"Тип данных", u"Уровень", u"Значение"]
    )
else:
    print(u"(нет)")
