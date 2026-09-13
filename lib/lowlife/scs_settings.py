# -*- coding: utf-8 -*-
"""
Окно настроек параметров СКС + их хранение между запусками.

Хранится в обычном JSON-файле в %APPDATA%\\pyRevit\\LowLifeSCS_settings.json
(см. _settings_file_path) — простой и однозначно проверяемый способ,
без зависимости от внутреннего API pyrevit.script.get_config()/save_config()
(на практике не гарантированно расшаривавшего секцию между разными
script.py одного расширения).

Значения общие для всех кнопок SCS.panel — сохраняются в одном файле,
поэтому достаточно настроить один раз.
"""

import os
import io
import json

import clr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('RevitAPI')

from Autodesk.Revit.DB import (
    ElementId, FilteredElementCollector, Family, BuiltInCategory, Element, GroupType
)

from pyrevit import forms

from System.Windows import (
    Window, WindowStartupLocation, Thickness,
    FontWeights, HorizontalAlignment, VerticalAlignment, TextWrapping
)
from System.Windows.Controls import (
    StackPanel, TextBlock, TextBox, Button, Orientation, DockPanel, Dock, ScrollViewer,
    ScrollBarVisibility
)
from System.Windows.Media import Brushes

from lowlife import scs as scs_defaults
from lowlife import settings_transfer
from lowlife.skud import parse_category_names

SETTINGS_FILE_NAME = "LowLifeSCS_settings.json"

