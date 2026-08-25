# -*- coding: utf-8 -*-
"""
Построение шлейфа СПС/СОУЭ и расчёт его длины по координатам устройств.

Отличие от СКС/СКУД: отдельных маркеров узлов нет — узлом шлейфа служит
само устройство. Порядок в шлейфе задаёт третье число адреса
(панель.шлейф.НОМЕР), а длина считается по координатам соседних устройств
(|dx|+|dy|+|dz|), потому что рядом стоящие обозначения перекрывают друг
друга и рисовать линии трассы негде.

Ветви от изоляторов
-------------------
Изолятор (ответвитель) начинает ветвь, которая назад к магистрали НЕ
возвращается. Нумерация K при этом сквозная по всему шлейфу, поэтому по
одному номеру отличить «продолжение магистрали» от «устройства на ветви»
нельзя — решает геометрия: каждое следующее устройство присоединяется к
тому из уже размещённых кандидатов (предыдущее по порядку либо любой
изолятор), который к нему ближе. Так ветвь, уходящая в сторону от
магистрали, цепляется за свой изолятор, а не тянется через всю трассу.

Работает с обычными dict-записями, без Revit API — как scs_addressing.
"""

FT_TO_M = 0.3048


def manhattan_ft(pt_a, pt_b):
    """Длина по катетам между точками, в футах (единицы Revit)."""
    return abs(pt_a.X - pt_b.X) + abs(pt_a.Y - pt_b.Y) + abs(pt_a.Z - pt_b.Z)


def build_loop_tree(nodes, panel_point=None):
    """
    Строит дерево шлейфа.

    nodes — список dict с ключами:
        "id"         — идентификатор (обычно ElementId.IntegerValue)
        "index"      — порядковый номер K из адреса
        "pt"         — точка (Revit XYZ или любой объект с .X/.Y/.Z)
        "is_isolator"— True для изолятора/ответвителя
    panel_point — точка панели; если задана, первое устройство цепляется к
    панели (её длина входит в шлейф).

    Проставляет каждому узлу "parent_id" (None у первого) и возвращает
    список узлов в порядке обхода. Порядок nodes значения не имеет —
    сортируется по "index".
    """
    ordered = sorted(nodes, key=lambda n: n["index"])

    if not ordered:
        return []

    for n in ordered:
        n["parent_id"] = None

    placed = []

    for node in ordered:
        if not placed:
            # Первое устройство шлейфа — от панели (если она известна).
            node["parent_id"] = None
            placed.append(node)
            continue

        # Кандидаты в родители: предыдущее по порядку устройство и любой
        # уже размещённый изолятор (от него может уходить ветвь).
        candidates = [placed[-1]]
        candidates.extend(p for p in placed if p["is_isolator"] and p is not placed[-1])

        # При равном расстоянии предпочитаем изолятор: ветви отходят
        # именно от них, а иначе выбор зависел бы от порядка перебора.
        # Второй ключ (id) — чтобы результат не менялся между запусками.
        best = min(
            candidates,
            key=lambda c: (manhattan_ft(c["pt"], node["pt"]), 0 if c["is_isolator"] else 1, c["id"])
        )

        node["parent_id"] = best["id"]
        placed.append(node)

    return ordered


def calc_loop_length_ft(ordered_nodes, panel_point=None):
    """
    Суммарная длина шлейфа по дереву (в футах): каждое ребро
    "родитель -> узел" считается один раз, ветви не возвращаются назад.

    Если задана panel_point, добавляется участок от панели до первого
    устройства.
    """
    by_id = dict((n["id"], n) for n in ordered_nodes)

    total_ft = 0.0

    for node in ordered_nodes:
        parent_id = node.get("parent_id")

        if parent_id is None:
            if panel_point is not None:
                total_ft += manhattan_ft(panel_point, node["pt"])
            continue

        parent = by_id.get(parent_id)
        if parent is None:
            continue

        total_ft += manhattan_ft(parent["pt"], node["pt"])

    return total_ft


def build_route_text(ordered_nodes, address_text_by_id):
    """
    Текст маршрута шлейфа: "3.1.1 -> 3.1.2 -> 3.1.3".

    Ветви показываются от своего изолятора: "3.1.2 -> 3.1.5" означает, что
    устройство 5 подключено к изолятору 2, а не к предыдущему по номеру.
    """
    parts = []

    for node in ordered_nodes:
        parent_id = node.get("parent_id")
        node_text = address_text_by_id.get(node["id"], unicode(node["index"]))

        if parent_id is None:
            parts.append(node_text)
            continue

        parent_text = address_text_by_id.get(parent_id)
        if parent_text:
            parts.append(u"{} -> {}".format(parent_text, node_text))
        else:
            parts.append(node_text)

    return u"; ".join(parts)


def parse_route_edges(route_text):
    """
    Обратный разбор текста маршрута шлейфа (build_route_text) — список
    (parent_addr, child_addr) для отрисовки маршрута кнопкой «Маршрут
    цепи»: parent_addr is None у корневого звена (подключено к панели
    напрямую, без родителя-устройства).

    "ARK1.1.1; ARK1.1.1 -> ARK1.1.2" ->
        [(None, "ARK1.1.1"), ("ARK1.1.1", "ARK1.1.2")]
    """
    text = (route_text or u"").strip()
    if not text:
        return []

    edges = []

    for part in text.split(u";"):
        part = part.strip()
        if not part:
            continue

        if u"->" in part:
            parent, child = part.split(u"->", 1)
            parent = parent.strip()
            child = child.strip()
            if child:
                edges.append((parent or None, child))
        else:
            edges.append((None, part))

    return edges


def previous_address_by_id(ordered_nodes, address_text_by_id):
    """
    {id устройства: адрес его родителя} — для записи «Предыдущий адрес» на
    устройствах, чтобы на плане было видно фактическую топологию шлейфа
    (особенно ветви от изоляторов).
    """
    result = {}

    for node in ordered_nodes:
        parent_id = node.get("parent_id")
        if parent_id is None:
            result[node["id"]] = u""
        else:
            result[node["id"]] = address_text_by_id.get(parent_id, u"")

    return result
