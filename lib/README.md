# lowlife — общая библиотека для кнопок LowLife.extension

Папка `lib/` лежит рядом с `LowLife.tab` на уровне расширения, поэтому pyRevit
сам добавляет её в `sys.path` — в любом `script.py` достаточно:

```python
from lowlife.geometry import get_point
```

Ниже — что лежит в каждом модуле, чтобы не искать нужный хелпер по файлам.

## geometry.py
Геометрия элементов Revit, не привязанная к конкретной дисциплине.

| Функция | Сигнатура | Что делает |
|---|---|---|
| `get_point` | `get_point(el)` | Точка `LocationPoint` элемента или `None` |
| `get_curve_data` | `get_curve_data(el, view)` | `(curve, p1, p2)` из `LocationCurve`; если её нет — диагональ bounding box в `view` |
| `point_key` | `point_key(p, tol)` | Ключ точки на сетке с шагом `tol` — для группировки близких точек в `dict` |
| `points_close` | `points_close(p1, p2, tol)` | `True`, если расстояние между точками `<= tol` |
| `is_point_on_curve` | `is_point_on_curve(curve, pt, tol)` | `(bool, projected_point)` — лежит ли точка на кривой с проекцией |
| `sort_points` | `sort_points(curve, points)` | Точки, отсортированные по расстоянию от начала кривой |
| `get_document_levels` | `get_document_levels(doc)` | Все уровни документа, отсортированные по высоте (`Elevation`) |
| `find_level_for_elevation` | `find_level_for_elevation(z, sorted_levels)` | Уровень, на котором физически находится точка с высотой `z` — ближайший снизу, иначе самый нижний; `sorted_levels` — результат `get_document_levels` (резервный вариант, если у элемента нет связанного уровня) |
| `get_element_level` | `get_element_level(doc, el)` | Уровень элемента через `Element.LevelId` — покрывает и параметр «Уровень» экземпляра (устройство/панель), и рабочую плоскость линейного элемента, не завися от языка интерфейса Revit; `None`, если не связан ни с каким уровнем |

## params.py
Чтение/запись параметров элемента по списку возможных имён (когда параметр
может называться по-разному в разных семействах/шаблонах).

| Функция | Сигнатура | Что делает |
|---|---|---|
| `get_double_param` | `get_double_param(el, names)` | Первое числовое значение параметра из `names`, иначе `None` |
| `set_double_param` | `set_double_param(el, names, value)` | Записывает `value` в первый найденный числовой параметр из `names` |
| `set_string_param` | `set_string_param(el, name, value)` | Записывает строковое `value` в параметр `name` (только для параметров типа String) |
| `get_string_param` | `get_string_param(el, name)` | Строковое значение параметра: `AsString` для текстовых, иначе `AsValueString` |
| `get_param_any` | `get_param_any(el, name)` | Строковое представление значения параметра **любого** типа хранения (String/Integer/Double/ElementId) |
| `set_param_any` | `set_param_any(el, name, value)` | Записывает `value`, сама подбирая способ (`Set`/`SetValueString`) под тип хранения параметра |

## selection.py
Работа с выделением элементов в Revit UI.

| Функция | Сигнатура | Что делает |
|---|---|---|
| `get_single_selection` | `get_single_selection(doc, uidoc, empty_message=..., multiple_message=...)` | Возвращает единственный выбранный элемент; если выделено 0 или >1 — показывает `forms.alert` и останавливает скрипт (`exitscript=True`) |

## electrical_circuits.py
Создание электрических цепей Revit — без привязки к дисциплине. Вынесен из
`fire_alarm_circuits.py`, чтобы кнопки ручного построения цепей на панелях
CircuitsSCS/CircuitsSKUD/CircuitsSPA и цепи «изолятор-устройства» СПС
(`fire_alarm_isolator_circuits.py`) не копировали одну и ту же логику.

| Функция | Сигнатура | Что делает |
|---|---|---|
| `resolve_system_type` | `resolve_system_type(name)` | `ElectricalSystemType` по имени из настроек (`"FireAlarm"`, `"Data"`, ...); при опечатке — ошибка со списком доступных. Через `getattr`, т.к. набор отличается между версиями Revit |
| `create_circuit` | `create_circuit(doc, panel_el, device_els, system_type_name)` | `ElectricalSystem.Create(device_els)` + `SelectPanel(panel_el)`; панель НЕ передаётся в список элементов цепи (иначе цепь выглядит "кольцевой" — панель одновременно источник и нагрузка). Элемент категории «Электрооборудование» среди `device_els` (например изолятор шлейфа СПС) ставится первым в списке — по наблюдению порядок важен для `Create()`. Если создание без панели всё равно падает с `electComponents`, повторяет попытку с панелью первым элементом, затем пробует `system.Remove([panel_el.Id])`, чтобы убрать её из состава элементов после `SelectPanel`. `(цепь, текст ошибки)` |

## manual_circuits.py
Тело кнопок «Цепи X» на панелях CircuitsSCS/CircuitsSKUD/CircuitsSPA:
пользователь сам выбирает панель и устройства, кнопка создаёт по
отдельной цепи на каждое устройство («домашний прогон»). Используется
целиком (`run_manual_circuit_button`) кнопками СКУД/СПА — различаются
только подписи и тип цепи по умолчанию, передаваемые из `script.py`. СКС —
особый случай (см. `scs_manual_circuits.py`): её кнопка берёт отсюда
только `pick_panel_and_devices`, т.к. тип цепи у неё фиксирован и
добавлен выбор проводника.