# (ключ, подпись в окне, пояснение простым языком, значение по умолчанию,
#  список ли это через запятую, обязательное ли поле, многострочное ли поле)
TEXT_FIELDS = [
    ("family_filter", u"Фильтр семейства сегментов трассы",
        u"Часть имени семейства линии трассы (line-based Generic Model) на плане — "
        u"например «Трасса». Только линии, у которых имя семейства содержит эту "
        u"подстроку, считаются трассой и участвуют в расстановке узлов.",
        scs_defaults.FAMILY_FILTER, False, True, False),
    ("cable_param_name", u"Параметр «Тип прокладки кабеля»",
        u"Имя текстового параметра, в который узлы маршрута и панели/стояки "
        u"записывают способ прокладки — «Лоток», «Труба» или «Труба открыто». По "
        u"значению этого параметра дальше считается длина в трубе/лотке и "
        u"применяются коэффициенты запаса.",
        scs_defaults.CABLE_PARAM_NAME, False, True, False),
    ("route_param_name", u"Параметр «Тип трассы»",
        u"Имя параметра, в который при расстановке узлов записывается значение из "
        u"двух следующих полей — просто отметка «это узел трассы СКС», по которой "
        u"такие элементы можно отличить и отфильтровать в спецификациях.",
        scs_defaults.ROUTE_PARAM_NAME, False, True, False),
    ("route_param_value", u"Значение параметра «Тип трассы» (не для стояков)",
        u"Что записывается в параметр «Тип трассы» у обычных узлов маршрута и "
        u"панелей (кроме стояков) — например «СКС». Само значение может быть "
        u"любым, лишь бы отличалось от значения для стояков ниже.",
        scs_defaults.ROUTE_PARAM_VALUE, False, True, False),
    ("route_param_value_riser", u"Значение параметра «Тип трассы» для стояков",
        u"То же самое, но записывается только узлам-стоякам — например «СКС "
        u"стояк». Позволяет отличить стояк от обычного узла трассы по значению "
        u"параметра, а не только по типоразмеру.",
        scs_defaults.ROUTE_PARAM_VALUE_RISER, False, True, False),
    ("device_cable_type_value", u"Тип прокладки кабеля для панелей и стояков",
        u"Значение, которое кнопка «Узлы трассы» принудительно проставляет "
        u"панелям и стоякам в параметр «Тип прокладки кабеля» (например «Труба») "
        u"— последний отрезок до шкафа или ввод в стояк считается трубой "
        u"независимо от того, чем на самом деле проложена трасса рядом.",
        scs_defaults.DEVICE_CABLE_TYPE_VALUE, False, True, False),
    ("riser_keywords", u"Ключевые слова стояков (через запятую)",
        u"Слова, по которым устройство или аннотация на плане распознаются как "
        u"стояк — по имени семейства/типа, например «стояк». Через запятую, если "
        u"вариантов написания несколько.",
        u", ".join(scs_defaults.RISER_KEYWORDS), True, False, False),
    ("riser_exclude_keywords", u"Слова-исключения стояков (через запятую)",
        u"Если одно из этих слов встречается в имени элемента, он НЕ считается "
        u"стояком, даже если рядом есть слово из «Ключевые слова стояков» выше — "
        u"нужно для похожих по названию, но не относящихся к стояку элементов.",
        u", ".join(scs_defaults.RISER_EXCLUDE_KEYWORDS), True, False, False),
    ("riser_annotation_keywords", u"Ключевые слова аннотации стояка (через запятую)",
        u"Слова для распознавания типовой аннотации стояка (стрелки подъёма/"
        u"опуска на плане) — отдельно от «Ключевые слова стояков», потому что имя "
        u"типа такой аннотации обычно не содержит слова «стояк». Если на этаже "
        u"стояк отмечен только такой аннотацией, узел всё равно будет расставлен "
        u"— на условной высоте +3000 мм от уровня вида.",
        u", ".join(scs_defaults.RISER_ANNOTATION_KEYWORDS), True, False, False),
    ("offset_param_names", u"Возможные имена параметра отметки (через запятую)",
        u"Варианты имени параметра «Смещение» у линии трассы или у устройства-"
        u"стояка — перечислите через запятую все, что встречаются в проекте "
        u"(используется первый найденный). Значение переносится на созданный "
        u"узел маршрута, чтобы марка узла показывала верную высотную отметку.",
        u", ".join(scs_defaults.OFFSET_PARAM_NAMES), True, True, False),

    # --- адресация узлов (RenumberAddresses) ---
    ("addr_param_name", u"[Адресация] Параметр «Адрес узла»",
        u"Текстовый параметр, в который кнопка «Адреса узлов» записывает адрес "
        u"узла/панели/стояка (например «F1.12», «F1.P1») — по нему строится весь "
        u"граф трассы: без заполненного адреса узел в расчёт не попадает.",
        u"", False, True, False),
    ("addr_prev_param_name", u"[Адресация] Параметр «Предыдущий адрес»",
        u"Текстовый параметр, в который записывается адрес РОДИТЕЛЬСКОГО узла (в "
        u"сторону панели) — этим узлы соединяются друг с другом в цепочку/дерево. "
        u"У панелей и стояков (корней дерева) он не заполняется.",
        u"", False, True, False),

    # --- критерии определения панели/шкафа — используются РАЗНЫМИ кнопками
    # для РАЗНЫХ целей (см. пояснение в окне настроек): ключевые слова —
    # для расстановки узлов и корней адресации (PlaceRouteNodes/
    # RenumberAddresses), рабочий набор — для выбора целевых панелей,
    # для которых считаются цепи (SyncCircuitsAndLengths). Элемент должен
    # подходить под оба критерия, чтобы полноценно участвовать во всех
    # трёх кнопках — если что-то из этого не работает, проверьте оба поля.
    ("panel_keywords", u"[Критерии панели] Ключевые слова панелей (через запятую)",
        u"Слова, по которым устройство на плане распознаётся как панель/шкаф для "
        u"расстановки узлов и как корень адресации (кнопки «Узлы трассы» и "
        u"«Адреса узлов»). Порядок важен: если на этаже несколько видов «панелей», "
        u"корнем адресации становится только тот вид, чьё слово стоит в списке "
        u"раньше.",
        u", ".join(scs_defaults.PANEL_KEYWORDS), True, False, False),
    ("panel_exclude_keywords", u"[Критерии панели] Слова-исключения панелей (через запятую)",
        u"Если одно из этих слов встречается в имени элемента, он не считается "
        u"панелью, даже если рядом есть слово из «Ключевые слова панелей» выше.",
        u", ".join(scs_defaults.PANEL_EXCLUDE_KEYWORDS), True, False, False),
    ("workset_param_name", u"[Критерии панели] Параметр рабочего набора элемента",
        u"Имя обычного параметра, в который в проекте дополнительно продублировано "
        u"название рабочего набора элемента (если такого параметра нет — "
        u"рабочий набор определяется штатным способом Revit, поле можно оставить "
        u"как есть).",
        u"Рабочий набор", False, True, False),
    ("workset_filter_key", u"[Критерии панели] Ключевое слово рабочего набора целевых панелей",
        u"Слово в названии рабочего набора нужных панелей/шкафов (например "
        u"«СКС») — по нему кнопки «Расчёт длины цепи», «Адреса узлов» и "
        u"«Структурная схема» отбирают, какие панели считать целевыми.",
        u"", False, True, False),

    # --- расчёт цепей и длин (SyncCircuitsAndLengths) ---
    ("excluded_device_keywords", u"[Цепи] Ключевые слова резервных портов, исключаемых из расчёта (через запятую)",
        u"Если в имени семейства устройства/порта встретилось одно из этих слов "
        u"(например «резерв»), оно не считается конечным устройством цепи и не "
        u"участвует ни в расчёте длины, ни в адресации — для запасных портов "
        u"панели.",
        u"", True, False, False),
    ("circuit_panel_param", u"[Цепи] Параметр цепи «Панель»",
        u"Параметр электрической цепи Revit, в котором записано имя её панели/"
        u"щита — по значению этого параметра цепь сопоставляется с элементом-"
        u"панелью на модели (сравнение идёт по имени, а не по Id).",
        u"", False, True, False),
    ("nearest_segment_param", u"[Цепи] Параметр «Ближайший узел маршрута» (у панелей и устройств)",
        u"Параметр (заполняется у панели и у устройства кнопкой «Адреса узлов»), "
        u"в котором хранится адрес ближайшего к нему узла маршрута — именно от "
        u"этих адресов «Расчёт длины цепи» начинает и заканчивает прокладку пути "
        u"каждой цепи.",
        u"", False, True, False),
    ("device_address_param", u"[Цепи] Параметр устройства «Адрес устройства»",
        u"Параметр устройства с его собственным адресом — его значение "
        u"подставляется в имя нагрузки цепи вместе с «Обозначением» типа "
        u"устройства, чтобы у каждой цепи было понятное человекочитаемое имя "
        u"нагрузки, а не просто номер.",
        u"", False, True, False),
    ("type_code_param", u"[Цепи] Параметр типа устройства «Обозначение»",
        u"Параметр типа устройства (в некоторых проектах — параметр экземпляра, "
        u"тогда программа при пустом результате на типе читает то же имя прямо с "
        u"устройства) с кратким буквенным обозначением — например «Р» для "
        u"розетки. Вместе с адресом устройства из него собирается имя нагрузки "
        u"цепи.",
        u"", False, True, False),
    ("circuit_name_type_param", u"[Цепи] Параметр цепи «Наименование» (для определения типа цепи)",
        u"Параметр цепи, по словам-признакам в значении которого (см. три поля "
        u"«Ключевое слово типа цепи…» ниже) определяется, оптическая это цепь, "
        u"витая пара или силовая — от этого зависит, как считается и "
        u"подписывается её длина.",
        u"", False, True, False),
    ("circuit_number_param", u"[Цепи] Параметр цепи «Номер цепи»",
        u"Параметр, в который пишется порядковый номер вида «FO-1», «PWR-2» для "
        u"оптических и силовых цепей целевых панелей, а также используется как "
        u"имя цепи в списке нагрузок узла, если у цепи ещё нет имени нагрузки.",
        u"", False, True, False),
    ("circuit_route_param", u"[Цепи] Параметр цепи «Маршрут цепи»",
        u"Параметр, в который записывается полный путь цепи — список адресов "
        u"узлов маршрута через «->», от панели до устройства. По этим данным "
        u"кнопка «Маршрут цепи» рисует цепь на плане для проверки.",
        u"", False, True, False),
    ("wire_length_param", u"[Цепи] Параметр цепи «Длина проводника»",
        u"Параметр итоговой полной длины кабеля цепи (с учётом коэффициентов "
        u"запаса) — сюда пишется сумма длин в лотке, трубе и трубе открыто.",
        u"", False, True, False),
    ("tray_length_param", u"[Цепи] Параметр цепи «Длина проводника в лотке»",
        u"Часть общей длины цепи, посчитанная как проложенная по лотку (с "
        u"коэффициентом запаса «Лоток» из поля ниже).",
        u"", False, True, False),
    ("pipe_length_param", u"[Цепи] Параметр цепи «Длина проводника в трубе»",
        u"Часть общей длины цепи, посчитанная как проложенная в трубе — сюда "
        u"пишется сумма длины в обычной трубе и в трубе открыто (обе физически "
        u"прокладываются в трубе, просто с разным коэффициентом запаса).",
        u"", False, True, False),
    ("route_method_param", u"[Цепи] Параметр цепи «Способ прокладки»",
        u"Параметр текстовой подписи вида «Труба: 12.3 м; Лоток: 5.0 м» — "
        u"собирается из трёх форматов меток ниже, только для тех способов "
        u"прокладки, которые реально встретились на пути этой цепи.",
        u"", False, True, False),
    ("load_name_param", u"[Цепи] Параметр цепи «Имя нагрузки»",
        u"Параметр, в который пишется имя нагрузки, собранное из обозначения "
        u"типа устройства и его адреса (например «Р.F1.12»). Для оптических "
        u"цепей не заполняется.",
        u"", False, True, False),
    ("wire_catalog_marker_param", u"[Цепи] Параметр-признак строки справочника кабелей",
        u"Необязательно. Имя параметра, который есть только у нужных строк "
        u"вашей ключевой спецификации кабелей — по нему программа отличает их от "
        u"остальных элементов проекта, когда показывает список кабелей для "
        u"выбора в разделе «Проводник для цепей СКС» ниже.",
        u"", False, False, False),
    ("segment_loads_param", u"[Цепи] Параметр узла маршрута «Список цепей»",
        u"Параметр узла маршрута, в который записывается текстовый список всех "
        u"цепей (и счётчик оптических/UTP), проходящих через этот узел — удобно "
        u"для проверки загрузки трассы прямо на плане, без открытия каждой цепи.",
        u"", False, True, False),
    ("install_tray_key", u"[Цепи] Значение «Тип прокладки» = лоток",
        u"Слово, которое ищется в параметре «Тип прокладки кабеля» узла, чтобы "
        u"считать этот участок трассы проложенным по лотку — должно точно "
        u"совпадать с тем, как лоток называется в вашем проекте (например "
        u"«Лоток»).",
        u"Лоток", False, True, False),
    ("install_pipe_key", u"[Цепи] Значение «Тип прокладки» = труба",
        u"То же самое для трубы — участок с таким словом в «Тип прокладки "
        u"кабеля» считается проложенным в трубе.",
        u"Труба", False, True, False),
    ("install_pipe_open_key", u"[Цепи] Значение «Тип прокладки» = труба открыто",
        u"То же самое для открыто проложенной трубы (например по стене без "
        u"штробы) — отдельная категория от обычной трубы, у неё свой коэффициент "
        u"запаса и своя метка.",
        u"Труба открыто", False, True, False),
    ("route_label_pipe_format", u"[Цепи] Формат метки трубы (используйте {} для метров)",
        u"Шаблон текста для параметра «Способ прокладки», например «Труба {} "
        u"м» — {} заменяется на посчитанную длину в трубе. Оставьте пустым, если "
        u"эту часть маршрута не нужно показывать в метке.",
        u"", False, True, False),
    ("route_label_tray_format", u"[Цепи] Формат метки лотка (используйте {} для метров)",
        u"То же самое для лотка, например «Лоток {} м».",
        u"", False, True, False),
    ("route_label_pipe_open_format", u"[Цепи] Формат метки трубы открыто (используйте {} для метров)",
        u"То же самое для открыто проложенной трубы, например «Труба откр. {} "
        u"м».",
        u"", False, True, False),
    ("circuit_key_fo", u"[Цепи] Ключевое слово типа цепи «оптическая»",
        u"Если это слово встречается в значении параметра цепи «Наименование» "
        u"(см. выше), цепь считается оптической — для неё не заполняется имя "
        u"нагрузки и отдельно ведётся нумерация «FO-1, FO-2…».",
        u"оптический", False, True, False),
    ("circuit_key_utp", u"[Цепи] Ключевое слово типа цепи «UTP/витая пара»",
        u"То же самое для цепей «витая пара» (UTP) — от типа цепи зависит, как "
        u"считается счётчик в параметре узла «Список цепей».",
        u"парной скрутки", False, True, False),
    ("circuit_key_power", u"[Цепи] Ключевое слово типа цепи «силовая»",
        u"То же самое для силовых цепей — они получают отдельную нумерацию "
        u"«PWR-1, PWR-2…», независимую от оптических.",
        u"силовой", False, True, False),
    ("horiz_tray_coef", u"[Цепи] Коэффициент запаса длины в лотке",
        u"На это число умножается посчитанная длина проводника, если способ "
        u"прокладки — лоток (учитывает провисание и технологический запас). "
        u"Например 1.10 — это +10% к длине.",
        u"1.10", False, True, False),
    ("horiz_pipe_coef", u"[Цепи] Коэффициент запаса длины в трубе (горизонталь)",
        u"То же самое для горизонтальных участков в трубе — умножается на длину "
        u"в трубе плюс горизонтальное смещение устройства/панели от ближайшего "
        u"узла.",
        u"1.15", False, True, False),
    ("vertical_coef", u"[Цепи] Коэффициент запаса длины по вертикали",
        u"Коэффициент запаса для вертикальных участков (переход между этажами, "
        u"спуск к устройству/подъём к панели) — умножается на посчитанную "
        u"разницу высот.",
        u"1.10", False, True, False),

    # --- структурная схема (BuildScsSchematic) ---
    ("schematic_view_name", u"[Схема] Имя вида структурной схемы",
        u"Чертёжный вид с этим именем создаётся при первом запуске кнопки "
        u"«Структурная схема» и обновляется при каждом повторном запуске. Если "
        u"переименовать вид в самом Revit, программа его больше не найдёт и "
        u"создаст новый — держите это имя синхронизированным с фактическим "
        u"именем вида.",
        u"Структурная схема СКС", False, True, False),
    ("layout_param_name", u"[Схема] Служебный параметр раскладки схемы",
        u"Текстовый параметр, привязанный к категории «Виды» — в нём хранится "
        u"раскладка предыдущего запуска (в формате JSON) для вида структурной "
        u"схемы. Не редактируйте его значение вручную: программа сама читает и "
        u"перезаписывает его, чтобы повторный запуск двигал только то, что "
        u"реально изменилось.",
        u"", False, True, False),
    ("room_param_name", u"[Схема] Параметр помещения устройства",
        u"Имя параметра (одно и то же на устройстве, на панели и на схемном "
        u"семействе-марке), в котором хранится текст помещения — по его "
        u"значению схема группирует устройства в общую рамку. Если у устройства "
        u"этот параметр ещё пуст, значение подбирается автоматически по маске "
        u"из поля ниже.",
        u"", False, True, False),
    ("room_mask", u"[Схема] Маска значения помещения из связи",
        u"Как собрать текст помещения из параметров Room связанной модели — "
        u"имена параметров через запятую и/или в скобках: «Имя (Номер)» → "
        u"«Офис (212)», «Имя, Номер» → «Офис, 212». Слова «Имя» и «Номер» — "
        u"служебные, означают имя и номер помещения. Срабатывает, только если "
        u"параметр помещения на устройстве (см. поле выше) ещё пустой.",
        u"Имя (Номер)", False, True, False),
    ("device_uid_param_name", u"[Схема] Служебный параметр UniqueId устройства",
        u"Текстовый параметр, привязанный к схемным семействам (маркерам на "
        u"схеме) — в нём хранится UniqueId исходного реального устройства/"
        u"панели. По нему программа при повторном запуске узнаёт, какой маркер "
        u"схемы уже создан для какого устройства, и обновляет его вместо "
        u"создания нового.",
        u"", False, True, False),
    ("node_label_offset_mm", u"[Схема] Смещение марки узла вверх от точки вставки, мм",
        u"Насколько выше точки вставки схемного семейства ставится его "
        u"текстовая марка (адрес/обозначение) — просто расстояние в "
        u"миллиметрах, чтобы подпись не накладывалась на сам значок узла.",
        u"5", False, True, False),
    ("max_row_width_mm", u"[Схема] Максимальная ширина строки помещений, мм",
        u"Если рамки помещений одного этажа не помещаются в одну строку по "
        u"ширине, следующее помещение переносится на новую строку ниже (порядок "
        u"помещений при этом не меняется — как перенос текста по словам). Пусто "
        u"или 0 — не ограничивать, всегда одна строка на этаж.",
        u"", False, False, False),
    ("schematic_device_categories_text", u"[Схема] Категории устройств схемы",
        u"Список произвольных названий категорий устройств для схемы — по одной "
        u"строке (например «Розетка», «Шкаф»). Для каждой строки ниже, в "
        u"таблице «Категории структурной схемы», отдельно выбирается схемное "
        u"семейство-марка и реальные типы устройств/панелей проекта, которые в "
        u"эту категорию входят.",
        u"", False, True, True),
]

