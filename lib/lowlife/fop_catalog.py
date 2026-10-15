# -*- coding: utf-8 -*-
"""
Каталог общих параметров, нужных кнопкам LowLife, — для кнопки
«Параметры в ФОП» (Tools.panel/FopParameters, окно — fop_parameters_ui.py,
работа с ФОП и привязки — fop_setup.py).

Каждая строка каталога — одна роль параметра (ключ настроек кнопок, тот же,
что в scs_settings/skud_settings/fire_alarm_settings/sot_settings), пример
имени, тип данных, экземпляр/тип и категории, к которым параметр нужно
привязать, — отдельно для каждой системы, которая его использует. Окно
показывает строки выбранных систем: категории — объединение категорий этих
систем, имя — уже введённое в настройках кнопок (или запомненное в общих
настройках), иначе пример.

Имена-примеры — только образец: реальные имена параметров — соглашение
проекта (см. CLAUDE.md), пользователь правит их в окне. Сюда нельзя вписывать
реальные имена конкретного проекта.

Без Revit API и WPF — категории записаны строками имён BuiltInCategory,
модуль покрыт tests/test_fop_catalog.py.
"""

import re

try:
    _text = unicode  # noqa: F821 — IronPython/Python 2
    _string_types = basestring  # noqa: F821
except NameError:  # Python 3 (тесты)
    _text = str
    _string_types = str


# --- системы -------------------------------------------------------------------

# (id, подпись, файл настроек кнопок системы в %APPDATA%\pyRevit)
SYSTEMS = [
    ("SCS", u"СКС", "LowLifeSCS_settings.json"),
    ("SKUD", u"СКУД", "LowLifeSKUD_settings.json"),
    ("SPS", u"СПС", "LowLifeSPS_settings.json"),
    ("SOUE", u"СОУЭ", "LowLifeSOUE_settings.json"),
    ("SPA", u"СПА", "LowLifeSPA_settings.json"),
    ("SOT", u"СОТ", "LowLifeSOT_settings.json"),
    ("SOUE_FLOOR", u"СОУЭ «Типовой этаж»", "LowLifeSOUEFloor_settings.json"),
    ("SS1", u"СС1", "LowLifeSS1Easy_settings.json"),
    ("COMPANION", u"РМ, АМ, МДУ", "LowLifeCompanionPlacement_settings.json"),
    ("ROOM_INFO", u"Запись помещения", "LowLifeRoomInfo_settings.json"),
    ("FLOOR", u"Заполнение этажа", "LowLifeFloor_settings.json"),
]

SYSTEM_IDS = [s[0] for s in SYSTEMS]
SYSTEM_TITLES = dict((s[0], s[1]) for s in SYSTEMS)
SYSTEM_FILES = dict((s[0], s[2]) for s in SYSTEMS)

FIRE = ("SPS", "SOUE", "SPA")

# Кнопки, которые пишут в элементы любых категорий, выбранных пользователем
# («Запись помещения», «Заполнение этажа»): у их ролей категорий нет — окно
# создаёт параметр в ФОП и вписывает имя в настройки, а привязать его к
# нужным категориям нужно вручную.
MANUAL_BINDING = u"— привяжите вручную"


# --- типы данных и привязка ------------------------------------------------------

TEXT = "text"
LENGTH = "length"
NUMBER = "number"

DATA_TYPE_TITLES = {
    TEXT: u"Текст",
    LENGTH: u"Длина",
    NUMBER: u"Число",
}

INSTANCE = "instance"
TYPE = "type"

KIND_TITLES = {
    INSTANCE: u"Экземпляр",
    TYPE: u"Тип",
}


# --- категории -------------------------------------------------------------------

GENERIC = "OST_GenericModel"
COMM = "OST_CommunicationDevices"
FIXTURES = "OST_ElectricalFixtures"
DATA = "OST_DataDevices"
EQUIPMENT = "OST_ElectricalEquipment"
CIRCUITS = "OST_ElectricalCircuit"
VIEWS = "OST_Views"
DETAIL = "OST_DetailComponents"
FIRE_DEVICES = "OST_FireAlarmDevices"
SECURITY = "OST_SecurityDevices"

CATEGORY_TITLES = {
    GENERIC: u"Обобщённые модели",
    COMM: u"Устройства связи",
    FIXTURES: u"Электрические приборы",
    DATA: u"Датчики/устройства данных",
    EQUIPMENT: u"Электрооборудование",
    CIRCUITS: u"Электрические цепи",
    VIEWS: u"Виды",
    DETAIL: u"Элементы узлов",
    FIRE_DEVICES: u"Пожарная сигнализация",
    SECURITY: u"Охранная сигнализация",
}