| Функция | Сигнатура | Что делает |
|---|---|---|
| `pick_panel_and_devices` | `pick_panel_and_devices(uidoc, doc, panel_prompt, devices_prompt)` | Выбор одной панели, затем нескольких устройств (`PickObject`/`PickObjects`, отсекая связанные файлы); останавливает скрипт при отмене или пустом выборе |
| `pick_system_type` | `pick_system_type(default_name)` | Диалог выбора `ElectricalSystemType` из доступных в текущей версии Revit, с предустановленным значением |
| `build_device_circuits` | `build_device_circuits(doc, panel_el, device_els, system_type_name, transaction_name)` | Создаёт по цепи на каждое устройство; `(created_count, errors)` |
| `run_manual_circuit_button` | `run_manual_circuit_button(discipline_title, default_system_type)` | Весь сценарий кнопки: выбор → создание → отчёт |

## scs_manual_circuits.py
Тело кнопки «Цепи СКС» (`CircuitsSCS.panel`): панель -> устройства, тип
цепи всегда `Data` (у СКС других не бывает — не запрашивается в диалоге,
в отличие от СКУД/СПА). Параметр «Проводник» (встроенный параметр
электрической цепи Revit, ссылка на строку ключевой спецификации) — имя
`CONDUCTOR_PARAM_NAME = u"Проводник"` зашито в код, а не в настройки СКС:
это не project-specific SMNX_-параметр. Revit не даёт получить список
строк справочника напрямую, поэтому список для выбора — значения,
**уже проставленные хотя бы у одной электрической цепи документа**.

| Функция | Сигнатура | Что делает |
|---|---|---|
| `list_used_conductors` | `list_used_conductors(doc)` | `{имя элемента-проводника: ElementId}` — по параметру «Проводник» уже существующих `ElectricalSystem` |
| `pick_conductor` | `pick_conductor(doc)` | Диалог выбора из `list_used_conductors`; останавливает скрипт, если список пуст (ни у одной цепи проводник ещё не выбран) или выбор отменён |
| `build_scs_manual_circuits` | `build_scs_manual_circuits(doc, panel_el, device_els, conductor_id)` | Создаёт по цепи типа Data на каждое устройство и проставляет «Проводник»; `(created_count, errors)` |

## scs.py
Константы и логика, специфичные для СКС / телекоммуникационных трасс
(`SCS.panel`). Сюда добавлять только то, что относится именно к этой
дисциплине — общие геометрические/параметрические вещи должны идти в
`geometry.py`/`params.py`.

Категории точек, которые PlaceRouteNodes вставляет как отдельные
семейства — **панель**, **стояк**, **узел маршрута** (обычный проходной/
концевой узел трассы). Устройства отдельной точкой вставки не считаются
— реальным устройствам (розетки, датчики и т.п.) в SyncCircuitsAndLengths
назначается ближайший уже адресованный узел маршрута, без своего
маркера (см. `docs/scs-panel.md`).

Константы: `FAMILY_FILTER`, `CABLE_PARAM_NAME`, `ROUTE_PARAM_NAME`,
`ROUTE_PARAM_VALUE` (для панели/маршрута), `ROUTE_PARAM_VALUE_RISER`
(отдельное значение для стояков — например «Вертикальный» вместо
«Горизонтальный»), `DEVICE_CABLE_TYPE_VALUE` (форсированный тип
прокладки для панелей/стояков — имя оставлено историческим, к
устройствам как категории больше не относится), `PANEL_KEYWORDS`,
`PANEL_EXCLUDE_KEYWORDS`, `RISER_KEYWORDS`, `RISER_EXCLUDE_KEYWORDS`,
`RISER_ANNOTATION_KEYWORDS` (отдельные от `RISER_KEYWORDS` — узнают
типовую аннотацию стояка на виде, не реальное устройство; имя типа
аннотации обычно не содержит слова «стояк»), `OFFSET_PARAM_NAMES`,
`CATEGORY_PRIORITY` (`("riser", "panel", "route")`).