# (ключ, подпись, пояснение простым языком, категории для пикера) —
# типы, выбираемые из проекта.
TYPE_FIELDS = [
    ("panel_type_id", u"Тип для точек панелей",
        u"Типоразмер категории «Обобщённые модели», которым кнопка «Узлы "
        u"трассы» помечает панели/шкафы на плане — этим же типом «Адреса "
        u"узлов» отличает панель от обычного узла маршрута.",
        (BuiltInCategory.OST_GenericModel,)),
    ("route_type_id", u"Тип для узлов маршрута",
        u"Типоразмер, которым отмечаются промежуточные узлы трассы (не панели "
        u"и не стояки) — ставится в точках стыков и разветвлений линий трассы.",
        (BuiltInCategory.OST_GenericModel,)),
    ("riser_type_id", u"Тип для точек стояков",
        u"Типоразмер, которым отмечаются точки стояков — по нему же «Адреса "
        u"узлов» отличает стояк от панели и обычного узла при построении "
        u"дерева адресации.",
        (BuiltInCategory.OST_GenericModel,)),
    ("node_annotation_type_id", u"[Схема] Марка узла на схеме",
        u"Тип аннотации категории «Марки элементов деталировки», который "
        u"автоматически ставится над каждым схемным семейством (розеткой, "
        u"шкафом) на структурной схеме и показывает его обозначение и адрес.",
        (BuiltInCategory.OST_DetailComponentTags,)),
]

