# -*- coding: utf-8 -*-
"""
Инкрементальная синхронизация структурной схемы СКУД — аналог
sot_schematic.sync_levels / sync_rooms_in_level.

Единица неизменности — ТОЧКА ПРОХОДА (схемное семейство контроллера
синхронизируется отдельно). При повторном запуске BuildSkudSchematic:
  - точка прохода с тем же набором устройств (по UniqueId) и той же
    подобранной группой — по геометрии не трогается (ручная раскладка
    сохраняется), обновляются только адрес/марка на схемных элементах;
  - изменившаяся — удаляется и рисуется заново;
  - пропавшая из модели — удаляется;
  - новая — размещается.
Линии контроллер→точка прохода пересоздаются каждый запуск (у прямых
коннекторов ручной маршрутизации нет).

Модуль работает с Revit API напрямую (как sot_schematic.py) — вне Revit
не импортируется и юнит-тестами не покрыт. Чистая часть (сигнатуры,
passage_point_changed, раскладочные точки) — в skud_schematic.py.
"""

import clr
clr.AddReference('RevitAPI')

from Autodesk.Revit.DB import ElementId, XYZ, Line

from lowlife.params import get_string_param, set_param_any
from lowlife.scs import safe_element_name
from lowlife.skud_schematic import (
    layout_points_by_level, passage_point_layout_point, device_layout_point,
    passage_point_changed, signature_text,
)


# ------------------------------------------------------------
# Revit-хелперы
# ------------------------------------------------------------

def _resolve(doc, id_int):
    if id_int is None:
        return None
    try:
        return doc.GetElement(ElementId(int(id_int)))
    except:
        return None


def _delete(doc, ids):
    for i in ids or []:
        el = _resolve(doc, i)
        if el is None:
            continue
        try:
            doc.Delete(el.Id)
        except:
            pass


def _location_point(el):
    try:
        return el.Location.Point
    except:
        return None


def _all_resolve(doc, ids):
    if not ids:
        return False
    for i in ids:
        if _resolve(doc, i) is None:
            return False
    return True


def _anchor_of(doc, ids, fallback):
    """Среднее Location.Point резолвнутых элементов; fallback, если ни одного."""
    pts = []
    for i in ids or []:
        el = _resolve(doc, i)
        if el is None:
            continue
        p = _location_point(el)
        if p is not None:
            pts.append(p)
    if not pts:
        return fallback
    n = float(len(pts))
    return XYZ(sum(p.X for p in pts) / n, sum(p.Y for p in pts) / n, pts[0].Z)


def _sorted_schematic(els):
    def key(el):
        p = _location_point(el)
        return (p.X, p.Y) if p is not None else (0.0, 0.0)
    return sorted(els, key=key)


def _place_group(doc, group_type, pt):
    """PlaceGroup + Regenerate + UngroupMembers -> ([int id членов], имя группы)."""
    if group_type is None:
        return [], u""
    try:
        g = doc.Create.PlaceGroup(pt, group_type)
        doc.Regenerate()
        freed = list(g.UngroupMembers())
    except:
        freed = []
    return [mid.IntegerValue for mid in freed], (safe_element_name(group_type) or u"")


def _make_line(doc, view, p_from, p_to):
    try:
        dc = doc.Create.NewDetailCurve(view, Line.CreateBound(p_from, p_to))
        return dc.Id.IntegerValue
    except:
        return None


def _dev_state(d, schem_el):
    return {
        "schematic_id": schem_el.Id.IntegerValue if schem_el is not None else None,
        "category": d["category"] or u"",
        "address": d["address"] or u"",
        "room": d["room"] or u"",
    }


def _write_address_and_mark(doc, el, addr, cfg):
    """Адрес → «Адрес…», и он же → «Марка…» (если параметр марки задан)."""
    if not addr:
        return
    set_param_any(el, cfg["schematic_address_param"], addr)
    if cfg["device_marking_param"]:
        set_param_any(el, cfg["device_marking_param"], addr)


def _link_and_address(doc, schem_el, d, cfg):
    if cfg["source_uid_param"]:
        set_param_any(schem_el, cfg["source_uid_param"], d["uid"])
    _write_address_and_mark(doc, schem_el, d["address"] or u"", cfg)


# ------------------------------------------------------------
# Точка прохода: keep / redraw
# ------------------------------------------------------------