| Функция | Сигнатура | Что делает |
|---|---|---|
| `detect_cable_type` | `detect_cable_type(el)` | Тип прокладки кабеля («Труба», «Труба открыто», «Лоток») по имени типоразмера/семейства **сегмента трассы** (линии) — этим определяется значение для примыкающего узла маршрута |
| `classify_element` | `classify_element(el, categories)` | `categories` — список `(name, keywords, exclude_keywords)`, проверяется по порядку; возвращает `name` первой подошедшей или `None` |
| `resolve_category` | `resolve_category(categories, priority=CATEGORY_PRIORITY)` | Из списка категорий объединённого узла выбирает одну по приоритету (riser > panel > route) |
| `merge_nodes` | `merge_nodes(nodes, tol, points_close_fn, existing_points=None)` | Объединяет узлы трассы ближе `tol` друг к другу в один, суммируя `categories`, `segment_ids`, `device`; `points_close_fn` обычно — `geometry.points_close`. Итоговая точка кластера выбирается **детерминированно** (не зависит от порядка обхода узлов, который может отличаться между запусками), по приоритету: (1) точка уже существующего на виде маркера из `existing_points`, если хоть один член кластера физически рядом с ним — иначе появление нового узла графа рядом с уже вставленным маркером (например, от только что добавленного сегмента) могло "утянуть" итоговую точку на новую координату, и дедуп в PlaceRouteNodes не находил старый маркер, создавая дубль рядом с ним; (2) точка помеченного узла (панель/стояк), если такая есть в кластере; (3) иначе — точка с наименьшими координатами (X, Y, Z) |
| `clear_stray_address_params` | `clear_stray_address_params(doc, param_names, allowed_type_ids, workset_param_name=None, workset_filter_key=None)` | Ищет элементы (Обобщённые модели + категории устройств/панелей), у которых заполнен один из `param_names`, но тип не входит в `allowed_type_ids`, и очищает эти параметры. Нужно вызывать в RenumberAddresses/SyncCircuitsAndLengths перед сбором узлов — иначе застрявший адрес на устройстве (с прежних запусков или ручного ввода) может быть спутан с адресом реального узла маршрута. `workset_*` ограничивают очистку одним рабочим набором: СКС и СКУД делят одни и те же имена параметров адреса (`SMNX_Сегмент_*`), и без этого запуск одной дисциплины стирал бы адреса другой. Вызывать внутри `revit.Transaction` |
| `is_excluded_device` | `is_excluded_device(el, excluded_keywords)` | Резервный (исключаемый из расчёта) порт — по ключевым словам в имени семейства. Общая для RenumberAddresses и SyncCircuitsAndLengths (обе ищут устройства через цепи целевых панелей) |
| `get_workset_name` | `get_workset_name(el, workset_param_name)` | Имя рабочего набора элемента: сперва по имени параметра (на случай, если рабочий набор продублирован в обычный параметр), иначе через `BuiltInParameter.ELEM_PARTITION_PARAM` |
| `panel_matches` | `panel_matches(panel, workset_param_name, workset_filter_key, norm_fn)` | Целевая панель — по ключевому слову в имени её рабочего набора (`norm_fn` — обычно `scs_circuits.norm`) |

## scs_settings.py
**Одно общее окно настроек на все четыре кнопки `SCS.panel`** (PlaceRouteNodes /
RenumberAddresses / SyncCircuitsAndLengths / SetupParameters): выбор
**типа для вставки** (панель/маршрут/стояк — из типов
категории «Обобщённые модели» в проекте, включая ещё НЕ вставленные —
см. `list_generic_model_symbols` ниже) + текстовые параметры
(`TEXT_FIELDS`, сгруппированы в окне по разделам через префикс
`"[Раздел] Подпись"`). Хранится в обычном JSON-файле
`%APPDATA%\pyRevit\LowLifeSCS_settings.json` (не в `pyRevit_config.ini` —
не полагаемся на `pyrevit.script.get_config()`, он не гарантированно
расшаривает секцию между разными `script.py`) — **не в репозитории**:
имена параметров и семейств зависят от проекта пользователя, дефолты в
`scs.py` намеренно пустые. Требования к семействам/параметрам — см.
`docs/scs-panel.md`.

Кнопка «Цепи СКС» на `CircuitsSCS.panel` эти настройки НЕ использует — у
неё нет своих project-specific параметров, см. `scs_manual_circuits.py`.

**Форму (`get_settings_interactive`) показывает только кнопка
«Параметры СКС» (SetupParameters)** — она единственное место, где
значения редактируются. Остальные три кнопки читают уже сохранённое
через `get_settings_silent()`, без показа окна — если запустить их до
первой настройки, `require()` остановит скрипт и попросит сначала
запустить «Параметры СКС».

Так как настройки общие, `require()` в каждой кнопке проверяет только
свой набор ключей — у разных кнопок разный набор нужных полей
(RenumberAddresses не использует поля SyncCircuitsAndLengths и
наоборот). Имена параметров (`cable_param_name`, `addr_param_name` и
т.п.) кнопки вообще не требуют через `require()` — их наличие/привязку
в проекте проверяет и чинит сама «Параметры СКС»; остаются обязательными
только выбор типов (id) и содержательные значения/ключевые слова,
которые «Параметры СКС» проверить не может.

| Функция | Сигнатура | Что делает |
|---|---|---|
| `get_settings_interactive` | `get_settings_interactive(doc)` | Показывает окно, сохраняет введённое и возвращает готовый словарь настроек (списки уже разобраны из строк через запятую, id типов — строки); `None`, если нажата «Отмена». Используется только в SetupParameters |
| `get_settings_silent` | `get_settings_silent()` | Без показа окна — уже сохранённые значения (или дефолты из `scs.py`), сразу через `to_runtime_settings`. Используется в PlaceRouteNodes/RenumberAddresses/SyncCircuitsAndLengths |
| `require` | `require(settings, keys)` | Проверяет, что перечисленные ключи заполнены (списки — что непусты); если нет — `forms.alert(exitscript=True)` со списком недостающих полей и предложением запустить «Параметры СКС» |
| `load_saved_values` | `load_saved_values()` | Сырые строковые значения из JSON-файла настроек, иначе — значения по умолчанию из `scs.py` |
| `save_values` | `save_values(values)` | Записывает словарь строковых значений в JSON-файл настроек |
| `show_settings_form` | `show_settings_form(doc, values)` | Само модальное окно (`ScrollViewer` + кнопки типов через `forms.SelectFromList`); используется внутри `get_settings_interactive` |
| `to_runtime_settings` | `to_runtime_settings(values)` | Строки → типы (списки через запятую → `list`); id типов не трогает |
| `list_generic_model_symbols` | `list_generic_model_symbols(doc)` | Все `FamilySymbol` категории «Обобщённые модели», загруженные в проект — обходом `Family`/`GetFamilySymbolIds()`, а не `FilteredElementCollector(...).OfClass(FamilySymbol)`, чтобы не пропустить типы без вставленных экземпляров |
| `_safe_element_name` | `_safe_element_name(el)` | `Element.Name.GetValue(el)` вместо прямого `el.Name` — в IronPython у некоторых Revit-элементов (в т.ч. `FamilySymbol`) `.Name` падает с ошибкой неоднозначного связывания, из-за чего в списке типов вместо имени типа показывался его `Id` |