# Категории реальных устройств/панелей СКС для схемы — только устройства
# связи и электрооборудование (панели/шкафы), а не весь набор
# CAT_DEVICES_AND_PANELS из scs_parameters.py (тот шире — используется
# для привязки параметров, где лишняя категория не мешает; здесь же это
# список выбора в пикере "реальные типы этой категории", и лишние
# категории только засоряли бы его типами, не относящимися к СКС).
# Источник списка — в таблице категорий структурной схемы
# (rebuild_category_type_pickers).
SCHEMATIC_SOURCE_CATEGORIES = (
    BuiltInCategory.OST_CommunicationDevices,
    BuiltInCategory.OST_ElectricalEquipment,
)

# Категория схемных семейств (элементы узлов/детализация) — та же, что у СОТ/СКУД.
SCHEMATIC_CATEGORIES = (BuiltInCategory.OST_DetailComponents,)

# {имя_категории: "id_типа"} — схемное семейство для категории.
SCHEMATIC_CATEGORY_TYPES_KEY = "schematic_category_type_ids"

# {имя_категории: ["id_типа1", ...]} — реальные типы устройств/панелей этой категории.
SCHEMATIC_CATEGORY_DEVICE_TYPES_KEY = "schematic_category_device_type_ids"

# (ключ, подпись, пояснение) — строка справочника кабелей (см.
# list_wire_catalog_items), выбирается отдельным пикером, а не текстом;
# хранится и читается так же, как TYPE_FIELDS, но источник списка для
# выбора другой.
CONDUCTOR_FIELDS = [
    ("conductor_type_id", u"Проводник (тип кабеля) для цепей СКС",
        u"Необязательно: если задан «Параметр-признак строки справочника "
        u"кабелей» выше, здесь можно выбрать конкретную строку из ключевой "
        u"спецификации кабелей — она будет проставлена всем цепям, "
        u"создаваемым кнопкой «Цепи СКС», без запроса при каждом запуске."),
]

LIST_FIELDS = set(key for key, _, _, _, is_list, _req, _ml in TEXT_FIELDS if is_list)


def _split_section(label_text):
    """"[Раздел] Подпись" -> ("Раздел", "Подпись"); просто "Подпись" -> (None, "Подпись")."""
    if label_text.startswith(u"[") and u"]" in label_text:
        end = label_text.index(u"]")
        return label_text[1:end], label_text[end + 1:].strip()
    return None, label_text


# Подписи без префикса "[Раздел]" — используются в сообщениях об отсутствующих полях
PLAIN_LABELS = {}
for _key, _label, _hint, _default, _is_list, _required, _multiline in TEXT_FIELDS:
    PLAIN_LABELS[_key] = _split_section(_label)[1]
for _key, _label, _hint, _categories in TYPE_FIELDS:
    PLAIN_LABELS[_key] = _split_section(_label)[1]
for _key, _label, _hint in CONDUCTOR_FIELDS:
    PLAIN_LABELS[_key] = _split_section(_label)[1]


def _safe_element_name(el):
    """
    Имя элемента через Element.Name.GetValue(el) — прямой доступ el.Name
    в IronPython у некоторых типов Revit-элементов (в т.ч. FamilySymbol)
    падает с ошибкой неоднозначного связывания и незаметно уходит в
    except, поэтому используем статическое свойство через рефлексию.
    """
    try:
        return Element.Name.GetValue(el)
    except:
        try:
            return el.Name
        except:
            return None


class TypeOption(object):
    """Обёртка над FamilySymbol для отображения в списке выбора."""

    def __init__(self, symbol):
        self.symbol = symbol

        fam_name = None
        try:
            fam_name = _safe_element_name(symbol.Family)
        except:
            pass

        type_name = _safe_element_name(symbol)

        self.name = u"{} : {}".format(
            fam_name or u"?",
            type_name or str(symbol.Id.IntegerValue)
        )

    def __str__(self):
        return self.name


def list_generic_model_symbols(doc):
    """
    Все загруженные в проект типоразмеры категории «Обобщённые модели» —
    включая те, у которых ещё нет ни одного вставленного экземпляра.

    FilteredElementCollector(...).OfClass(FamilySymbol) в некоторых
    случаях пропускает типы без экземпляров, поэтому обходим сами
    семейства (Family) категории и берём их типоразмеры через
    GetFamilySymbolIds() — так гарантированно попадают все загруженные.
    """
    symbols = []

    families = FilteredElementCollector(doc).OfClass(Family)

    for family in families:
        try:
            if family.FamilyCategory is None:
                continue
            if family.FamilyCategory.Id != ElementId(BuiltInCategory.OST_GenericModel):
                continue
        except:
            continue

        for symbol_id in family.GetFamilySymbolIds():
            symbol = doc.GetElement(symbol_id)
            if symbol:
                symbols.append(symbol)

    return symbols


class WireTypeOption(object):
    """
    Обёртка над строкой ключевой спецификации кабелей для отображения в
    списке выбора (не WireType — см. list_wire_catalog_items).
    """

    def __init__(self, wire_type):
        self.wire_type = wire_type
        base_name = _safe_element_name(wire_type) or str(wire_type.Id.IntegerValue)
        self.name = u"{} (ID {})".format(base_name, wire_type.Id.IntegerValue)

    def __str__(self):
        return self.name


def list_wire_catalog_items(doc, marker_param_name):
    """
    Строки ключевой спецификации кабелей, используемой параметром цепи
    «Проводник» (StorageType.ElementId — Revit хранит там ссылку на
    строку ключевой спецификации, а не на Autodesk.Revit.DB.Electrical.WireType).

    Ключевое имя строки хранится в BuiltInParameter.REF_TABLE_ELEM_NAME,
    общем для ВСЕХ ключевых спецификаций документа — поэтому дополнительно
    фильтруем по наличию marker_param_name (произвольный параметр,
    присутствующий только у строк нужного справочника кабелей, например
    "SMNX_Марка" — задаётся пользователем в настройках, т.к. это
    соглашение конкретного проекта).
    """
    from Autodesk.Revit.DB import BuiltInParameter

    if not marker_param_name:
        return []

    items = []
    for el in FilteredElementCollector(doc).WhereElementIsNotElementType().ToElements():
        try:
            key_param = el.get_Parameter(BuiltInParameter.REF_TABLE_ELEM_NAME)
            if not key_param or not key_param.HasValue:
                continue
            if el.LookupParameter(marker_param_name) is None:
                continue
        except:
            continue
        items.append(el)

    return items