LV_DEVICES = [COMM, FIXTURES, DATA]          # слаботочные устройства СКС/СКУД
LV_AND_PANELS = LV_DEVICES + [EQUIPMENT]
FIRE_AND_PANELS = [FIRE_DEVICES, EQUIPMENT]
SOT_SOURCES = [SECURITY, EQUIPMENT, DATA]    # как sot_settings.SOURCE_CATEGORIES
SS1_ELEMENTS = [COMM, DATA, GENERIC]         # кроссы и кабельные подводы СС1


def _fire(categories):
    return dict((s, categories) for s in FIRE)


# --- каталог ---------------------------------------------------------------------

class ParamSpec(object):
    """
    Одна роль параметра.

    key        — ключ в файлах настроек кнопок.
    system_keys — {id системы: [ключи]} — если в какой-то системе та же роль
                 записана под другим ключом (или под несколькими — одно и то
                 же значение на устройстве и на значке схемы); без записи —
                 [key]. Имя параметра пишется во все ключи.
    label      — что это за параметр (подпись в окне).
    example    — пример имени без префикса (окно добавляет префикс).
    data_type  — TEXT/LENGTH/NUMBER (тип нового определения в ФОП).
    kind       — INSTANCE/TYPE.
    categories — {id системы: [имена BuiltInCategory]}.
    aliases    — другие частые названия того же параметра (без префикса) —
                 для поиска похожего параметра в ФОП (match_fop).
    is_list    — в настройках список имён через запятую (своё имя ставится
                 первым, остальные сохраняются).
    note       — пояснение (необязательность и т. п.).
    """

    def __init__(self, key, label, example, data_type, kind, categories,
                 aliases=(), is_list=False, note=u"", system_keys=None):
        self.key = key
        self.system_keys = dict(system_keys or {})
        self.label = label
        self.example = example
        self.data_type = data_type
        self.kind = kind
        self.categories = categories
        self.aliases = list(aliases)
        self.is_list = is_list
        self.note = note

    def keys_for(self, system):
        """Ключи настроек роли в файле системы."""
        return list(self.system_keys.get(system) or [self.key])


_OPTIONAL_SCHEMATIC = u"Нужен только для структурной схемы"

