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

## scs.py
Константы и логика, специфичные для СКС / телекоммуникационных трасс
(`SCS.panel`). Сюда добавлять только то, что относится именно к этой
дисциплине — общие геометрические/параметрические вещи должны идти в
`geometry.py`/`params.py`.

Константы: `FAMILY_FILTER`, `CABLE_PARAM_NAME`, `ROUTE_PARAM_NAME`,
`ROUTE_PARAM_VALUE`, `DEVICE_CABLE_TYPE_VALUE`, `DEVICE_KEYWORDS`,
`DEVICE_EXCLUDE_KEYWORDS`, `PANEL_KEYWORDS`, `PANEL_EXCLUDE_KEYWORDS`,
`OFFSET_PARAM_NAMES`, `CATEGORY_PRIORITY` (`("panel", "device", "route")`).

| Функция | Сигнатура | Что делает |
|---|---|---|
| `detect_cable_type` | `detect_cable_type(el)` | Тип прокладки кабеля («Труба», «Труба открыто», «Лоток») по имени типоразмера/семейства сегмента трассы |
| `classify_element` | `classify_element(el, categories)` | `categories` — список `(name, keywords, exclude_keywords)`, проверяется по порядку; возвращает `name` первой подошедшей или `None` |
| `text_match_device` | `text_match_device(el, device_keywords=..., device_exclude_keywords=...)` | Тонкая обёртка над `classify_element` для одной категории "device" (оставлена для обратной совместимости) |
| `resolve_category` | `resolve_category(categories, priority=CATEGORY_PRIORITY)` | Из списка категорий объединённого узла выбирает одну по приоритету (panel > device > route) |
| `merge_nodes` | `merge_nodes(nodes, tol, points_close_fn)` | Объединяет узлы трассы ближе `tol` друг к другу в один, суммируя `categories`, `segment_ids`, `device`; `points_close_fn` обычно — `geometry.points_close` |
| `clear_stray_address_params` | `clear_stray_address_params(doc, param_names, allowed_type_ids)` | Ищет элементы (Обобщённые модели + категории панелей/устройств), у которых заполнен один из `param_names`, но тип не входит в `allowed_type_ids`, и очищает эти параметры. Нужно вызывать в RenumberAddresses/SyncCircuitsAndLengths перед сбором узлов — иначе застрявший адрес на устройстве (с прежних запусков или ручного ввода) может быть спутан с адресом реального узла маршрута. Вызывать внутри `revit.Transaction` |

## scs_settings.py
**Одно общее окно настроек на все три кнопки `SCS.panel`** (PlaceRouteNodes /
RenumberAddresses / SyncCircuitsAndLengths): выбор **типа для вставки**
(панель/устройство/маршрут/стояк — из типов категории «Обобщённые модели»
в проекте) + текстовые параметры (`TEXT_FIELDS`, сгруппированы в окне по
разделам через префикс `"[Раздел] Подпись"`). Всё хранится в конфиге
pyRevit (`pyRevit_config.ini`, секция `LowLifeSCS`) — **не в
репозитории**: имена параметров и семейств зависят от проекта
пользователя, дефолты в `scs.py` намеренно пустые. Требования к
семействам/параметрам — см. `docs/scs-panel.md`.

Так как окно общее, форма **не блокирует** сохранение из-за пустых полей —
у разных кнопок разный набор нужных полей (RenumberAddresses не
использует поля SyncCircuitsAndLengths и наоборот). Каждая кнопка сама
проверяет свой набор через `require()` сразу после получения settings.

| Функция | Сигнатура | Что делает |
|---|---|---|
| `get_settings_interactive` | `get_settings_interactive(doc)` | Показывает окно, сохраняет введённое и возвращает готовый словарь настроек (списки уже разобраны из строк через запятую, id типов — строки); `None`, если нажата «Отмена» |
| `require` | `require(settings, keys)` | Проверяет, что перечисленные ключи заполнены (списки — что непусты); если нет — `forms.alert(exitscript=True)` со списком недостающих полей. Вызывать сразу после `get_settings_interactive` |
| `load_saved_values` | `load_saved_values()` | Сырые строковые значения из конфига, иначе — значения по умолчанию из `scs.py` |
| `save_values` | `save_values(values)` | Записывает словарь строковых значений в конфиг |
| `show_settings_form` | `show_settings_form(doc, values)` | Само модальное окно (`ScrollViewer` + кнопки типов через `forms.SelectFromList`); используется внутри `get_settings_interactive` |
| `to_runtime_settings` | `to_runtime_settings(values)` | Строки → типы (списки через запятую → `list`); id типов не трогает |
| `list_generic_model_symbols` | `list_generic_model_symbols(doc)` | Все `FamilySymbol` категории «Обобщённые модели» в проекте |

Обычный сценарий использования в кнопке:
```python
from lowlife import scs_settings
from lowlife.scs_settings import get_settings_interactive

settings = get_settings_interactive(doc)
if settings is None:
    forms.alert(u"Операция отменена.", exitscript=True)

scs_settings.require(settings, ["family_filter", "cable_param_name", "panel_type_id"])

FAMILY_FILTER = settings["family_filter"]
DEVICE_KEYWORDS = settings["device_keywords"]  # уже list
PANEL_TYPE_ID = ElementId(int(settings["panel_type_id"]))
panel_symbol = doc.GetElement(PANEL_TYPE_ID)
```

## scs_addressing.py
Логика кнопки **RenumberAddresses** («Адреса узлов»): классификация точек
относительно линий трассы (`classify_point` → `NODE_STRICT`/`NODE_ON_LINE`/
`NODE_NEAR_ENDPOINT`/`OFFSET_MARKER`/`UNCONNECTED`), построение соседства
узлов на линии, обход в ширину от корней (панелей/стояков), код этажа из
имени уровня/вида. Работает с обычными dict-записями `{"point": (x,y),
...}`, не с Revit-элементами — вызывающий скрипт сам заполняет флаги
`is_riser`/`is_panel` (по `ElementId` типа и по ключевым словам
соответственно) перед вызовом `classify_point`.

Ключевые функции: `classify_point`, `add_neighbor`, `find_nearest_real_node`,
`find_best_real_node_for_offset`, `get_floor_code_from_view`,
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
