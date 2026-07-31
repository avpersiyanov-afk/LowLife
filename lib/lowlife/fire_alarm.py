# -*- coding: utf-8 -*-
"""
Константы и логика, специфичные для СПС и СОУЭ (пожарная сигнализация и
оповещение).

Отличие от СКС/СКУД: здесь нет отдельных маркеров узлов маршрута — узлом
шлейфа выступает само устройство. Устройства соединяются в шлейф по
адресу (панель.шлейф.номер), длина считается по координатам соседних
устройств, а изоляторы (ответвители) начинают ветвь, которая назад к
магистрали не возвращается.

Адресация:
    панель     SMNX_Обозначение = "ARK", SMNX_Адрес устройства = "3"  -> ARK3
    устройство SMNX_Обозначение = "BTH", SMNX_Адрес устройства = "3.1.2"
                                                    панель 3, шлейф 1, №2
"""

from lowlife.scs import classify_element

# Ключевое слово изолятора/ответвителя в имени семейства — от такого
# устройства уходит ветвь.
ISOLATOR_KEYWORD = u"изолятор"


def parse_device_address(address):
    """
    "3.1.2" -> (3, 1, 2) — (номер панели, номер шлейфа, порядковый номер).

    Возвращает None, если адрес не разбирается: лишние/недостающие части
    или нечисловые значения. Пробелы вокруг чисел допускаются.
    """
    if not address:
        return None

    parts = [p.strip() for p in unicode(address).split(u".")]

    if len(parts) != 3:
        return None

    try:
        return tuple(int(p) for p in parts)
    except:
        return None


def parse_panel_address(address):
    """
    "3" -> 3 — номер панели из её SMNX_Адрес устройства.

    Возвращает None, если это не одно целое число.
    """
    if not address:
        return None

    value = unicode(address).strip()

    try:
        return int(value)
    except:
        return None


def make_full_mark(designation, address):
    """"ARK" + "3" -> "ARK3"; "BTH" + "3.1.2" -> "BTH3.1.2"."""
    if designation and address:
        return u"{}{}".format(designation, address)
    if designation:
        return unicode(designation)
    if address:
        return unicode(address)
    return None


def is_isolator(el, isolator_keyword=ISOLATOR_KEYWORD):
    """Изолятор/ответвитель — по ключевому слову в имени семейства/типа."""
    if not isolator_keyword:
        return False
    return classify_element(el, [("isolator", [isolator_keyword], [])]) == "isolator"


def group_devices_by_loop(devices, address_by_id):
    """
    Группирует устройства по (панель, шлейф).

    devices — список элементов, address_by_id — {element_id: (panel, loop,
    index)}. Возвращает {(panel, loop): [элементы, отсортированные по
    порядковому номеру]}.
    """
    loops = {}

    for el in devices:
        parsed = address_by_id.get(el.Id.IntegerValue)
        if parsed is None:
            continue
        panel_num, loop_num, _index = parsed
        loops.setdefault((panel_num, loop_num), []).append(el)

    for key in loops:
        loops[key].sort(key=lambda e: address_by_id[e.Id.IntegerValue][2])

    return loops