CATALOG = [
    # --- узлы трассы (СКС/СКУД) ---
    ParamSpec("route_param_name", u"Тип трассы узла (маршрут/стояк)", u"Тип трассы",
              TEXT, INSTANCE, {"SCS": [GENERIC], "SKUD": [GENERIC]}),
    ParamSpec("cable_param_name", u"Тип прокладки кабеля (узлы трассы)", u"Тип прокладки",
              TEXT, INSTANCE, {"SCS": [GENERIC], "SKUD": [GENERIC]}),
    ParamSpec("addr_param_name", u"Адрес узла трассы", u"Адрес узла",
              TEXT, INSTANCE, {"SCS": [GENERIC], "SKUD": [GENERIC]}),
    ParamSpec("addr_prev_param_name", u"Предыдущий адрес (узла трассы / устройства шлейфа)",
              u"Предыдущий адрес", TEXT, INSTANCE,
              dict([("SCS", [GENERIC]), ("SKUD", [GENERIC])] + list(_fire([FIRE_DEVICES]).items())),
              note=u"У СПС/СОУЭ/СПА необязателен"),
    ParamSpec("segment_loads_param", u"Список цепей узла маршрута", u"Цепи узла",
              TEXT, INSTANCE, {"SCS": [GENERIC], "SKUD": [GENERIC]}),
    ParamSpec("offset_param_names", u"Отметка (узлы, устройства, панели)", u"Отметка",
              LENGTH, INSTANCE, {"SCS": [GENERIC] + LV_AND_PANELS, "SKUD": [GENERIC] + LV_AND_PANELS},
              aliases=[u"Смещение", u"Высота установки"],
              is_list=True, note=u"Если в семействах уже есть свой параметр отметки — впишите его имя"),
    ParamSpec("nearest_segment_param", u"Ближайший узел маршрута (у панели/устройства)",
              u"Ближайший узел", TEXT, INSTANCE, {"SCS": LV_AND_PANELS, "SKUD": LV_AND_PANELS}),

    # --- устройства ---
    # СКУД копирует адрес на значок схемы в schematic_address_param — один
    # параметр на устройстве и на значке (СОТ/СПС делают так же одним ключом).
    ParamSpec("device_address_param", u"Адрес устройства (и его значка на схеме)", u"Адрес устройства",
              TEXT, INSTANCE,
              dict([("SCS", LV_DEVICES), ("SKUD", LV_AND_PANELS + [DETAIL]),
                    ("SOT", SOT_SOURCES + [DETAIL]), ("SS1", SS1_ELEMENTS)]
                   + list(_fire(FIRE_AND_PANELS).items())),
              system_keys={"SKUD": ["device_address_param", "schematic_address_param"]}),
    # «Обозначение» — краткий код модели, всегда параметр типа.
    ParamSpec("designation_param", u"Обозначение (у панели и устройств)", u"Обозначение",
              TEXT, TYPE,
              dict([("SCS", LV_DEVICES), ("SKUD", LV_DEVICES)] + list(_fire(FIRE_AND_PANELS).items())),
              aliases=[u"Обозначение типа"]),
    # СКУД: «Маркировка контроллера» и «Марка устройства» — одна роль (копия
    # адреса для плана/спецификации) на контроллере, устройстве и значке схемы.
    ParamSpec("device_marking_param", u"Марка (копия адреса) устройства/контроллера", u"Марка устройства",
              TEXT, INSTANCE,
              dict([("SKUD", LV_AND_PANELS + [DETAIL])] + list(_fire([FIRE_DEVICES]).items())),
              system_keys={"SKUD": ["device_marking_param", "controller_marking_param"]},
              note=u"У СПС/СОУЭ/СПА необязателен"),
    ParamSpec("passage_point_param", u"Номер точки прохода (устройство)", u"Точка прохода",
              TEXT, INSTANCE, {"SKUD": LV_DEVICES},
              note=u"Необязателен: пусто — точка прохода №1"),

    # --- электрические цепи ---
    ParamSpec("circuit_name_type_param", u"Наименование цепи", u"Наименование цепи",
              TEXT, INSTANCE, {"SCS": [CIRCUITS]}),
    ParamSpec("circuit_number_param", u"Номер цепи", u"Номер цепи",
              TEXT, INSTANCE, dict([("SCS", [CIRCUITS])] + list(_fire([CIRCUITS]).items()))),
    ParamSpec("circuit_route_param", u"Маршрут цепи", u"Маршрут цепи",
              TEXT, INSTANCE, dict([("SCS", [CIRCUITS]), ("SKUD", [CIRCUITS])] + list(_fire([CIRCUITS]).items()))),
    ParamSpec("wire_length_param", u"Длина проводника, м", u"Длина проводника",
              NUMBER, INSTANCE, dict([("SCS", [CIRCUITS]), ("SKUD", [CIRCUITS])] + list(_fire([CIRCUITS]).items())),
              aliases=[u"Длина кабеля"],
              note=u"Число, не «Длина»: кнопки пишут метры"),
    ParamSpec("tray_length_param", u"Длина проводника в лотке, м", u"Длина в лотке",
              NUMBER, INSTANCE, dict([("SCS", [CIRCUITS]), ("SKUD", [CIRCUITS])] + list(_fire([CIRCUITS]).items())),
              aliases=[u"Длина проводника в лотке", u"Длина кабеля в лотке"],
              note=u"Число, не «Длина»: кнопки пишут метры"),
    ParamSpec("pipe_length_param", u"Длина проводника в трубе, м", u"Длина в трубе",
              NUMBER, INSTANCE, dict([("SCS", [CIRCUITS]), ("SKUD", [CIRCUITS])] + list(_fire([CIRCUITS]).items())),
              aliases=[u"Длина проводника в трубе", u"Длина кабеля в трубе"],
              note=u"Число, не «Длина»: кнопки пишут метры"),
    ParamSpec("route_method_param", u"Способ прокладки", u"Способ прокладки",
              TEXT, INSTANCE, dict([("SCS", [CIRCUITS]), ("SKUD", [CIRCUITS])] + list(_fire([CIRCUITS]).items()))),

    # --- линии проводки (СПС/СОУЭ/СПА) ---
    ParamSpec("wire_mark_param", u"Марка линии проводки", u"Марка линии",
              TEXT, INSTANCE, dict([("COMPANION", [GENERIC])] + list(_fire([GENERIC]).items())),
              note=u"Необязателен"),

    # --- структурные схемы ---
    ParamSpec("room_param_name", u"Помещение (устройство и его значок на схеме)", u"Помещение",
              TEXT, INSTANCE,
              dict([("SCS", LV_AND_PANELS), ("SOT", SOT_SOURCES + [DETAIL]),
                    ("SOUE_FLOOR", [FIRE_DEVICES, COMM]), ("SS1", SS1_ELEMENTS), ("ROOM_INFO", [])]
                   + list(_fire(FIRE_AND_PANELS + [DETAIL]).items())),
              note=u"Для структурных схем, «Типового этажа», СС1, «Записи помещения»"),
    ParamSpec("level_param_name", u"Уровень на устройстве (для схем)", u"Уровень",
              TEXT, INSTANCE, dict([("SOT", SOT_SOURCES)] + list(_fire([FIRE_DEVICES]).items())),
              note=u"Необязателен: пусто — уровень элемента в Revit"),
    ParamSpec("floor_param_name", u"Этаж элемента («Заполнение этажа», «Проверка LOI»)", u"Этаж",
              TEXT, INSTANCE, {"FLOOR": []},
              note=u"Элементы любых категорий — привяжите к нужным вручную"),
    ParamSpec("building_param_name", u"Корпус на устройстве", u"Корпус",
              TEXT, INSTANCE, dict([("SOT", SOT_SOURCES)] + list(_fire([FIRE_DEVICES]).items())),
              aliases=[u"Здание"],
              note=u"Необязателен"),
    ParamSpec("section_param_name", u"Секция на устройстве", u"Секция",
              TEXT, INSTANCE, {"SOT": SOT_SOURCES}, note=u"Необязателен"),
    # Каждая схема пишет только в свой вид и свои значки, поэтому один
    # параметр на все системы.
    ParamSpec("layout_param_name", u"Служебный: состояние схемы (вид)", u"Раскладка схемы",
              TEXT, INSTANCE,
              dict([("SCS", [VIEWS]), ("SKUD", [VIEWS]), ("SOT", [VIEWS])] + list(_fire([VIEWS]).items())),
              note=_OPTIONAL_SCHEMATIC),
    ParamSpec("device_uid_param_name", u"Служебный: UniqueId устройства (значок схемы)",
              u"UID устройства", TEXT, INSTANCE,
              dict([("SCS", [DETAIL]), ("SKUD", [DETAIL]), ("SOT", [DETAIL])] + list(_fire([DETAIL]).items())),
              note=_OPTIONAL_SCHEMATIC),
]

