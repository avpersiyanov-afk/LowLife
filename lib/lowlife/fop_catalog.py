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
]

SYSTEM_IDS = [s[0] for s in SYSTEMS]
SYSTEM_TITLES = dict((s[0], s[1]) for s in SYSTEMS)
SYSTEM_FILES = dict((s[0], s[2]) for s in SYSTEMS)

FIRE = ("SPS", "SOUE", "SPA")


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


def _fire(categories):
    return dict((s, categories) for s in FIRE)


# --- каталог ---------------------------------------------------------------------

class ParamSpec(object):
    """
    Одна роль параметра.

    key        — ключ в файлах настроек кнопок.
    label      — что это за параметр (подпись в окне).
    example    — пример имени без префикса (окно добавляет префикс).
    data_type  — TEXT/LENGTH/NUMBER (тип нового определения в ФОП).
    kind       — INSTANCE/TYPE.
    categories — {id системы: [имена BuiltInCategory]}.
    native     — обычно это штатный параметр Revit (не из ФОП): в окне
                 строка по умолчанию не отмечена, пример — имя штатного
                 параметра, без префикса.
    is_list    — в настройках список имён через запятую (своё имя ставится
                 первым, остальные сохраняются).
    note       — пояснение (необязательность и т. п.).
    """

    def __init__(self, key, label, example, data_type, kind, categories,
                 native=False, is_list=False, note=u""):
        self.key = key
        self.label = label
        self.example = example
        self.data_type = data_type
        self.kind = kind
        self.categories = categories
        self.native = native
        self.is_list = is_list
        self.note = note


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
              is_list=True, note=u"Если в семействах уже есть свой параметр отметки — впишите его имя"),
    ParamSpec("nearest_segment_param", u"Ближайший узел маршрута (у панели/устройства)",
              u"Ближайший узел", TEXT, INSTANCE, {"SCS": LV_AND_PANELS, "SKUD": LV_AND_PANELS}),

    # --- устройства ---
    ParamSpec("device_address_param", u"Адрес устройства", u"Адрес устройства",
              TEXT, INSTANCE,
              dict([("SCS", LV_DEVICES), ("SKUD", LV_AND_PANELS)] + list(_fire(FIRE_AND_PANELS).items()))),
    ParamSpec("type_code_param", u"Обозначение типа устройства", u"Обозначение типа",
              TEXT, TYPE, {"SCS": LV_DEVICES, "SKUD": LV_DEVICES}),
    ParamSpec("designation_param", u"Обозначение (у панели и устройств)", u"Обозначение",
              TEXT, INSTANCE, _fire(FIRE_AND_PANELS)),
    ParamSpec("controller_marking_param", u"Маркировка контроллера", u"Маркировка контроллера",
              TEXT, INSTANCE, {"SKUD": [EQUIPMENT]}),
    ParamSpec("device_marking_param", u"Марка устройства", u"Марка устройства",
              TEXT, INSTANCE, dict([("SKUD", LV_DEVICES)] + list(_fire([FIRE_DEVICES]).items())),
              note=u"У СПС/СОУЭ/СПА необязателен"),
    ParamSpec("schematic_address_param", u"Адрес устройства на схеме", u"Адрес на схеме",
              TEXT, INSTANCE, {"SKUD": [GENERIC]}),
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
              note=u"Число, не «Длина»: кнопки пишут метры"),
    ParamSpec("tray_length_param", u"Длина проводника в лотке, м", u"Длина в лотке",
              NUMBER, INSTANCE, dict([("SCS", [CIRCUITS]), ("SKUD", [CIRCUITS])] + list(_fire([CIRCUITS]).items())),
              note=u"Число, не «Длина»: кнопки пишут метры"),
    ParamSpec("pipe_length_param", u"Длина проводника в трубе, м", u"Длина в трубе",
              NUMBER, INSTANCE, dict([("SCS", [CIRCUITS]), ("SKUD", [CIRCUITS])] + list(_fire([CIRCUITS]).items())),
              note=u"Число, не «Длина»: кнопки пишут метры"),
    ParamSpec("route_method_param", u"Способ прокладки", u"Способ прокладки",
              TEXT, INSTANCE, dict([("SCS", [CIRCUITS]), ("SKUD", [CIRCUITS])] + list(_fire([CIRCUITS]).items()))),
    ParamSpec("circuit_panel_param", u"Панель цепи", u"Панель",
              TEXT, INSTANCE, dict([("SCS", [CIRCUITS]), ("SKUD", [CIRCUITS])] + list(_fire([CIRCUITS]).items())),
              native=True, note=u"Обычно штатный параметр Revit «Панель»"),
    ParamSpec("load_name_param", u"Имя нагрузки цепи", u"Имя нагрузки",
              TEXT, INSTANCE, dict([("SCS", [CIRCUITS]), ("SKUD", [CIRCUITS])] + list(_fire([CIRCUITS]).items())),
              native=True, note=u"Обычно штатный параметр Revit «Имя нагрузки»"),
    ParamSpec("cable_type_param", u"Проводник (тип кабеля цепи)", u"Проводник",
              TEXT, INSTANCE, dict([("SKUD", [CIRCUITS])] + list(_fire([CIRCUITS]).items())),
              native=True, note=u"Обычно штатный параметр Revit «Проводник»"),

    # --- линии проводки (СПС/СОУЭ/СПА) ---
    ParamSpec("wire_mark_param", u"Марка линии проводки", u"Марка линии",
              TEXT, INSTANCE, _fire([GENERIC]), note=u"Необязателен"),

    # --- структурные схемы ---
    ParamSpec("room_param_name", u"Помещение (устройство и его значок на схеме)", u"Помещение",
              TEXT, INSTANCE,
              dict([("SCS", LV_AND_PANELS), ("SOT", SOT_SOURCES + [DETAIL])]
                   + list(_fire(FIRE_AND_PANELS + [DETAIL]).items())),
              note=_OPTIONAL_SCHEMATIC),
    ParamSpec("address_param_name", u"Адрес камеры/устройства СОТ", u"Адрес СОТ",
              TEXT, INSTANCE, {"SOT": SOT_SOURCES + [DETAIL]}),
    ParamSpec("level_param_name", u"Уровень (этаж) на устройстве", u"Этаж",
              TEXT, INSTANCE, dict([("SOT", SOT_SOURCES)] + list(_fire([FIRE_DEVICES]).items())),
              note=u"Необязателен: пусто — уровень элемента в Revit"),
    ParamSpec("building_param_name", u"Корпус на устройстве", u"Корпус",
              TEXT, INSTANCE, dict([("SOT", SOT_SOURCES)] + list(_fire([FIRE_DEVICES]).items())),
              note=u"Необязателен"),
    ParamSpec("section_param_name", u"Секция на устройстве", u"Секция",
              TEXT, INSTANCE, {"SOT": SOT_SOURCES}, note=u"Необязателен"),
    ParamSpec("layout_param_name", u"Служебный: раскладка схемы (вид)", u"Раскладка схемы",
              TEXT, INSTANCE, dict([("SCS", [VIEWS]), ("SOT", [VIEWS])] + list(_fire([VIEWS]).items())),
              note=_OPTIONAL_SCHEMATIC),
    ParamSpec("device_uid_param_name", u"Служебный: UniqueId устройства (значок схемы)",
              u"UID устройства", TEXT, INSTANCE,
              dict([("SCS", [DETAIL]), ("SOT", [DETAIL])] + list(_fire([DETAIL]).items())),
              note=_OPTIONAL_SCHEMATIC),
    ParamSpec("manifest_param_name", u"Служебный: манифест схемы СКУД (вид)", u"Манифест схемы",
              TEXT, INSTANCE, {"SKUD": [VIEWS]}, note=_OPTIONAL_SCHEMATIC),
    ParamSpec("schematic_source_uid_param", u"Служебный: UniqueId устройства (значок схемы СКУД)",
              u"UID устройства СКУД", TEXT, INSTANCE, {"SKUD": [DETAIL]},
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

    def __init__(self, spec, systems, categories, example, name, checked):
        self.spec = spec
        self.key = spec.key
        self.systems = systems
        self.categories = categories
        self.Checked = checked
        self.Label = spec.label
        self.Example = example
        self.Name = name
        self.DataType = DATA_TYPE_TITLES.get(spec.data_type, spec.data_type)
        self.Kind = KIND_TITLES.get(spec.kind, spec.kind)
        self.Categories = u", ".join(CATEGORY_TITLES.get(c, c) for c in categories)
        self.Systems = u", ".join(SYSTEM_TITLES.get(s, s) for s in systems)
        self.Note = spec.note


def example_name(spec, prefix):
    """Пример имени: у штатных параметров Revit — без префикса."""
    if spec.native:
        return spec.example
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
        names = split_names(dict.get(data, spec.key) if isinstance(data, dict) else None)
        if names:
            return names[0]
    names = split_names((shared or {}).get(spec.key))
    return names[0] if names else u""


def build_rows(system_ids, settings_by_system=None, shared=None, prefix=DEFAULT_PREFIX):
    """Строки окна для выбранных систем, в порядке CATALOG."""
    settings_by_system = settings_by_system or {}
    rows = []
    for spec in CATALOG:
        systems = spec_systems(spec, system_ids)
        if not systems:
            continue
        example = example_name(spec, prefix)
        name = saved_name(spec, systems, settings_by_system, shared) or example
        rows.append(Row(spec, systems, spec_categories(spec, systems), example, name,
                        checked=not spec.native))
    return rows


def change_prefix(rows, old_prefix, new_prefix):
    """
    Меняет префикс у примеров и у имён, которые пользователь не трогал
    (имя = прежний пример). Свои имена и имена из настроек не меняет.
    """
    for row in rows:
        old_example = example_name(row.spec, old_prefix)
        new_example = example_name(row.spec, new_prefix)
        if _text(row.Name or u"").strip() == old_example:
            row.Name = new_example
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
            value = name
            if row.spec.is_list:
                data = settings_by_system.get(s) or {}
                old = split_names(dict.get(data, row.key) if isinstance(data, dict) else None)
                value = u", ".join([name] + [n for n in old if n.lower() != name.lower()])
            updates.setdefault(s, {})[row.key] = value
    return updates
