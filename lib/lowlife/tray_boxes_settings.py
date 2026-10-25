# -*- coding: utf-8 -*-
"""
Настройки кнопки «Боксы на лотки» (Tools.panel/TrayOpeningBoxes) + их
хранение между запусками (%APPDATA%\\pyRevit\\LowLifeTrayBoxes_settings.json).

Обвязка (хранение, окно, Shift+клик/тихий режим) — общая,
settings_core.TextSettings; здесь только описание полей. Имена параметров
размеров — параметры самого семейства бокса (экземпляра или типа); по
умолчанию — обычные «Ширина»/«Глубина»/«Высота».
"""

from lowlife import settings_core
from lowlife.i18n import tr


HOSTS_ALL = "walls_floors"
HOSTS_WALLS = "walls"
HOSTS_FLOORS = "floors"

ORIGIN_CENTER = "center"
ORIGIN_BOTTOM = "bottom"

# Модель, где искать пересечения: эта модель, все сразу или одна связь
# (значение — имя файла связи, Title её документа).
SOURCE_HOST = "__host__"
SOURCE_ALL = "__all__"


class SourceField(settings_core.ChoiceField):
    u"""Выбор модели. Варианты-связи берутся из открытой модели (окно
    строится заново при каждом Shift+клике), поэтому сохранённое имя связи,
    которой сейчас нет в списке, не сбрасывается на умолчание."""

    def coerce(self, value):
        return value or self.default


def _source_field(link_titles):
    choices = [(SOURCE_HOST, u"Только эта модель"),
               (SOURCE_ALL, u"Эта модель и все загруженные связи")]
    choices += [(title, tr(u"Связь «{}»").format(title)) for title in link_titles]
    return SourceField(
        "box_source_model",
        u"④ Где искать пересечения",
        u"Модель",
        choices,
        hint=(
            u"В какой модели искать стены и перекрытия, сквозь которые проходят лотки: "
            u"в этой, в одной из загруженных связей (например, АР или КР) или везде."
        ),
        default=SOURCE_ALL,
    )


def _migrate(saved, values):
    u"""Старая настройка «искать в связях: да/нет» → модель."""
    if not saved.get("box_source_model") and saved.get("box_use_links") == "no":
        values["box_source_model"] = SOURCE_HOST


def link_titles(doc):
    u"""Имена файлов загруженных связей (без повторов), по алфавиту."""
    from Autodesk.Revit.DB import FilteredElementCollector, RevitLinkInstance
    titles = set()
    for link in FilteredElementCollector(doc).OfClass(RevitLinkInstance):
        link_doc = link.GetLinkDocument()
        if link_doc is not None and link_doc.Title:
            titles.add(link_doc.Title)
    return sorted(titles, key=lambda t: t.lower())