DEFAULT_PREFIX = u"LL_"
DEFAULT_GROUP = u"LowLife"

# Символы, которые Revit не допускает в имени параметра.
FORBIDDEN_CHARS = u"\\:{}[]|;<>?`~"


# --- строки для окна ---------------------------------------------------------------

class Row(object):
    """
    Строка таблицы окна: роль параметра для выбранных систем. Атрибуты с
    заглавной буквы — для привязки WPF (DataGrid).
    """

    def __init__(self, spec, systems, categories, example, name, source):
        self.spec = spec
        self.key = spec.key
        self.systems = systems
        self.categories = categories
        # Откуда имя: SOURCE_SETTINGS/SOURCE_FOP/SOURCE_EXAMPLE; auto_name —
        # последнее подставленное автоматически (Name != auto_name — правил
        # пользователь, такое имя больше не трогаем).
        self.source = source
        self.auto_name = name
        self.Checked = True
        self.Label = spec.label
        self.Example = example
        self.Name = name
        self.DataType = DATA_TYPE_TITLES.get(spec.data_type, spec.data_type)
        self.Kind = KIND_TITLES.get(spec.kind, spec.kind)
        self.Categories = (u", ".join(CATEGORY_TITLES.get(c, c) for c in categories)
                           or MANUAL_BINDING)
        self.Systems = u", ".join(SYSTEM_TITLES.get(s, s) for s in systems)
        self.Note = spec.note
        self.FopStatus = u""

    def edited(self):
        return _text(self.Name or u"").strip() != _text(self.auto_name or u"").strip()

    def set_auto(self, name, source):
        self.Name = name
        self.auto_name = name
        self.source = source


SOURCE_SETTINGS = "settings"
SOURCE_FOP = "fop"
SOURCE_EXAMPLE = "example"


def example_name(spec, prefix):
    return (prefix or u"") + spec.example