def list_symbols_by_categories(doc, builtin_categories):
    """
    Все загруженные в проект типоразмеры для перечисленных
    BuiltInCategory (включая типы без вставленных экземпляров, см.
    list_generic_model_symbols).
    """
    category_ids = set(ElementId(bic) for bic in builtin_categories)
    symbols = []

    families = FilteredElementCollector(doc).OfClass(Family)

    for family in families:
        try:
            if family.FamilyCategory is None:
                continue
            if family.FamilyCategory.Id not in category_ids:
                continue
        except:
            continue

        for symbol_id in family.GetFamilySymbolIds():
            symbol = doc.GetElement(symbol_id)
            if symbol:
                symbols.append(symbol)

    return symbols


class GroupTypeOption(object):
    """Обёртка над GroupType (тип группы) для отображения в списке выбора."""

    def __init__(self, group_type):
        self.group_type = group_type
        self.name = _safe_element_name(group_type) or str(group_type.Id.IntegerValue)

    def __str__(self):
        return self.name


def list_detail_group_types(doc):
    """
    Типы групп деталей проекта (GroupType категории OST_IOSDetailGroups),
    включая ещё не размещённые. Для выбора типовых групп структурной схемы
    СКУД (см. skud_settings).
    """
    result = []

    for group_type in FilteredElementCollector(doc).OfClass(GroupType):
        try:
            category = group_type.Category
        except:
            category = None
        if category is None:
            continue
        if category.Id.IntegerValue == int(BuiltInCategory.OST_IOSDetailGroups):
            result.append(group_type)

    return result


def _type_display_name(doc, id_str):
    if not id_str:
        return u"(не выбран)"

    try:
        el = doc.GetElement(ElementId(int(id_str)))
    except:
        return u"(не выбран)"

    if el is None:
        return u"(не выбран)"

    fam_name = None
    try:
        fam_name = _safe_element_name(el.Family)
    except:
        pass

    type_name = _safe_element_name(el)

    if fam_name and type_name:
        return u"{} : {}".format(fam_name, type_name)

    return type_name or id_str


def _type_names_display(doc, id_strs):
    """Отображаемое имя списка выбранных типов (id-строки) через "; ", либо "(не выбрано)"."""
    if not id_strs:
        return u"(не выбрано)"
    return u"; ".join(_type_display_name(doc, s) for s in id_strs)


def list_used_symbols_by_categories(doc, builtin_categories):
    """
    Только типы, у которых в проекте есть хотя бы один размещённый
    экземпляр — в отличие от list_symbols_by_categories (все загруженные
    типы, включая никогда не использованные), чтобы список выбора
    реальных устройств/панелей категории структурной схемы не
    засорялся типами, которых нет на модели. Для схемных семейств
    (ещё не вставленных на схему) по-прежнему используется
    list_symbols_by_categories.
    """
    seen_ids = set()
    symbols = []

    for bic in builtin_categories:
        try:
            instances = FilteredElementCollector(doc).OfCategory(bic).WhereElementIsNotElementType().ToElements()
        except:
            continue

        for el in instances:
            try:
                type_id = el.GetTypeId()
            except:
                continue

            if type_id is None or type_id == ElementId.InvalidElementId:
                continue

            if type_id.IntegerValue in seen_ids:
                continue

            symbol = doc.GetElement(type_id)
            if symbol is not None:
                seen_ids.add(type_id.IntegerValue)
                symbols.append(symbol)

    return symbols


def _settings_file_path():
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    folder = os.path.join(appdata, "pyRevit")

    if not os.path.isdir(folder):
        try:
            os.makedirs(folder)
        except:
            pass

    return os.path.join(folder, SETTINGS_FILE_NAME)


def _read_all():
    path = _settings_file_path()

    if not os.path.isfile(path):
        return {}

    try:
        with io.open(path, "r", encoding="utf-8") as f:
            text = f.read()
        if not text.strip():
            return {}
        return json.loads(text)
    except:
        return {}


def _write_all(data):
    path = _settings_file_path()

    try:
        with io.open(path, "w", encoding="utf-8") as f:
            f.write(unicode(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)))
    except:
        forms.alert(
            u"Не удалось сохранить настройки СКС в файл:\n{}".format(path)
        )


def load_saved_values():
    """Строковые значения настроек: из JSON-файла, иначе — значения по умолчанию."""
    saved = _read_all()
    values = {}

    for key, _, _, default, _, _, _ in TEXT_FIELDS:
        values[key] = saved.get(key, default)

    for key, _, _, _ in TYPE_FIELDS:
        values[key] = saved.get(key, "")

    for key, _, _ in CONDUCTOR_FIELDS:
        values[key] = saved.get(key, "")

    # Миграция room_number_param_name -> room_mask (см. room_info.py).
    if not saved.get("room_mask") and saved.get("room_number_param_name"):
        values["room_mask"] = u"Имя ({})".format(saved["room_number_param_name"])

    return values


def save_values(values):
    data = _read_all()
    data.update(values)
    _write_all(data)


def load_schematic_category_type_ids():
    saved = _read_all()
    return dict(saved.get(SCHEMATIC_CATEGORY_TYPES_KEY, {}))


def load_schematic_category_device_type_ids():
    saved = _read_all()
    return dict(saved.get(SCHEMATIC_CATEGORY_DEVICE_TYPES_KEY, {}))


def save_schematic_category_type_ids(type_ids):
    data = _read_all()
    data[SCHEMATIC_CATEGORY_TYPES_KEY] = dict(type_ids)
    _write_all(data)


def save_schematic_category_device_type_ids(type_ids):
    data = _read_all()
    data[SCHEMATIC_CATEGORY_DEVICE_TYPES_KEY] = dict(type_ids)
    _write_all(data)


def get_schematic_category_symbols(doc, settings):
    """
    {имя_категории: FamilySymbol} для категорий из
    schematic_device_categories_text с выбранным существующим в проекте
    схемным типом. Категории без выбранного/валидного типа в словарь не
    попадают.
    """
    categories = parse_category_names(settings.get("schematic_device_categories_text", u""))
    type_ids = load_schematic_category_type_ids()

    symbols = {}
    for name in categories:
        id_str = type_ids.get(name)
        if not id_str:
            continue
        try:
            symbol = doc.GetElement(ElementId(int(id_str)))
        except:
            symbol = None
        if symbol is not None:
            symbols[name] = symbol

    return symbols


def get_schematic_category_device_type_ids(settings):
    """{имя_категории: set(int)} — id реальных типов устройств/панелей категории."""
    categories = parse_category_names(settings.get("schematic_device_categories_text", u""))
    saved = load_schematic_category_device_type_ids()

    result = {}
    for name in categories:
        id_strs = saved.get(name) or []
        ids = set()
        for id_str in id_strs:
            try:
                ids.add(int(id_str))
            except:
                continue
        if ids:
            result[name] = ids

    return result