def _keep_passage_point(doc, pp, prev_pp, cfg, report):
    """Геометрию не трогаем — только обновляем адрес/марку на схемных элементах."""
    uid_to_schem = {}
    if cfg["source_uid_param"]:
        for i in prev_pp.get("element_ids", []):
            el = _resolve(doc, i)
            if el is None:
                continue
            u = get_string_param(el, cfg["source_uid_param"])
            if u:
                uid_to_schem[u] = i

    devices_state = {}
    for d in pp["devices"]:
        uid = d["uid"]
        prev_dev = prev_pp.get("devices", {}).get(uid, {})
        schem_id = prev_dev.get("schematic_id")
        if _resolve(doc, schem_id) is None:
            schem_id = uid_to_schem.get(uid)
        schem_el = _resolve(doc, schem_id)

        addr = d["address"] or u""
        if schem_el is not None:
            if addr:
                set_param_any(schem_el, cfg["schematic_address_param"], addr)
                if cfg["device_marking_param"]:
                    set_param_any(schem_el, cfg["device_marking_param"], addr)
        else:
            report["stale_refs"] += 1

        devices_state[uid] = {
            "schematic_id": schem_id,
            "category": d["category"] or u"",
            "address": addr,
            "room": d["room"] or u"",
        }

    return {
        "signature": [[c, n] for c, n in pp["signature"]],
        "group": pp["matched_group"],
        "element_ids": list(prev_pp.get("element_ids", [])),
        "devices": devices_state,
    }


def _redraw_passage_point(doc, view, pp, pp_pt, cfg):
    matched = pp["matched_group"]
    element_ids = []
    devices_state = {}

    # реальные устройства по категории, в порядке первого появления
    desired_by_cat = {}
    order = []
    for d in pp["devices"]:
        c = d["category"] or u""
        if c not in desired_by_cat:
            desired_by_cat[c] = []
            order.append(c)
        desired_by_cat[c].append(d)

    if matched:
        gt = cfg["pp_group_types_by_name"].get(matched)
        freed, _gname = _place_group(doc, gt, pp_pt)
        element_ids.extend(freed)

        schem_by_cat = {}
        for i in freed:
            el = _resolve(doc, i)
            if el is None:
                continue
            cat = cfg["category_of_schematic"](el)
            if not cat:
                continue
            schem_by_cat.setdefault(cat, []).append(el)

        for cat in order:
            schem_list = _sorted_schematic(schem_by_cat.get(cat, []))
            devs = desired_by_cat[cat]
            for d, schem_el in zip(devs, schem_list):
                _link_and_address(doc, schem_el, d, cfg)
                devices_state[d["uid"]] = _dev_state(d, schem_el)
            for d in devs[len(schem_list):]:
                devices_state[d["uid"]] = _dev_state(d, None)
    else:
        # резервная раскладка: все устройства столбиком вниз от pp_pt,
        # в порядке категорий (в пределах категории — по адресу)
        idx = 0
        for cat in order:
            for d in desired_by_cat[cat]:
                symbol = cfg["category_symbols"].get(cat) if cat else None
                if symbol is None:
                    devices_state[d["uid"]] = _dev_state(d, None)
                    continue
                if not symbol.IsActive:
                    symbol.Activate()
                dpt = device_layout_point(pp_pt, idx, cfg["fallback_step_ft"])
                idx += 1
                schem_el = doc.Create.NewFamilyInstance(dpt, symbol, view)
                if schem_el is None:
                    devices_state[d["uid"]] = _dev_state(d, None)
                    continue
                element_ids.append(schem_el.Id.IntegerValue)
                _link_and_address(doc, schem_el, d, cfg)
                devices_state[d["uid"]] = _dev_state(d, schem_el)

    return {
        "signature": [[c, n] for c, n in pp["signature"]],
        "group": matched,
        "element_ids": element_ids,
        "devices": devices_state,
    }


# ------------------------------------------------------------
# Контроллер — одиночное схемное семейство (не группа)
# ------------------------------------------------------------

def _place_controller(doc, view, symbol, uid, addr, cfg, pt):
    """Вставляет схемное семейство контроллера, пишет UniqueId, адрес и марку.
    Возвращает [int id] (пустой список, если вставить не удалось)."""
    if symbol is None:
        return []
    if not symbol.IsActive:
        symbol.Activate()
    try:
        el = doc.Create.NewFamilyInstance(pt, symbol, view)
    except:
        el = None
    if el is None:
        return []
    if cfg["source_uid_param"]:
        set_param_any(el, cfg["source_uid_param"], uid)
    _write_address_and_mark(doc, el, addr, cfg)
    return [el.Id.IntegerValue]


def _sync_controller_node(doc, view, dc, prev_c, fresh_pt, cfg):
    """(element_ids, insert_pt). insert_pt — откуда раскладывать точки
    прохода этого контроллера."""
    addr = dc["address"]
    prev_node = prev_c.get("node") if prev_c else None

    if prev_node and _all_resolve(doc, prev_node.get("element_ids", [])):
        ids = list(prev_node["element_ids"])
        for i in ids:
            el = _resolve(doc, i)
            if el is not None:
                _write_address_and_mark(doc, el, addr, cfg)
        return ids, _anchor_of(doc, ids, fresh_pt)

    if prev_node:
        _delete(doc, prev_node.get("element_ids", []))

    ids = _place_controller(doc, view, cfg["controller_symbol"], dc["uid"], addr, cfg, fresh_pt)
    return ids, fresh_pt