def spec_systems(spec, system_ids):
    """Системы из system_ids (в их порядке в SYSTEMS), которым нужен параметр."""
    chosen = set(system_ids)
    return [s for s in SYSTEM_IDS if s in chosen and s in spec.categories]


def spec_categories(spec, systems):
    """Объединение категорий систем без повторов, в порядке появления."""
    result = []
    for s in systems:
        for c in spec.categories.get(s, []):
            if c not in result:
                result.append(c)
    return result


def split_names(value):
    """Список имён из значения настройки (строка через запятую или список)."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        items = value
    else:
        items = _text(value).split(u",")
    return [_text(v).strip() for v in items if _text(v).strip()]


def saved_name(spec, systems, settings_by_system, shared=None):
    """
    Имя, уже введённое для роли: из файлов настроек систем (по порядку),
    иначе — из общих настроек (LowLifeShared_settings.json), иначе u"".
    У списка имён — первое.
    """
    for s in systems:
        data = settings_by_system.get(s) or {}
        if not isinstance(data, dict):
            continue
        for key in spec.keys_for(s):
            names = split_names(dict.get(data, key))
            if names:
                return names[0]
    shared = shared or {}
    for key in [spec.key] + [k for s in systems for k in spec.keys_for(s)]:
        names = split_names(shared.get(key))
        if names:
            return names[0]
    return u""


def build_rows(system_ids, settings_by_system=None, shared=None, prefix=DEFAULT_PREFIX):
    """Строки окна для выбранных систем, в порядке CATALOG."""
    settings_by_system = settings_by_system or {}
    rows = []
    for spec in CATALOG:
        systems = spec_systems(spec, system_ids)
        if not systems:
            continue
        example = example_name(spec, prefix)
        name = saved_name(spec, systems, settings_by_system, shared)
        source = SOURCE_SETTINGS if name else SOURCE_EXAMPLE
        rows.append(Row(spec, systems, spec_categories(spec, systems), example,
                        name or example, source))
    return rows


def change_prefix(rows, old_prefix, new_prefix):
    """
    Меняет префикс у примеров и у имён, которые пользователь не трогал
    (имя = прежний пример). Свои имена и имена из настроек не меняет.
    """
    for row in rows:
        new_example = example_name(row.spec, new_prefix)
        if row.source == SOURCE_EXAMPLE and not row.edited():
            row.set_auto(new_example, SOURCE_EXAMPLE)
        row.Example = new_example


def name_error(name):
    """Текст ошибки для имени параметра или None."""
    name = _text(name or u"").strip()
    if not name:
        return u"пустое имя"
    bad = [ch for ch in FORBIDDEN_CHARS if ch in name]
    if bad:
        return u"недопустимые символы: {}".format(u" ".join(bad))
    return None


def validate(rows):
    """Ошибки по отмеченным строкам (пустые/недопустимые/повторяющиеся имена)."""
    errors = []
    seen = {}
    for row in rows:
        if not row.Checked:
            continue
        name = _text(row.Name or u"").strip()
        err = name_error(name)
        if err:
            errors.append(u"«{}»: {}".format(row.Label, err))
            continue
        lower = name.lower()
        if lower in seen:
            errors.append(u"«{}» и «{}»: одно и то же имя «{}»".format(seen[lower], row.Label, name))
        else:
            seen[lower] = row.Label
    return errors


def settings_updates(rows, settings_by_system=None):
    """
    {id системы: {ключ: значение}} — что дописать в файлы настроек кнопок
    по отмеченным строкам. Список имён (is_list) — своё имя первым, прежние
    имена после него, без повторов.
    """
    settings_by_system = settings_by_system or {}
    updates = {}
    for row in rows:
        if not row.Checked:
            continue
        name = _text(row.Name or u"").strip()
        if not name:
            continue
        for s in row.systems:
            for key in row.spec.keys_for(s):
                value = name
                if row.spec.is_list:
                    data = settings_by_system.get(s) or {}
                    old = split_names(dict.get(data, key) if isinstance(data, dict) else None)
                    value = u", ".join([name] + [n for n in old if n.lower() != name.lower()])
                updates.setdefault(s, {})[key] = value
    return updates


# --- поиск в ФОП ---------------------------------------------------------------------

class FopDef(object):
    """Определение из файла ФОП: имя, группа, тип данных (TEXT/LENGTH/NUMBER или None — другой)."""

    def __init__(self, name, group, data_type=None):
        self.name = name
        self.group = group
        self.data_type = data_type


def _tokens(name):
    """Слова имени в нижнем регистре (ё = е), без однобуквенных."""
    text = _text(name or u"").lower().replace(u"ё", u"е")
    return [t for t in re.split(u"[^0-9a-zа-я]+", text) if len(t) > 1]


def _stem(token):
    """Грубая основа слова: без двух последних букв у длинных слов."""
    return token if len(token) <= 4 else token[:max(len(token) - 2, 3)]


def _same_word(a, b):
    """Одно слово в разных формах («проводника»/«проводник»); короткие — только точно."""
    if a == b:
        return True
    sa, sb = _stem(a), _stem(b)
    if min(len(sa), len(sb)) < 3:
        return False
    return sa.startswith(sb) or sb.startswith(sa)


def _patterns(spec):
    return [_tokens(spec.example)] + [_tokens(a) for a in spec.aliases]


def _spec_words(spec):
    words = []
    for pattern in _patterns(spec):
        words.extend(pattern)
    return words


def _other_words(spec):
    """Слова примеров других ролей, которых нет у этой — по ним роли различаются."""
    own = _spec_words(spec)
    result = []
    for other in CATALOG:
        if other is spec:
            continue
        for w in _spec_words(other):
            if not any(_same_word(w, o) for o in own):
                result.append(w)
    return result


def similarity(spec, name):
    """
    Насколько имя name из ФОП похоже на роль spec: None — не похоже, иначе
    число лишних слов (меньше — лучше). Похоже — все слова примера (или
    одного из aliases) есть в имени, а лишних слов, отличающих другую роль
    («лотке», «схеме», «типа»…), нет; префикс проекта («ADSK_») — просто
    лишнее слово.
    """
    words = _tokens(name)
    if not words:
        return None
    others = _other_words(spec)
    best = None
    for pattern in _patterns(spec):
        if not pattern:
            continue
        if not all(any(_same_word(p, w) for w in words) for p in pattern):
            continue
        extras = [w for w in words if not any(_same_word(w, p) for p in pattern)]
        if any(any(_same_word(e, o) for o in others) for e in extras):
            continue
        if best is None or len(extras) < best:
            best = len(extras)
    return best


def find_exact(fop_defs, name):
    lower = _text(name or u"").strip().lower()
    for d in fop_defs:
        if d.name.lower() == lower:
            return d
    return None


def match_fop(rows, fop_defs):
    """
    Подставляет в строки похожие параметры из ФОП. Не трогает имена из
    настроек кнопок и правленые пользователем (их имена, если они есть в
    ФОП, другим строкам не достаются). Каждое определение ФОП — не больше
    чем в одну строку; сначала самые похожие с подходящим типом данных.
    Строка без похожего — снова с примером.
    """
    taken = set()
    free = []
    for row in rows:
        if row.source == SOURCE_SETTINGS or row.edited():
            exact = find_exact(fop_defs, row.Name)
            if exact is not None:
                taken.add(exact.name.lower())
            continue
        free.append(row)

    candidates = []
    for row in free:
        for d in fop_defs:
            score = similarity(row.spec, d.name)
            if score is None:
                continue
            type_penalty = 0 if d.data_type in (None, row.spec.data_type) else 1
            candidates.append(((type_penalty, score), row, d))
    candidates.sort(key=lambda c: c[0])

    matched = {}
    for _score, row, d in candidates:
        if row.key in matched or d.name.lower() in taken:
            continue
        matched[row.key] = d
        taken.add(d.name.lower())

    for row in free:
        d = matched.get(row.key)
        if d is not None:
            row.set_auto(d.name, SOURCE_FOP)
        elif row.source == SOURCE_FOP:
            row.set_auto(row.Example, SOURCE_EXAMPLE)


def update_status(rows, fop_defs, write_fop=False):
    """
    Столбец «В ФОП»: есть ли там параметр с текущим именем строки. Нет —
    при write_fop будет создан, иначе строка пропускается (если параметра
    нет и в проекте).
    """
    for row in rows:
        d = find_exact(fop_defs, row.Name)
        if d is None:
            row.FopStatus = u"нет — будет создан" if write_fop else u"нет — не создаётся"
            continue
        status = u"есть, группа «{}»".format(d.group)
        if row.source == SOURCE_FOP and not row.edited():
            status = u"найден похожий, группа «{}»".format(d.group)
        if d.data_type != row.spec.data_type:
            status += u"; тип в ФОП не «{}»".format(DATA_TYPE_TITLES[row.spec.data_type])
        row.FopStatus = status
