# -*- coding: utf-8 -*-
"""
Построение шлейфа СПС/СОУЭ/СПА и расчёт его длины по координатам устройств.

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

Переход между этажами (стояк) и кольцевой шлейф
-------------------------------------------------
build_loop_tree/build_route_text/previous_address_by_id не знают про этажи
и стояк — дерево строится и раньше, по адресу и геометрии. Про этажи и
стояк знает только расчёт длины (calc_loop_length_ft/_edge_length_ft):
если узлы ребра на разных этажах (node["floor"], проставляется
fire_alarm_circuits.build_loop_nodes по level_param_name) и передан
risers_by_floor (fire_alarm_circuits.find_risers/group_risers_by_floor) —
ребро считается через ближайший стояк на каждом из двух этажей, а не
напрямую. calc_loop_length_ft(..., ring_loop=True) добавляет обратный
участок кольца — от последнего узла МАГИСТРАЛИ (не ветки изолятора) до
ближайшего стояка на его этаже (резерв — прямой участок до панели); ветви
изоляторов в кольцо не входят и не удваиваются.

Работает с обычными dict-записями, без Revit API — как scs_addressing.
"""

FT_TO_M = 0.3048


def manhattan_ft(pt_a, pt_b):
    """Длина по катетам между точками, в футах (единицы Revit)."""
    return abs(pt_a.X - pt_b.X) + abs(pt_a.Y - pt_b.Y) + abs(pt_a.Z - pt_b.Z)


def _nearest_riser(risers, pt):
    """Ближайший (по катетам) риск из списка risers к точке pt, либо None."""
    if not risers:
        return None
    return min(risers, key=lambda r: manhattan_ft(r["pt"], pt))


def _edge_length_ft(pt_a, floor_a, pt_b, floor_b, risers_by_floor):
    """
    Длина ребра между двумя точками по катетам.

    Если этажи совпадают (или неизвестны, или стояки не заданы) — прямой
    отрезок по катетам, как раньше. Если этажи разные — через стояк:
    точка_a -> ближайший стояк НА ЭТАЖЕ a -> ближайший стояк НА ЭТАЖЕ b ->
    точка_b, тоже по катетам на каждом участке. Стояк на каждом этаже
    выбирается независимо (ближайший к своей точке) — сопоставление
    вертикали между этажами не нужно явно: при обычном вертикальном
    стояке, выровненном по X/Y на всех этажах, "ближайший к точке на своём
    этаже" и так даёт один и тот же стояк.

    Если стояк не нашёлся хотя бы на одном из двух этажей — резерв: прямой
    отрезок, как если бы стояк не был задан вовсе.
    """
    direct = manhattan_ft(pt_a, pt_b)

    if not risers_by_floor or floor_a == floor_b or floor_a is None or floor_b is None:
        return direct

    riser_a = _nearest_riser(risers_by_floor.get(floor_a), pt_a)
    riser_b = _nearest_riser(risers_by_floor.get(floor_b), pt_b)

    if riser_a is None or riser_b is None:
        return direct

    return (
        manhattan_ft(pt_a, riser_a["pt"]) +
        manhattan_ft(riser_a["pt"], riser_b["pt"]) +
        manhattan_ft(riser_b["pt"], pt_b)
    )


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


def calc_loop_length_ft(ordered_nodes, panel_point=None, panel_floor=None,
                         risers_by_floor=None, ring_loop=False):
    """
    Суммарная длина шлейфа по дереву (в футах): каждое ребро
    "родитель -> узел" считается один раз, ветви изоляторов не
    возвращаются назад (и не входят в кольцо, см. ring_loop ниже).

    Если задана panel_point, добавляется участок от панели до первого
    устройства. Каждое ребро (включая панель -> первое устройство) вместо
    прямого катета считается через стояк, если у его концов разные этажи
    (node["floor"]/panel_floor) и risers_by_floor непустой — см.
    _edge_length_ft.

    ring_loop=True — добавляет обратный участок кольца: от последнего узла
    МАГИСТРАЛИ (не ветки изолятора) до ближайшего стояка на его этаже, по
    катетам; если стояк не найден — прямой участок по катетам до панели.
    Узел считается магистральным, если его родитель — непосредственно
    предыдущий по адресу узел (у веток изолятора родитель — сам изолятор,
    а не предыдущий по номеру узел, этим они и отличаются от магистрали,
    см. build_loop_tree). Корневой узел (первый по адресу) магистральный
    всегда.
    """
    by_id = dict((n["id"], n) for n in ordered_nodes)

    total_ft = 0.0
    last_trunk_node = None

    for i, node in enumerate(ordered_nodes):
        parent_id = node.get("parent_id")

        if parent_id is None:
            if panel_point is not None:
                total_ft += _edge_length_ft(
                    panel_point, panel_floor, node["pt"], node.get("floor"), risers_by_floor
                )
            last_trunk_node = node
            continue

        parent = by_id.get(parent_id)
        if parent is None:
            continue

        total_ft += _edge_length_ft(
            parent["pt"], parent.get("floor"), node["pt"], node.get("floor"), risers_by_floor
        )

        if parent_id == ordered_nodes[i - 1]["id"]:
            last_trunk_node = node

    if ring_loop and last_trunk_node is not None:
        riser = _nearest_riser(
            (risers_by_floor or {}).get(last_trunk_node.get("floor")), last_trunk_node["pt"]
        )
        if riser is not None:
            total_ft += manhattan_ft(last_trunk_node["pt"], riser["pt"])
        elif panel_point is not None:
            total_ft += manhattan_ft(last_trunk_node["pt"], panel_point)

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