# ------------------------------------------------------------
# Верхний уровень
# ------------------------------------------------------------

def sync_schematic(doc, view, desired_controllers, previous_state, cfg):
    """
    desired_controllers — желаемое состояние:
      [{"uid", "id", "address", "elevation",
        "passage_points": [{"key", "signature", "uncategorized",
                            "matched_group"|None,
                            "devices": [{"uid","id","category","address","room"}]}]}]
    previous_state — dict манифеста v2 (или skud_schematic_manifest.empty_manifest()).
    cfg — dict: category_of_schematic, schematic_address_param,
      device_marking_param, source_uid_param, controller_symbol (FamilySymbol
      схемного семейства контроллера), pp_group_types_by_name {имя: GroupType},
      category_symbols {категория: FamilySymbol} (для резервной раскладки),
      fallback_step_ft (шаг столбика в резервной раскладке), layout_gap_ft.

    Возвращает (new_state, report). Транзакция уже открыта вызывающим.
    """
    prev_controllers = previous_state.get("controllers", {})
    _delete(doc, previous_state.get("line_ids", []))
    new_line_ids = []

    elevations = [c["elevation"] for c in desired_controllers]
    fresh_points = layout_points_by_level(XYZ(0.0, 0.0, 0.0), elevations, cfg["layout_gap_ft"])

    report = {
        "pp_unchanged": 0, "pp_redrawn": 0, "pp_created": 0, "pp_removed": 0,
        "controllers_created": 0, "controllers_removed": 0, "stale_refs": 0,
        "no_match": [],
    }

    desired_uids = set(c["uid"] for c in desired_controllers)
    new_controllers = {}

    for idx, dc in enumerate(desired_controllers):
        uid = dc["uid"]
        prev_c = prev_controllers.get(uid)
        if prev_c is None:
            report["controllers_created"] += 1

        node_ids, insert_pt = _sync_controller_node(
            doc, view, dc, prev_c, fresh_points[idx], cfg
        )
        controller_anchor = _anchor_of(doc, node_ids, insert_pt)

        prev_pps = prev_c.get("passage_points", {}) if prev_c else {}
        new_pps = {}

        for i, pp in enumerate(dc["passage_points"]):
            key = pp["key"]
            prev_pp = prev_pps.get(key)
            desired_dev_uids = [d["uid"] for d in pp["devices"]]

            changed = passage_point_changed(prev_pp, desired_dev_uids, pp["matched_group"])
            if prev_pp is not None and not changed and not _all_resolve(
                doc, prev_pp.get("element_ids", [])
            ):
                changed = True

            pp_pt = passage_point_layout_point(insert_pt, i, cfg["layout_gap_ft"])

            if not changed:
                new_pp = _keep_passage_point(doc, pp, prev_pp, cfg, report)
                report["pp_unchanged"] += 1
            else:
                if prev_pp is not None:
                    _delete(doc, prev_pp.get("element_ids", []))
                    report["pp_redrawn"] += 1
                else:
                    report["pp_created"] += 1
                new_pp = _redraw_passage_point(doc, view, pp, pp_pt, cfg)

            if pp["matched_group"] is None:
                report["no_match"].append(
                    u"Контроллер {} — точка прохода «{}»: нет типовой группы для "
                    u"состава {}. Создайте группу с этим составом.".format(
                        dc["address"], key, signature_text(tuple(tuple(x) for x in pp["signature"]))
                    )
                )

            new_pps[key] = new_pp

            pp_anchor = _anchor_of(doc, new_pp["element_ids"], pp_pt)
            lid = _make_line(doc, view, controller_anchor, pp_anchor)
            if lid is not None:
                new_line_ids.append(lid)

        for old_key, old_pp in prev_pps.items():
            if old_key not in new_pps:
                _delete(doc, old_pp.get("element_ids", []))
                report["pp_removed"] += 1

        new_controllers[uid] = {
            "address": dc["address"],
            "node": {"element_ids": node_ids},
            "passage_points": new_pps,
        }

    for old_uid, old_c in prev_controllers.items():
        if old_uid in desired_uids:
            continue
        _delete(doc, old_c.get("node", {}).get("element_ids", []))
        for old_pp in old_c.get("passage_points", {}).values():
            _delete(doc, old_pp.get("element_ids", []))
        report["controllers_removed"] += 1

    new_state = {
        "schema_version": 2,
        "line_ids": new_line_ids,
        "controllers": new_controllers,
    }
    return new_state, report
