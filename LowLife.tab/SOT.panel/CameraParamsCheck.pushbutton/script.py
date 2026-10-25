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
    u"Плюс два дополнительных раздела: геометрия и ориентация именно этого "
    u"экземпляра в проекте (откуда берётся направление взгляда, отражение, "
    u"хост, уровень) и разбор самого семейства — открывает его на "
    u"редактирование, читает все типоразмеры и формулы параметров, "
    u"вложенные семейства, тела/вырезы, опорные плоскости, разъёмы — и "
    u"закрывает без сохранения.\n\n"
    u"Ничего не пишет в модель и не меняет настройки."
)
__author__ = "Pipers"

from pyrevit import revit, forms, script
from lowlife.i18n import tr

from Autodesk.Revit.UI.Selection import ObjectType
from Autodesk.Revit.Exceptions import OperationCanceledException

from lowlife import sot_fov

doc = revit.doc
uidoc = revit.uidoc


_STATUS_RU = {
    u"ok": u"OK",
    u"not_configured": tr(u"— не настроено"),
    u"not_found": tr(u"FAIL — не найден на камере"),
    u"wrong_kind": tr(u"FAIL — не тот тип данных"),
    u"tilt_not_instance": tr(u"FAIL — только на типе (нужен экземпляр)"),
    u"empty": tr(u"~ пусто"),
}


def _kind_label(kind):
    return tr(sot_fov.PARAM_KIND_RU.get(kind, kind))


def _kinds_label(kinds):
    return u"/".join(_kind_label(k) for k in kinds)


def _entry_label(entry):
    if entry is None:
        return u"—"
    name, kind, level, value_text, has_value = entry
    val = value_text if has_value else tr(u"пусто")
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
        tr(u"Выберите ОДНУ камеру для проверки параметров её типа")
    )
except OperationCanceledException:
    forms.alert(tr(u"Выбор отменён."), exitscript=True)

el = doc.GetElement(ref.ElementId)
if el is None:
    forms.alert(tr(u"Не удалось получить выбранный элемент."), exitscript=True)

diag = sot_fov.diagnose_camera_params(doc, el, settings)

output = script.get_output()
output.print_md(tr(u"# Проверка параметров камеры — отчёт"))

cat_note = u"" if diag["category_ok"] else tr(u"  (⚠ не входит в «Категории камер» из настроек «Зон обзора»)")
print(tr(u"Семейство: {}").format(diag["family_name"] or u"—"))
print(tr(u"Типоразмер: {}").format(diag["type_name"] or u"—"))
print(tr(u"Категория: {}{}").format(diag["category_name"] or u"—", cat_note))

output.print_md(u"---")
output.print_md(tr(u"## Роли параметров («Зоны обзора» / «Навести на помещение»)"))
print(tr(u"* — обязательная роль (без неё зона не построится)."))

roles_table = []
for role in diag["roles"]:
    label = role["label"] + (u" *" if role["required"] else u"")
    if role["must_be_instance"]:
        label += tr(u" (только экземпляр)")
    configured_label = (role["configured_name"] or u"—").replace(u";", u" / ")
    roles_table.append([
        label,
        configured_label,
        _STATUS_RU.get(role["status"], role["status"]),
        _entry_label(role["found"]),
        _kinds_label(role["expected_kinds"]),
    ])
output.print_table(
    table_data=roles_table,
    columns=[tr(u"Роль"), tr(u"Настроено имя"), tr(u"Статус"), tr(u"Найдено на камере"), tr(u"Подходящий тип данных")]
)

need_action = [r for r in diag["roles"] if r["status"] != u"ok"]
if need_action:
    output.print_md(tr(u"### Что делать"))
    for role in need_action:
        cands = _candidates_label(role["candidates"])
        if cands:
            print(tr(u"· {}: впишите в настройках одно из имён — {}.").format(role["label"], cands))
        elif role["status"] == u"not_configured" and not role["required"]:
            print(tr(u"· {}: не обязательна, можно оставить пустой.").format(role["label"]))
        else:
            print(
                tr(u"· {}: на камере нет ни одного параметра типа «{}» — "
                u"нужно ДОБАВИТЬ такой параметр в семейство.").format(
                    role["label"], _kinds_label(role["expected_kinds"])
                )
            )

output.print_md(u"---")
output.print_md(tr(u"## Все параметры экземпляра ({})").format(len(diag["instance_params"])))
if diag["instance_params"]:
    output.print_table(
        table_data=_param_rows(diag["instance_params"]),
        columns=[tr(u"Имя"), tr(u"Тип данных"), tr(u"Уровень"), tr(u"Значение")]
    )
else:
    print(tr(u"(нет)"))

output.print_md(tr(u"## Все параметры типа ({})").format(len(diag["type_params"])))
if diag["type_params"]:
    output.print_table(
        table_data=_param_rows(diag["type_params"]),
        columns=[tr(u"Имя"), tr(u"Тип данных"), tr(u"Уровень"), tr(u"Значение")]
    )