Обычный сценарий использования в рабочей кнопке (не SetupParameters):
```python
from lowlife import scs_settings
from lowlife.scs_settings import get_settings_silent

settings = get_settings_silent()
if settings is None:
    forms.alert(u"Операция отменена.", exitscript=True)

scs_settings.require(settings, ["family_filter", "cable_param_name", "panel_type_id"])

FAMILY_FILTER = settings["family_filter"]
PANEL_KEYWORDS = settings["panel_keywords"]  # уже list
PANEL_TYPE_ID = ElementId(int(settings["panel_type_id"]))
panel_symbol = doc.GetElement(PANEL_TYPE_ID)
```

## scs_addressing.py
Логика кнопки **RenumberAddresses** («Адреса узлов»): классификация точек
относительно линий трассы (`classify_point` → `NODE_STRICT`/`NODE_ON_LINE`/
`NODE_NEAR_ENDPOINT`/`OFFSET_MARKER`/`UNCONNECTED`), построение соседства
узлов на линии, кратчайший путь до корня (панели/стояка) через Дейкстру
и порядок нумерации через обход в глубину (DFS), код этажа из имени
уровня/вида. Работает с обычными dict-записями `{"point": (x,y), ...}`,
не с Revit-элементами — вызывающий скрипт сам заполняет флаги
`is_riser`/`is_panel` (по `ElementId` типа и по ключевым словам
соответственно) перед вызовом `classify_point`.

| Функция | Сигнатура | Что делает |
|---|---|---|
| `build_shortest_path_tree` | `build_shortest_path_tree(nodes_by_id, roots, all_nodes, dist_fn=dist2)` | Многоисточниковый Дейкстра: `parent_id` каждого узла — ближайший по **реальному расстоянию** сосед (не по числу шагов графа, как раньше при BFS). Узлы вне досягаемости от `roots` (отдельная связная компонента) добираются локальными "корнями" без родителя. Возвращает `(visited_ids, effective_roots)` — `effective_roots` включает и такие локальные корни |
| `depth_first_order` | `depth_first_order(nodes_by_id, roots)` | Обход построенного дерева в глубину (итеративно, без рекурсии): одна ветка получает подряд идущие номера, затем следующая — вместо чередования веток, как при обходе в ширину |
| `select_root_sources` | `select_root_sources(panels, risers, real_nodes, margin)` | Выбирает источники корней обхода: панели в приоритете, но только те, что физически попадают в область реальных узлов маршрута (+`margin`) — иначе панель, случайно подошедшая по ключевым словам, но находящаяся в другом конце проекта, "прилипала" бы к ближайшему узлу без ограничения расстояния. Если ни одна панель не попала в область — пробуются стояки по тому же правилу. Возвращает `(root_sources, far_sources)` |
| `get_floor_code_for_level` | `get_floor_code_for_level(view, all_levels)` | Код этажа вида `F3`/`F-1` из имени уровня вида. Если в проекте несколько уровней с одинаковым именем на разной отметке (например, два уровня "Этаж -1" в разных секциях), различает их суффиксом по порядку отметки среди одноимённых: самый нижний — `F-1`, следующий — `F-1.1`, следующий — `F-1.2` и т.д. — иначе оба получили бы один и тот же код и адреса узлов совпадали бы между этажами. `all_levels` — результат `geometry.get_document_levels(doc)` |

Остальные ключевые функции: `classify_point`, `add_neighbor`,
`find_nearest_real_node`, `find_best_real_node_for_offset`,
`point_to_segment_distance_xy`, `line_parameter_xy`, `matches_keywords`.

## scs_circuits.py
Логика кнопки **SyncCircuitsAndLengths** («Синхронизация цепей»): граф по
адресам узлов (`build_graph`, использует `addr_prev_param_name` —
параметр может содержать несколько адресов через запятую, отсюда
`split_multi_value`), поиск кратчайшего пути A* (`astar_path`), длины по
способу прокладки (`calc_lengths`, `balance_round_parts`), классификация
и подписи цепей (`classify_circuit_type`, `make_load_name`,
`build_segment_list_text`), диагностика обрывов графа (`bfs_component`,
`find_closest_pair_between_sets` — используются, чтобы показать, где
именно у цепи нет пути до панели).

`find_nearest_segment_id(point, segments)` — ближайший адресованный
узел маршрута к панели/устройству, **только по XY, без Z**: панель или
устройство подводится к линии трассы в плане, а разница в высоте
подключения (розетка на 300мм, узел маршрута на потолке и т.п.) не
должна перебивать правильный выбор узла. Вертикальная составляющая
длины кабеля считается отдельно (`raw_vertical_ft` в самом скрипте
кнопки) — здесь она игнорируется только для выбора узла, не для расчёта
длины. Само вычисление и запись параметра «Ближайший узел маршрута» для
панелей/устройств происходит в **RenumberAddresses** (сразу после
нумерации адресов, пока функция уже нужна) — SyncCircuitsAndLengths
только читает уже записанное значение, ничего не досчитывает.