def _split_list(text):
    return [x.strip() for x in text.split(",") if x.strip()]


def to_runtime_settings(values):
    """Преобразует строковые значения формы в типы, готовые для scs.py (id типов остаются строками)."""
    settings = dict(values)
    for key in LIST_FIELDS:
        settings[key] = _split_list(values[key])
    return settings


def require(settings, keys):
    """
    Проверяет, что перечисленные ключи заполнены в settings (после
    to_runtime_settings). Настройки общие на все кнопки SCS.panel, поэтому
    каждая кнопка проверяет только те поля, которые использует сама —
    остальные могут быть пустыми, если эта кнопка ими не пользуется.
    Останавливает скрипт через forms.alert(exitscript=True), если чего-то не хватает.
    """
    missing = []

    for key in keys:
        value = settings.get(key)

        if isinstance(value, list):
            ok = len(value) > 0
        else:
            ok = bool(value and str(value).strip())

        if not ok:
            missing.append(PLAIN_LABELS.get(key, key))

    if missing:
        forms.alert(
            u"В настройках СКС не заполнены обязательные для этой кнопки поля:\n\n{}\n\n"
            u"Запустите кнопку «Параметры СКС» и заполните их там.".format(u"\n".join(missing)),
            exitscript=True
        )


def show_settings_form(doc, values, keys=None):
    """
    Модальное окно редактирования настроек СКС: выбор типов для вставки
    (панель/устройство/маршрут) + текстовые параметры.
    Возвращает словарь строковых значений или None, если пользователь отменил.

    keys=None — показываются все поля (как раньше). Если передан набор
    ключей (Shift+клик по конкретной кнопке — см. require() рядом с ней в
    коде кнопки), показываются только поля из этого набора: TEXT_FIELDS и
    TYPE_FIELDS фильтруются по ключу, секция «Проводник для цепей СКС»
    показывается только если в наборе есть "conductor_type_id". Сохранение
    (save_values) всё равно мержится в общий JSON-файл, так что поля,
    скрытые в этом окне, не теряются — они просто не редактируются отсюда.
    """
    result = {"values": None}

    type_fields = TYPE_FIELDS if keys is None else [f for f in TYPE_FIELDS if f[0] in keys]
    text_fields = TEXT_FIELDS if keys is None else [f for f in TEXT_FIELDS if f[0] in keys]
    show_conductor = keys is None or "conductor_type_id" in keys

    win = Window()
    win.Title = u"Настройки СКС"
    win.Width = 780
    win.Height = 760 if keys is None else min(760, 220 + 70 * (len(type_fields) + len(text_fields)))
    win.WindowStartupLocation = WindowStartupLocation.CenterScreen
    # Topmost намеренно НЕ ставим: иначе окно выбора типа
    # (forms.SelectFromList, отдельное Window) открывается позади этого
    # окна и его невозможно ни увидеть, ни подвинуть на передний план.

    outer = DockPanel()
    outer.LastChildFill = True

    root = StackPanel()
    root.Margin = Thickness(16)

    title = TextBlock()
    title.Text = u"Настройки параметров СКС"
    title.FontSize = 16
    title.FontWeight = FontWeights.Bold
    title.Margin = Thickness(0, 0, 0, 4)
    root.Children.Add(title)

    hint = TextBlock()
    hint.Text = (
        u"Значения сохраняются и подставляются при следующих запусках."
        if keys is None else
        u"Показаны только поля, которые использует эта кнопка. Остальные "
        u"настройки СКС не затрагиваются."
    )
    hint.FontSize = 11
    hint.Foreground = Brushes.Gray
    hint.TextWrapping = TextWrapping.Wrap
    hint.Margin = Thickness(0, 0, 0, 10)
    root.Children.Add(hint)

    # --- типы для вставки ---

    type_values = {key: values.get(key, "") for key, _, _, _ in type_fields}
    type_labels = {}

    type_current_section = [None]

    def make_type_picker(key, label_text, hint_text, categories):
        section, plain_label = _split_section(label_text)

        if section != type_current_section[0]:
            type_current_section[0] = section
            section_title = TextBlock()
            section_title.Text = section if section else u"Типы для вставки"
            section_title.FontWeight = FontWeights.Bold
            section_title.Margin = Thickness(0, 16, 0, 4)
            root.Children.Add(section_title)

        label = TextBlock()
        label.Text = plain_label
        label.Margin = Thickness(0, 8, 0, 2)
        root.Children.Add(label)

        if hint_text:
            field_hint = TextBlock()
            field_hint.Text = hint_text
            field_hint.FontSize = 11
            field_hint.Foreground = Brushes.Gray
            field_hint.TextWrapping = TextWrapping.Wrap
            field_hint.Margin = Thickness(0, 0, 0, 2)
            root.Children.Add(field_hint)

        row = StackPanel()
        row.Orientation = Orientation.Horizontal

        value_label = TextBlock()
        value_label.Text = _type_display_name(doc, type_values[key])
        value_label.VerticalAlignment = VerticalAlignment.Center
        value_label.Width = 300
        value_label.TextWrapping = TextWrapping.Wrap
        type_labels[key] = value_label

        pick_btn = Button()
        pick_btn.Content = u"Выбрать..."
        pick_btn.Padding = Thickness(8, 2, 8, 2)
        pick_btn.Margin = Thickness(8, 0, 0, 0)

        def on_pick(sender, args, key=key, label_text=label_text, categories=categories):
            symbols = list_symbols_by_categories(doc, categories)
            if not symbols:
                forms.alert(u"В проекте нет типов нужной категории.")
                return

            options = sorted([TypeOption(s) for s in symbols], key=lambda o: o.name)
            selected = forms.SelectFromList.show(
                options,
                title=plain_label,
                button_name=u"Выбрать",
                multiselect=False
            )

            if selected:
                type_values[key] = str(selected.symbol.Id.IntegerValue)
                type_labels[key].Text = selected.name

        pick_btn.Click += on_pick

        row.Children.Add(value_label)
        row.Children.Add(pick_btn)
        root.Children.Add(row)

    for key, label_text, hint_text, categories in type_fields:
        make_type_picker(key, label_text, hint_text, categories)

    # --- текстовые параметры (сгруппированы по разделу, если подпись начинается с "[Раздел]") ---

    boxes = {}
    current_section = None
    panel_criteria_hint_shown = [False]

    category_type_ids = load_schematic_category_type_ids()
    category_device_type_ids = load_schematic_category_device_type_ids()
    category_type_labels = {}
    category_device_labels = {}
    category_types_panel = StackPanel()

    def rebuild_category_type_pickers(sender=None, args=None):
        category_types_panel.Children.Clear()
        category_type_labels.clear()
        category_device_labels.clear()

        categories = parse_category_names(boxes["schematic_device_categories_text"].Text)

        if not categories:
            hint2 = TextBlock()
            hint2.Text = u"(нет категорий — заполните поле выше и нажмите «Обновить список»)"
            hint2.FontSize = 11
            hint2.Foreground = Brushes.Gray
            category_types_panel.Children.Add(hint2)
            return

        for name in categories:
            group_title = TextBlock()
            group_title.Text = u"Категория «{}»".format(name)
            group_title.FontWeight = FontWeights.Bold
            group_title.Margin = Thickness(0, 12, 0, 2)
            category_types_panel.Children.Add(group_title)

            # --- схемное семейство для вставки ---

            label = TextBlock()
            label.Text = u"Схемное семейство (для вставки)"
            label.Margin = Thickness(0, 4, 0, 2)
            category_types_panel.Children.Add(label)

            row = StackPanel()
            row.Orientation = Orientation.Horizontal

            value_label = TextBlock()
            value_label.Text = _type_display_name(doc, category_type_ids.get(name, ""))
            value_label.VerticalAlignment = VerticalAlignment.Center
            value_label.Width = 300
            value_label.TextWrapping = TextWrapping.Wrap
            category_type_labels[name] = value_label

            pick_btn = Button()
            pick_btn.Content = u"Выбрать..."
            pick_btn.Padding = Thickness(8, 2, 8, 2)
            pick_btn.Margin = Thickness(8, 0, 0, 0)

            def on_pick_schematic(sender, args, name=name):
                schematic_categories = list(SCHEMATIC_CATEGORIES)
                symbols = list_symbols_by_categories(doc, schematic_categories)
                if not symbols:
                    forms.alert(u"В проекте нет типов категории «Элементы узлов».")
                    return

                options = sorted([TypeOption(s) for s in symbols], key=lambda o: o.name)
                selected = forms.SelectFromList.show(
                    options,
                    title=u"Схемное семейство для категории «{}»".format(name),
                    button_name=u"Выбрать",
                    multiselect=False
                )

                if selected:
                    category_type_ids[name] = str(selected.symbol.Id.IntegerValue)
                    category_type_labels[name].Text = selected.name

            pick_btn.Click += on_pick_schematic

            row.Children.Add(value_label)
            row.Children.Add(pick_btn)
            category_types_panel.Children.Add(row)

            # --- реальные типы устройств/панелей модели, относящиеся к категории ---

            label2 = TextBlock()
            label2.Text = u"Реальные типы устройств/панелей этой категории (в модели)"
            label2.Margin = Thickness(0, 6, 0, 2)
            category_types_panel.Children.Add(label2)

            row2 = StackPanel()
            row2.Orientation = Orientation.Horizontal

            device_ids = category_device_type_ids.get(name, [])
            device_label = TextBlock()
            device_label.Text = _type_names_display(doc, device_ids)
            device_label.VerticalAlignment = VerticalAlignment.Center
            device_label.Width = 300
            device_label.TextWrapping = TextWrapping.Wrap
            category_device_labels[name] = device_label

            pick_btn2 = Button()
            pick_btn2.Content = u"Выбрать..."
            pick_btn2.Padding = Thickness(8, 2, 8, 2)
            pick_btn2.Margin = Thickness(8, 0, 0, 0)

            def on_pick_devices(sender, args, name=name):
                source_categories = list(SCHEMATIC_SOURCE_CATEGORIES)
                symbols = list_used_symbols_by_categories(doc, source_categories)
                if not symbols:
                    forms.alert(u"В проекте нет размещённых экземпляров в категориях устройств/панелей СКС.")
                    return

                options = sorted([TypeOption(s) for s in symbols], key=lambda o: o.name)
                selected = forms.SelectFromList.show(
                    options,
                    title=u"Типы устройств/панелей для категории «{}»".format(name),
                    button_name=u"Выбрать",
                    multiselect=True
                )

                if selected is not None:
                    category_device_type_ids[name] = [str(o.symbol.Id.IntegerValue) for o in selected]
                    category_device_labels[name].Text = _type_names_display(doc, category_device_type_ids[name])

            pick_btn2.Click += on_pick_devices

            row2.Children.Add(device_label)
            row2.Children.Add(pick_btn2)
            category_types_panel.Children.Add(row2)

    for key, label_text, hint_text, _, _, required, multiline in text_fields:
        section, plain_label = _split_section(label_text)

        if section != current_section:
            current_section = section
            section_title = TextBlock()
            section_title.Text = section if section else u"Параметры"
            section_title.FontWeight = FontWeights.Bold
            section_title.Margin = Thickness(0, 16, 0, 4)
            root.Children.Add(section_title)

            if section == u"Критерии панели" and not panel_criteria_hint_shown[0]:
                panel_criteria_hint_shown[0] = True
                panel_hint = TextBlock()
                panel_hint.Text = (
                    u"Это два независимых критерия одной и той же панели/шкафа. "
                    u"«Ключевые слова панелей» определяют, что считается панелью на "
                    u"плане — для расстановки узлов и как корень адресации (кнопки "
                    u"«Узлы трассы» и «Адреса узлов»). «Рабочий набор» отдельно "
                    u"определяет целевые панели категории «Электрооборудование», для "
                    u"которых строятся и считаются цепи (кнопка «Расчёт длины цепи»). "
                    u"Элемент должен подходить под ОБА критерия, иначе он может "
                    u"появиться на схеме узлом, но выпасть из расчёта цепей — или "
                    u"наоборот."
                )
                panel_hint.FontSize = 11
                panel_hint.Foreground = Brushes.Gray
                panel_hint.TextWrapping = TextWrapping.Wrap
                panel_hint.Margin = Thickness(0, 0, 0, 8)
                root.Children.Add(panel_hint)

        label = TextBlock()
        label.Text = plain_label + (u" *" if required else u"")
        label.Margin = Thickness(0, 8, 0, 2)
        label.TextWrapping = TextWrapping.Wrap
        root.Children.Add(label)

        if hint_text:
            field_hint = TextBlock()
            field_hint.Text = hint_text
            field_hint.FontSize = 11
            field_hint.Foreground = Brushes.Gray
            field_hint.TextWrapping = TextWrapping.Wrap
            field_hint.Margin = Thickness(0, 0, 0, 2)
            root.Children.Add(field_hint)

        box = TextBox()
        box.Text = values.get(key, "")
        box.Padding = Thickness(4)

        if multiline:
            box.AcceptsReturn = True
            box.TextWrapping = TextWrapping.Wrap
            box.Height = 80
            box.VerticalScrollBarVisibility = ScrollBarVisibility.Auto

        root.Children.Add(box)
        boxes[key] = box

        if key == "schematic_device_categories_text":
            refresh_btn = Button()
            refresh_btn.Content = u"Обновить список категорий ниже"
            refresh_btn.Padding = Thickness(8, 2, 8, 2)
            refresh_btn.HorizontalAlignment = HorizontalAlignment.Left
            refresh_btn.Margin = Thickness(0, 4, 0, 0)
            refresh_btn.Click += rebuild_category_type_pickers
            root.Children.Add(refresh_btn)

            category_types_title = TextBlock()
            category_types_title.Text = u"Категории структурной схемы: семейства и устройства"
            category_types_title.FontWeight = FontWeights.Bold
            category_types_title.Margin = Thickness(0, 12, 0, 4)
            category_types_title.TextWrapping = TextWrapping.Wrap
            root.Children.Add(category_types_title)

            root.Children.Add(category_types_panel)
            rebuild_category_type_pickers()

    # --- проводник для цепей СКС (кнопка «Цепи СКС») ---

    conductor_values = {}

    if show_conductor:
        conductor_section_title = TextBlock()
        conductor_section_title.Text = u"Проводник для цепей СКС"
        conductor_section_title.FontWeight = FontWeights.Bold
        conductor_section_title.Margin = Thickness(0, 16, 0, 4)
        root.Children.Add(conductor_section_title)

        conductor_key, conductor_label_text, conductor_hint_text = CONDUCTOR_FIELDS[0]

        conductor_hint = TextBlock()
        conductor_hint.Text = conductor_hint_text
        conductor_hint.FontSize = 11
        conductor_hint.Foreground = Brushes.Gray
        conductor_hint.TextWrapping = TextWrapping.Wrap
        conductor_hint.Margin = Thickness(0, 0, 0, 8)
        root.Children.Add(conductor_hint)

        conductor_values = {key: values.get(key, "") for key, _, _ in CONDUCTOR_FIELDS}

        conductor_row = StackPanel()
        conductor_row.Orientation = Orientation.Horizontal

        conductor_value_label = TextBlock()
        conductor_value_label.Text = _type_display_name(doc, conductor_values[conductor_key])
        conductor_value_label.VerticalAlignment = VerticalAlignment.Center
        conductor_value_label.Width = 300
        conductor_value_label.TextWrapping = TextWrapping.Wrap
        conductor_row.Children.Add(conductor_value_label)

        conductor_pick_btn = Button()
        conductor_pick_btn.Content = u"Выбрать..."
        conductor_pick_btn.Padding = Thickness(8, 2, 8, 2)
        conductor_pick_btn.Margin = Thickness(8, 0, 0, 0)

        def on_pick_conductor(sender, args):
            marker_param_name = (
                boxes["wire_catalog_marker_param"].Text.strip() if "wire_catalog_marker_param" in boxes
                else (values.get("wire_catalog_marker_param") or u"").strip()
            )
            if not marker_param_name:
                forms.alert(
                    u"Сначала заполните поле «Параметр-признак строки справочника "
                    u"кабелей» в разделе «Цепи»."
                )
                return

            wire_items = list_wire_catalog_items(doc, marker_param_name)
            if not wire_items:
                forms.alert(
                    u"Не найдено строк справочника кабелей (ни один элемент документа "
                    u"не содержит одновременно «Ключевое имя» и параметр «{}»).".format(
                        marker_param_name
                    )
                )
                return

            options = sorted([WireTypeOption(w) for w in wire_items], key=lambda o: o.name)
            selected = forms.SelectFromList.show(
                options,
                title=conductor_label_text,
                button_name=u"Выбрать",
                multiselect=False
            )

            if selected:
                conductor_values[conductor_key] = str(selected.wire_type.Id.IntegerValue)
                conductor_value_label.Text = selected.name

        conductor_pick_btn.Click += on_pick_conductor

        conductor_row.Children.Add(conductor_pick_btn)
        root.Children.Add(conductor_row)

    required_hint = TextBlock()
    required_hint.Text = u"* обязательные поля — без них соответствующая кнопка не сможет найти элементы или записать параметры"
    required_hint.FontSize = 11
    required_hint.Foreground = Brushes.Gray
    required_hint.TextWrapping = TextWrapping.Wrap
    required_hint.Margin = Thickness(0, 10, 0, 0)
    root.Children.Add(required_hint)

    # --- кнопки (закреплены внизу окна, вне прокручиваемой области) ---

    buttons = StackPanel()
    buttons.Orientation = Orientation.Horizontal
    buttons.HorizontalAlignment = HorizontalAlignment.Right
    buttons.Margin = Thickness(16, 8, 16, 12)
    DockPanel.SetDock(buttons, Dock.Bottom)

    reset_btn = Button()
    reset_btn.Content = u"Сбросить параметры"
    reset_btn.Padding = Thickness(10, 4, 10, 4)
    reset_btn.Margin = Thickness(0, 0, 8, 0)

    cancel_btn = Button()
    cancel_btn.Content = u"Отмена"
    cancel_btn.Padding = Thickness(10, 4, 10, 4)
    cancel_btn.Margin = Thickness(0, 0, 8, 0)

    ok_btn = Button()
    ok_btn.Content = u"Сохранить и запустить"
    ok_btn.Padding = Thickness(10, 4, 10, 4)
    ok_btn.FontWeight = FontWeights.Bold

    def on_reset(sender, args):
        for key, _, _, default, _, _, _ in text_fields:
            boxes[key].Text = default

    def on_ok(sender, args):
        # Настройки общие на все кнопки SCS.panel — какие поля обязательны,
        # решает каждая кнопка сама через scs_settings.require() после
        # получения settings. Здесь просто сохраняем то, что введено (если
        # keys сузил форму, сохраняются только показанные поля — остальные
        # значения в общем JSON-файле остаются как были, см. save_values).
        combined = {key: box.Text for key, box in boxes.items()}
        combined.update(type_values)
        combined.update(conductor_values)
        result["values"] = combined
        save_schematic_category_type_ids(category_type_ids)
        save_schematic_category_device_type_ids(category_device_type_ids)
        win.Close()

    def on_cancel(sender, args):
        win.Close()

    reset_btn.Click += on_reset
    ok_btn.Click += on_ok
    cancel_btn.Click += on_cancel

    buttons.Children.Add(reset_btn)
    buttons.Children.Add(cancel_btn)
    buttons.Children.Add(ok_btn)

    def _on_settings_imported():
        result["values"] = settings_transfer.RELOAD
        win.Close()

    settings_transfer.add_transfer_buttons(
        buttons, _read_all, _write_all, u"СКС", _on_settings_imported
    )

    scroll = ScrollViewer()
    scroll.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
    scroll.Content = root

    outer.Children.Add(buttons)
    outer.Children.Add(scroll)

    win.Content = outer
    win.ShowDialog()

    return result["values"]