def _make_settings(titles):
    return settings_core.TextSettings(
        file_name="LowLifeTrayBoxes_settings.json",
        button_name=u"Боксы на лотки",
        heading=u"Боксы на пересечениях лотков",
        transfer_label=u"кнопки «Боксы на лотки»",
        fields=[
            settings_core.TextField(
                "box_family_words",
                u"① Семейство бокса",
                u"Слова в имени семейства (через запятую)",
                hint=u"Берутся загруженные семейства, в имени которых есть хотя бы одно слово (без учёта регистра).",
                default=u"бокс",
            ),
            settings_core.TextField(
                "box_type_words",
                u"",
                u"Слова в имени типа (через запятую)",
                hint=u"Из подходящих семейств — типы, в имени которых есть хотя бы одно слово. Несколько — кнопка спросит.",
                default=u"временный",
            ),
            settings_core.TextField(
                "box_workset_words",
                u"",
                u"Рабочий набор боксов — слова в имени (через запятую)",
                hint=(
                    u"Боксы создаются в рабочем наборе, в имени которого есть хотя бы одно слово "
                    u"(без учёта регистра); несколько подходящих — кнопка спросит. Пусто — в "
                    u"активном рабочем наборе. В модели без рабочих наборов не используется."
                ),
                default=u"боксы",
            ),
            settings_core.ChoiceField(
                "box_origin",
                u"",
                u"Точка вставки семейства",
                [(ORIGIN_CENTER, u"В середине бокса"),
                 (ORIGIN_BOTTOM, u"В середине низа бокса")],
                hint=u"Где у семейства бокса точка вставки — от этого зависит, куда его ставить по высоте.",
                default=ORIGIN_CENTER,
            ),
            settings_core.TextField(
                "box_width_param",
                u"② Параметры размеров бокса",
                u"Ширина (вдоль оси X семейства)",
                hint=u"В стене — вдоль стены, в перекрытии — вдоль ширины лотка.",
                default=u"Ширина",
            ),
            settings_core.TextField(
                "box_depth_param",
                u"",
                u"Глубина (вдоль оси Y семейства)",
                hint=u"В стене — по толщине стены, в перекрытии — вдоль высоты лотка.",
                default=u"Глубина",
            ),
            settings_core.TextField(
                "box_height_param",
                u"",
                u"Высота (вдоль оси Z семейства)",
                hint=(
                    u"В стене — по высоте лотка, в перекрытии — по толщине перекрытия. "
                    u"Если параметр — параметр типа, кнопка создаёт типоразмер под размер "
                    u"(«<тип> ШxГxВ»)."
                ),
                default=u"Высота",
            ),
            settings_core.NumberField(
                "size_extra_mm",
                u"③ Размеры",
                u"Бокс больше сечения лотка на, мм",
                hint=u"Добавляется к ширине и к высоте лотка (всего, не с каждой стороны).",
                default=50.0, minimum=0.0,
            ),
            settings_core.NumberField(
                "depth_extra_mm",
                u"",
                u"Бокс толще стены/перекрытия на, мм",
                hint=u"0 — глубина бокса ровно по толщине стены или перекрытия.",
                default=0.0, minimum=0.0,
            ),
            settings_core.ChoiceField(
                "box_hosts",
                u"⑤ Что пересекать",
                u"Элементы",
                [(HOSTS_ALL, u"Стены и перекрытия"),
                 (HOSTS_WALLS, u"Только стены"),
                 (HOSTS_FLOORS, u"Только перекрытия")],
                default=HOSTS_ALL,
            ),
            _source_field(titles),
            settings_core.NumberField(
                "max_slope_deg",
                u"",
                u"Допуск наклона лотка, градусы",
                hint=(
                    u"Сквозь стену — только горизонтальные лотки, сквозь перекрытие — только "
                    u"вертикальные (отклонение не больше допуска)."
                ),
                default=1.0, minimum=0.0,
            ),
            settings_core.NumberField(
                "max_wall_angle_deg",
                u"",
                u"Наибольший угол между лотком и перпендикуляром к стене, градусы",
                hint=u"Лотки, идущие сквозь стену наискось сильнее, пропускаются (бокс вышел бы слишком длинным).",
                default=60.0, minimum=0.0,
            ),
        ],
        width=760, height=640,
        migrate=_migrate,
    )


SETTINGS = _make_settings([])


load_saved_values = SETTINGS.load_saved_values
save_values = SETTINGS.save_values
require = SETTINGS.require
show_settings_form = SETTINGS.show_settings_form


def get_settings_interactive(doc=None):
    u"""Окно настроек; в списке моделей — связи, загруженные в doc (и
    сохранённая связь, даже если сейчас не загружена)."""
    titles = link_titles(doc) if doc is not None else []
    saved = SETTINGS.load_saved_values().get("box_source_model")
    if saved not in (SOURCE_HOST, SOURCE_ALL) and saved and saved not in titles:
        titles.append(saved)
    return _make_settings(titles).get_settings_interactive()


get_settings_silent = SETTINGS.get_settings_silent