## scs_parameters.py
Логика кнопки **SetupParameters** («Параметры СКС»): таблица `PARAM_SPECS`
(ключ настроек → категории Revit → instance/type → источник) для каждого
параметра, который читают/пишут три кнопки СКС, и функции проверки/
привязки этих параметров из **уже подключённого к проекту** файла общих
параметров (ФОП, `Application.SharedParametersFilename`). Ничего не
выдумывает — если определения параметра нет ни в проекте, ни в файле
ФОП, `ensure_binding` возвращает `missing_definition=True`, и кнопка
только сообщает об этом, не создавая новых определений в файле ФОП.

| Функция | Сигнатура | Что делает |
|---|---|---|
| `find_existing_binding` | `find_existing_binding(doc, name)` | `(definition, binding)` параметра с именем `name`, если он уже привязан хоть к чему-то в проекте |
| `find_shared_definition` | `find_shared_definition(sp_file, name)` | Определение параметра `name` в открытом файле ФОП (`Application.OpenSharedParameterFile()`), перебором всех групп |
| `ensure_binding` | `ensure_binding(doc, app, sp_file, name, categories, binding_kind)` | Добавляет параметру `name` привязку ко всем `categories`, которых ему не хватает; `dict` с `added_categories`/`already_ok`/`missing_definition`/`error` |

## route_nodes.py
Общее тело кнопки «Узлы трассы» для **любой** дисциплины: расстановка
панелей/узлов маршрута/стояков по линиям сегментов трассы. Дисциплина
задаётся конфигом (ключевые слова, типы семейств, рабочий набор), а не
копией скрипта — узлы СКС ведут до шкафа СКС, узлы СКУД от устройств до
контроллера, дальше появятся СПС/СОУЭ, а логика одна.

| Функция | Сигнатура | Что делает |
|---|---|---|
| `place_route_nodes` | `place_route_nodes(doc, view, config, symbols_by_category, document_levels)` | Полный проход: сбор сегментов, граф линий, панели/стояки, слияние, вставка/обновление маркеров. Транзакцию НЕ открывает — вызывающий оборачивает сам |
| `collect_segments` | `collect_segments(doc, view, family_filter)` | Линейные элементы-сегменты трассы на виде |
| `build_line_graph` | `build_line_graph(segments)` | `(node_points, graph, segment_ids_by_node)` — линии режутся на участки в точках примыкания других линий |
| `collect_marked_points` | `collect_marked_points(doc, view, node_points, classify_rules, workset_param_name, workset_filter_key)` | Панели/стояки по ключевым словам **и** (если задан) по рабочему набору — то, чем дисциплины отличаются на одном плане |
| `build_insert_nodes` | `build_insert_nodes(node_points, segment_ids_by_node, marked_points)` | Узлы для вставки: точки графа + помеченные точки, слитые по допуску |
| `find_existing_markers` | `find_existing_markers(generic, placed_type_ids)` | Уже вставленные маркеры по ключу точки — чтобы повторный запуск обновлял, а не плодил копии |
| `resolve_node_values` | `resolve_node_values(doc, node, segments_by_id, marked_points, config, document_levels)` | Значения параметров и уровень для одного узла |

## route_addressing.py
Общее тело кнопки «Адреса узлов» для любой дисциплины. Сам алгоритм
(классификация точек, Дейкстра до корня, обход в глубину) живёт в
`scs_addressing.py` и от дисциплины не зависит; здесь — сборка элементов
из документа, применение алгоритма и запись результата.

| Функция | Сигнатура | Что делает |
|---|---|---|
| `renumber_addresses` | `renumber_addresses(doc, view, config, renumber_existing)` | Полный проход нумерации; возвращает dict со всем нужным для записи и отчёта (или `{"error": ...}`). В документ не пишет |
| `write_addresses` | `write_addresses(route_points, config, renumber_existing)` | Пишет «Адрес узла»/«Предыдущий адрес»; `(changed, skipped)`. Внутри транзакции |
| `write_nearest_nodes` | `write_nearest_nodes(doc, route_points, targets, config)` | Пишет «Ближайший узел маршрута» переданным панелям/устройствам (по XY); уже заполненное не перезаписывает. Внутри транзакции |
| `collect_lines_and_points` | `collect_lines_and_points(doc, view, config)` | Линии и точки на виде; панель дополнительно фильтруется по рабочему набору дисциплины |
| `link_nodes_along_lines` | `link_nodes_along_lines(lines, real_nodes)` | Соседство узлов вдоль каждой линии |
| `attach_roots` | `attach_roots(root_sources, lines_by_id, real_nodes)` | Привязывает панели/стояки к ближайшим реальным узлам — корни обхода |
| `assign_addresses` | `assign_addresses(ordered_routes, floor_code, renumber_existing)` | Проставляет адреса: всем заново либо только пустым |

Кнопки `SCS.panel` пока используют свои копии этой логики (СКС работает и
её не трогали ради рефакторинга) — при следующей правке СКС их стоит
перевести на эти модули.