def get_settings_interactive(doc, keys=None):
    """
    Показывает окно настроек, сохраняет введённые значения и возвращает
    полный актуальный словарь настроек (списки уже разобраны из строк,
    id типов остаются строками — их разбирает вызывающий скрипт).
    Возвращает None, если пользователь нажал "Отмена".

    keys=None — редактируются все поля (исторически так работала кнопка
    «Параметры СКС»). Каждая рабочая кнопка СКС вызывает это по
    Shift+клику со своим набором keys (тем же, что передаёт в require()
    плюс несколько дополнительных, которые использует не напрямую, а
    через библиотечные функции) — тогда показываются только её поля.
    Возвращается всегда ПОЛНЫЙ словарь настроек (после сохранения), а не
    только отредактированные поля — остальные кнопки СКС могут требовать
    и другие ключи из того же файла.
    """
    while True:
        saved = load_saved_values()
        edited = show_settings_form(doc, saved, keys=keys)

        if edited == settings_transfer.RELOAD:
            # пользователь загрузил настройки из файла — они уже записаны,
            # открываем окно заново с обновлёнными значениями
            continue

        if edited is None:
            return None

        save_values(edited)
        return to_runtime_settings(load_saved_values())


def get_settings_silent():
    """
    Настройки без показа окна — уже сохранённые значения (или значения
    по умолчанию из scs.py, если ещё ничего не настроено). Используется
    рабочими кнопками СКС (не «Параметры СКС»): настраивать/менять
    значения — задача кнопки «Параметры СКС», остальные только читают.
    """
    return to_runtime_settings(load_saved_values())