else:
    print(tr(u"(нет)"))

nested_params = diag.get("nested_params") or []
output.print_md(tr(u"## Параметры вложенных общих семейств ({})").format(len(nested_params)))
if nested_params:
    output.print_table(
        table_data=_param_rows(nested_params),
        columns=[tr(u"Имя"), tr(u"Тип данных"), tr(u"Уровень"), tr(u"Значение")]
    )
else:
    print(tr(u"(нет вложенных общих семейств — параметры необщих вложенных видны "
          u"только через параметры самой камеры)"))


def _bool_ru(v):
    if v is None:
        return u"—"
    return tr(u"да") if v else tr(u"нет")


def _print_geometry(geo):
    output.print_md(u"---")
    output.print_md(tr(u"## Геометрия и ориентация этого экземпляра в проекте"))
    if geo["location_mm"]:
        x, y, z = geo["location_mm"]
        print(tr(u"Точка вставки, мм: X={:.0f}  Y={:.0f}  Z={:.0f}").format(x, y, z))
    else:
        print(tr(u"Точка вставки: у элемента нет LocationPoint."))
    print(tr(u"Уровень: {}").format(geo["level_name"]))
    print(tr(u"Хост: {}").format(geo["host_label"]))
    print(tr(u"Тип размещения семейства: {}").format(geo["placement_type"]))
    print(u"Mirrored: {}   FacingFlipped: {}   HandFlipped: {}".format(
        _bool_ru(geo["mirrored"]), _bool_ru(geo["facing_flipped"]), _bool_ru(geo["hand_flipped"])
    ))
    az = geo["facing_azimuth_deg"]
    print(u"FacingOrientation: {}{}".format(
        geo["facing_orientation_text"],
        tr(u"  (азимут {:.0f}°)").format(az) if az is not None else u""
    ))
    print(u"HandOrientation: {}".format(geo["hand_orientation_text"]))
    print(u"Transform.BasisY / BasisX: {} / {}".format(geo["basis_y_text"], geo["basis_x_text"]))
    print(u"")
    print(tr(u"Направление, которое реально берёт «Зоны обзора» (FacingOrientation -> "
          u"BasisY -> BasisX -> HandOrientation⟂, первое ненулевое, плюс поворот/доворот "
          u"из настроек): {}").format(geo["used_direction_source"]))
    if geo["used_azimuth_deg"] is not None:
        print(tr(u"Итоговый азимут зоны: {:.0f}°").format(geo["used_azimuth_deg"]))


def _print_family_def(fdef):
    output.print_md(u"---")
    output.print_md(tr(u"## Разбор семейства (структура .rfa)"))
    print(tr(u"Семейство: {}   Категория: {}   Тип размещения: {}").format(
        fdef["family_name"] or u"—", fdef["category_name"] or u"—", fdef["placement_type"] or u"—"
    ))

    if fdef["error"]:
        print(u"⚠ {}".format(fdef["error"]))
    if not fdef["editable"]:
        return

    types = fdef["types"]
    if types:
        param_order = [(p[0], p[1]) for p in types[0]["params"]]
        rows = []
        for i, (pname, formula) in enumerate(param_order):
            row = [pname, formula or u"—"]
            for t in types:
                params = t["params"]
                tp_val = params[i][2] if i < len(params) else u""
                row.append(tp_val or u"—")
            rows.append(row)
        output.print_md(tr(u"### Типоразмеры и параметры ({})").format(len(types)))
        print(tr(u"Столбец «Формула» — из чего вычисляется параметр внутри семейства (пусто — вписывается вручную)."))
        output.print_table(
            table_data=rows,
            columns=[tr(u"Параметр"), tr(u"Формула")] + [t["name"] for t in types]
        )
    else:
        print(tr(u"Типоразмеры не прочитаны (семейство без типов либо ошибка выше)."))

    if fdef["nested_families"]:
        output.print_md(tr(u"### Вложенные семейства"))
        output.print_table(
            table_data=[[n["name"], n["category"] or u"—", n["count"]] for n in fdef["nested_families"]],
            columns=[tr(u"Семейство"), tr(u"Категория"), tr(u"Экземпляров")]
        )

    if fdef["forms"]:
        output.print_md(tr(u"### Формы (тела/вырезы)"))
        output.print_table(
            table_data=[[f["name"], f["kind"]] for f in fdef["forms"]],
            columns=[tr(u"Имя"), tr(u"Тело/вырез")]
        )

    if fdef["reference_planes"]:
        print(tr(u"Опорные плоскости: {}").format(u", ".join(fdef["reference_planes"])))

    if fdef["connectors"]:
        output.print_md(tr(u"### Разъёмы (connectors)"))
        output.print_table(
            table_data=[[c["domain"], c["id"]] for c in fdef["connectors"]],
            columns=[tr(u"Домен"), u"Id"]
        )


_print_geometry(diag["geometry"])
_print_family_def(diag["family_def"])