## route_export.py
Запись таблицы адресов СКС в xlsx через `openpyxl`. Вынесен из
`route_addressing.py` в отдельный модуль намеренно: `openpyxl` —
CPython-only зависимость (импортируется внутри функции, не на уровне
модуля), а `route_addressing.py` используется и IronPython2-кнопками,
которым эта зависимость не нужна. Импортируется только из кнопок,
объявивших `#! python3` в `script.py` (сейчас — `ExportAddressesToExcel`).

| Функция | Сигнатура | Что делает |
|---|---|---|
| `export_addressing_to_excel` | `export_addressing_to_excel(rows, file_path)` | Пишет лист `"Адреса СКС"` с жирным заголовком и автошириной колонок; `rows` — список dict с ключами `id/category/x_mm/y_mm/addr/addr_prev/cable_type` (см. `COLUMNS`) |

## skud.py
Константы и логика, специфичные для СКУД (контроль доступа, `SKUD.panel`) —
по образцу `scs.py`, но независимый модуль (своя дисциплина).

| Функция | Сигнатура | Что делает |
|---|---|---|
| `is_controller` | `is_controller(el, workset_param_name, workset_keyword, type_keyword)` | Контроллер — рабочий набор содержит `workset_keyword` **и** имя типа (`Symbol.Name`) содержит `type_keyword` |
| `parse_category_names` | `parse_category_names(text)` | Текст вида `"контроллер\nсчитыватель\nзамок"` → список имён категорий устройств (по одной на строку) — общие категории для схемы (BuildSkudSchematic) и подбора проводника (AssignCircuitsAndCables) |
| `category_by_type_id` | `category_by_type_id(el, category_type_ids)` | Категория реального устройства по точному совпадению `ElementId` его типа с одним из `category_type_ids` (`{имя: set(int)}` из настроек) — заменяет сопоставление по ключевым словам |
| `hypotenuse_length_ft` | `hypotenuse_length_ft(pt_a, pt_b)` | `|dx|+|dy|+|dz|` между двумя точками (в футах) — длина "по катетам" для устройств рядом с контроллером |
| `is_near_controller` | `is_near_controller(controller_pt, device_pt, threshold_ft)` | `True`, если прямое 3D-расстояние между контроллером и устройством меньше порога |

## skud_settings.py
Окно настроек СКУД (все кнопки `SKUD.panel`) — независимая копия структуры
`scs_settings.py` (свой JSON `%APPDATA%\pyRevit\LowLifeSKUD_settings.json`,
свои `TEXT_FIELDS`/`TYPE_FIELDS`, свои `get_settings_interactive`/
`get_settings_silent`/`require`). Реэкспортирует
`list_generic_model_symbols`/`_safe_element_name`/`TypeOption` из
`scs_settings.py` — эти функции не специфичны для СКС по факту реализации.
Поддерживает многострочные текстовые поля (`schematic_device_categories_text`)
— `AcceptsReturn`/`TextWrapping` на `TextBox`, в отличие от однострочных
полей `scs_settings.py`.

Категории из `schematic_device_categories_text` — общая таблица для
структурной схемы (BuildSkudSchematic) и подбора типа проводника
(AssignCircuitsAndCables): один список категорий, одно сопоставление
«категория → реальные типы устройств». Для каждой категории окно хранит
(отдельно от `TEXT_FIELDS`, прямыми ключами в JSON):
`schematic_category_type_ids` (схемное семейство для вставки — из
категории Detail Items, `list_symbols_by_categories`),
`schematic_category_device_type_ids` (список реальных типов устройств
модели, отнесённых к категории — мультивыбор из `OST_SecurityDevices` +
`OST_ElectricalEquipment`), `schematic_category_wire_type_ids` (тип
проводника) и `schematic_category_layout_mm` (смещение `dx, dy` от точки
контроллера, мм) — с превью раскладки прямо в окне настроек.

Параметр цепи «Проводник» (`cable_type_param`) хранится как
`StorageType.ElementId`, но ссылается НЕ на
`Autodesk.Revit.DB.Electrical.WireType`, а на строку ключевой
спецификации — справочник кабельной продукции проекта (в наблюдаемом
проекте: отдельный вид спецификации со строками-«изделиями», у каждой
свои параметры вроде `SMNX_Марка`/`SMNX_Наименование`). Ключевое имя
строки читается через `BuiltInParameter.REF_TABLE_ELEM_NAME` — общий для
ВСЕХ ключевых спецификаций документа, поэтому `list_wire_catalog_items`
(в `scs_settings.py`) дополнительно фильтрует по наличию параметра
`wire_catalog_marker_param` (настраивается в окне СКУД, например
`SMNX_Марка`) — единственный надёжный способ отличить нужный справочник
от прочих ключевых спецификаций в проекте. Запись — `params.set_element_id_param`
(`p.Set(ElementId)`), не `set_param_any`/`SetValueString` — тот путь
для ElementId-параметров молча не срабатывал.

Форму показывает только кнопка «Параметры СКУД» (`SetupParameters` в
`SKUD.panel`) — остальные кнопки читают уже сохранённое через
`get_settings_silent()`, тот же принцип, что в СКС.

## skud_parameters.py
Таблица `PARAM_SPECS` для параметров СКУД + проверка/привязка из ФОП.
Логика привязки (`ensure_binding`, `find_existing_binding`,
`find_shared_definition`, `get_category`, `binding_has_category`) не
специфична для СКС — импортируется напрямую из `scs_parameters.py`, здесь
только своя таблица `PARAM_SPECS` (категории — контроллеры
`OST_ElectricalEquipment`, устройства СКУД, `OST_ElectricalCircuit`,
`OST_GenericModel` для узлов трассы/схемы).

## skud_schematic.py
Логика кнопки **BuildSkudSchematic** («Структурная схема»): без
группы-эталона — каждый контроллер и каждое его устройство вставляются
как отдельный экземпляр типа, назначенного в настройках СКУД для
соответствующей категории (реальное устройство сопоставляется с
категорией по точному типу — `skud.category_by_type_id`, не по ключевым
словам), в точке, вычисленной от точки контроллера.

| Функция | Сигнатура | Что делает |
|---|---|---|
| `layout_points_by_level` | `layout_points_by_level(base_point, level_elevations, gap_ft)` | Точки вставки контроллеров, сгруппированных по этажу (`level_elevations` — Elevation уровня каждого контроллера, тот же порядок, что список контроллеров): один этаж — один сплошной горизонтальный ряд по X с шагом `gap_ft`, без ограничения длины; следующий этаж — со сдвигом вверх по Y на `gap_ft`, от точки клика пользователя (`base_point`) |
| `device_layout_point` | `device_layout_point(insert_pt, category_layout, category, index_in_category, step_ft)` | Точка вставки устройства: точка контроллера (`insert_pt`) + смещение `(dx, dy)` категории из `category_layout` (`{имя: (dx_ft, dy_ft)}`, из настроек) + шаг `step_ft` вправо по X на каждый следующий экземпляр той же категории у этого контроллера |

Координаты (dx, dy от контроллера) и шаг между однотипными устройствами,
а также сопоставление категория→реальные типы устройств и
категория→схемное семейство для вставки — настраиваются в окне
«Параметры СКУД» (`skud_settings.py`), включая превью раскладки.

Линии между контроллером и устройствами на схеме — простые независимые
`DetailLine` (топология "звезда"), создаются кнопкой сразу после вставки
каждой пары точек.

## fire_alarm.py
Константы и разбор адресов для **СПС и СОУЭ** (`SPS.panel`/`SOUE.panel`).
Отличие от СКС/СКУД: отдельных маркеров узлов нет — узлом шлейфа служит
само устройство, длинных участков нет, а изоляторы начинают ветвь.

Адресация: у панели «Обозначение» = `ARK` и «Адрес устройства» = `3`
(итого `ARK3`); у устройства «Адрес устройства» = `3.1.2` — панель 3,
шлейф 1, номер 2.

| Функция | Сигнатура | Что делает |
|---|---|---|
| `parse_device_address` | `parse_device_address(address)` | `"3.1.2"` → `(3, 1, 2)`; `None`, если частей не три или они нечисловые |
| `parse_panel_address` | `parse_panel_address(address)` | `"3"` → `3`; `None`, если это не одно целое число |
| `make_full_mark` | `make_full_mark(designation, address)` | `"BTH"` + `"3.1.2"` → `"BTH3.1.2"` |
| `is_isolator` | `is_isolator(el, isolator_keyword)` | Изолятор/ответвитель — по ключевому слову в имени семейства |
| `group_devices_by_loop` | `group_devices_by_loop(devices, address_by_id)` | `{(панель, шлейф): [устройства по порядковому номеру]}` |

## fire_alarm_loops.py
Построение шлейфа и расчёт его длины по координатам (без Revit API —
как `scs_addressing`).

**Ветви от изоляторов**: нумерация `K` сквозная по шлейфу, поэтому по
номеру нельзя отличить продолжение магистрали от устройства на ветви.
Решает геометрия — каждое следующее устройство цепляется к ближайшему из
кандидатов (предыдущее по порядку либо любой уже размещённый изолятор).
При равном расстоянии предпочитается изолятор, затем меньший `id`, чтобы
результат не зависел от порядка перебора.

| Функция | Сигнатура | Что делает |
|---|---|---|
| `build_loop_tree` | `build_loop_tree(nodes, panel_point=None)` | Проставляет `parent_id` каждому узлу; возвращает узлы в порядке обхода |
| `calc_loop_length_ft` | `calc_loop_length_ft(ordered_nodes, panel_point=None)` | Длина по дереву: каждое ребро один раз, ветви назад не возвращаются |
| `build_route_text` | `build_route_text(ordered_nodes, address_text_by_id)` | `"3.1.1 -> 3.1.2; 3.1.2 -> 3.1.5"` — вторая пара показывает ветвь |
| `previous_address_by_id` | `previous_address_by_id(ordered_nodes, address_text_by_id)` | `{id: адрес родителя}` — для записи «Предыдущего адреса» на устройства |
| `split_branch_devices` | `split_branch_devices(ordered_nodes)` | `(trunk_nodes, branch_nodes)` — узел считается веткой, если его родитель изолятор, но не непосредственно предыдущий по адресу узел. Используется `build_loop_circuits`, чтобы не включать ветки в магистральную цепь |
| `manhattan_ft` | `manhattan_ft(pt_a, pt_b)` | `|dx|+|dy|+|dz|` между точками |

## fire_alarm_circuits.py
Поиск панелей/устройств СПС/СОУЭ в документе, создание электрических
цепей и запись длин. Категории устройств берутся через `getattr` —
набор `BuiltInCategory` отличается между версиями Revit, и отсутствующее
имя иначе уронило бы модуль на импорте.

`resolve_system_type`/`create_circuit` здесь больше не определены — они
переехали в `electrical_circuits.py` (не специфичны для СПС/СОУЭ), но
по-прежнему импортируются в этот модуль для обратной совместимости
(`fire_alarm_buttons.py` берёт `create_circuit` отсюда же).

| Функция | Сигнатура | Что делает |
|---|---|---|
| `find_panels` | `find_panels(doc, config)` | `{номер панели: элемент}` — по рабочему набору и «Обозначению» |
| `find_devices` | `find_devices(doc, config)` | `(devices, address_by_id, address_text_by_id, skipped)`; `skipped` — с неразбираемым адресом |
| `existing_circuits_by_number` | `existing_circuits_by_number(doc, config)` | Уже созданные цепи по «Номеру цепи» — чтобы не пересоздавать |
| `device_category_id` | `device_category_id(el)` | `int(BuiltInCategory)` устройства, если это одна из `DEVICE_CATEGORIES`, иначе `None` — для подбора типа проводника по категории |
| `build_loop_nodes` | `build_loop_nodes(device_els, address_by_id, isolator_keyword)` | Узлы для `build_loop_tree` из элементов Revit |
| `write_loop_length` | `write_loop_length(circuit, ordered_nodes, panel_point, config)` | Считает и пишет длину и способ прокладки |

## fire_alarm_settings.py
Настройки СПС/СОУЭ. Один модуль на обе системы, но **разные файлы**:
`set_system("SPS")` или `set_system("SOUE")` в начале скрипта кнопки
выбирает, какой JSON читать/писать. Функции те же, что в
`scs_settings`/`skud_settings` (`get_settings_interactive`,
`get_settings_silent`, `require`, ...).

У системы могут быть свои значения по умолчанию (`SYSTEMS[...]["defaults"]`)
— они перекрывают общие из `TEXT_FIELDS`. Так задаётся, например, тип
электрической цепи: шлейф СПС создаётся как пожарная сигнализация.

## fire_alarm_buttons.py
Тела кнопок СПС/СОУЭ — общие для обеих систем, чтобы `script.py` остался
тонким (выбрать систему и вызвать функцию).

| Функция | Сигнатура | Что делает |
|---|---|---|
| `build_loop_circuits` | `build_loop_circuits(doc, settings)` | Кнопка «Цепи шлейфов»: цепь на каждый шлейф + подключение к панели. Устройства-ветки изоляторов (`split_branch_devices`) в цепь не включаются |
| `calc_loop_lengths` | `calc_loop_lengths(doc, settings)` | Кнопка «Длины шлейфов»: длина по координатам, марка и «предыдущий адрес» на устройствах |

## fire_alarm_isolator_circuits.py
Тело кнопки «Цепи изолятор-устройства СПС» (`CircuitsSPS.panel`): в отличие
от `build_loop_circuits` (весь шлейф целиком по адресации), состав каждой
цепи здесь выбирается вручную — сначала устройства пожарной сигнализации
(категория `OST_FireAlarmDevices`), затем изолятор (`OST_ElectricalEquipment`).

Правила группировки: каждое устройство ручного пуска (ИПР, слово «ручной»
в имени типа) — отдельная цепь; остальные выбранные устройства — одна
общая цепь. Если так получается больше `MAX_CIRCUITS_PER_ISOLATOR` (2)
цепей — жёсткий лимит: ничего не создаётся, кнопка показывает
предупреждение.

| Функция | Сигнатура | Что делает |
|---|---|---|
| `pick_devices_and_isolator` | `pick_devices_and_isolator(uidoc, doc)` | Один `PickObjects` на устройства и изолятор вместе (фильтр по обеим категориям); при отмене (Esc) возвращает `(None, None)`, при неверном составе (не ровно один изолятор / нет устройств) просит повторить выбор |
| `is_manual_device` | `is_manual_device(el)` | Устройство ручного пуска — по слову «ручной» в имени семейства/типа |
| `split_manual_devices` | `split_manual_devices(device_els)` | `(ручные, остальные)` |
| `build_isolator_device_circuits` | `build_isolator_device_circuits(doc, device_els, isolator_el, settings)` | Строит цепи по правилам группировки, проставляет «Панель», «Имя нагрузки», «Проводник»; `(created_circuits, error_message)` |

## media_keys.py
Эмуляция нажатий медиаклавиш Windows (`Music.panel`).

Константы: `VK_MEDIA_NEXT`, `VK_MEDIA_PREV`, `VK_MEDIA_PLAY_PAUSE`,
`VK_VOLUME_DOWN`, `VK_VOLUME_UP`.

| Функция | Сигнатура | Что делает |
|---|---|---|
| `press_key` | `press_key(key)` | Имитирует нажатие и отпускание виртуальной клавиши `key` через `ctypes`/`user32` |

## Куда добавлять новое

- Новый хелпер, полезный **вне зависимости от дисциплины** (геометрия, параметры, UI) → существующий общий модуль (`geometry.py`, `params.py`, `selection.py`) или новый общий модуль рядом с ними.
- Логика, специфичная **для одной дисциплины/панели** (СКС, потом — например, ОПС/СБ) → отдельный модуль по образцу `scs.py` (например `fire_alarm.py`, `security.py`).
- Скрипт кнопки (`script.py`) должен остаться последовательностью вызовов этих функций, без копирования их тел.
