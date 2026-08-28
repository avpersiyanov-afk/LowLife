# tests/

Юнит-тесты для чистой (без Revit API) логики в `lib/lowlife/`: графовые и
геометрические алгоритмы, которые работают на обычных `dict`/`tuple`, а не
на Revit-элементах — см. `lib/README.md` за описанием каждого модуля.

Покрыты:

- `scs_addressing.py` — классификация точек относительно линий, Дейкстра до
  корня, обход в глубину для нумерации адресов, выбор корней с учётом
  расстояния.
- `scs_circuits.py` — нормализация текстовых значений, сборка графа по
  адресам, A\*, разбивка длины по способу прокладки (труба/лоток/труба
  открыто), согласованное округление.
- `fire_alarm_loops.py` — построение дерева шлейфа СПС/СОУЭ (включая ветви
  от изоляторов) и расчёт его длины.
- `skud_schematic.py` (частично) — чистые функции подбора типовой группы
  для структурной схемы СКУД: `passage_points_of` (разбивка по точкам
  прохода), `signature_of` (сигнатура состава), `match_group_name`,
  `signature_text`, `majority_value` (голосование за помещение),
  `category_of_from_type_map`/`invert_*`. `lowlife.params` модуль
  импортирует лениво с запасным вариантом, поэтому остаётся импортируемым
  вне Revit; `classify_members`/`group_signature`/раскладочные точки
  (нужен `doc`/`XYZ`) не тестируются.
- `scs.py` (частично) — только `merge_nodes`/`_pick_cluster_point`
  (кластеризация узлов трассы по близости при расстановке маркеров,
  PlaceRouteNodes/route_nodes.py): эти функции работают с обычными
  dict/точками и не вызывают `classify_element`/`safe_element_name`
  (единственное, что в scs.py трогает Revit API). Остальной scs.py
  (`classify_element`, `get_workset_name`, `clear_stray_address_params`,
  `collect_target_panel_devices`, ...) по-прежнему не тестируется вне
  Revit.
- `scs_schematic.py` (частично) — только `panel_riser_x` (X стояка
  панели по её порядковому номеру, структурная схема СКС): чистая
  формула без Revit API. `sync_panel_buses` импортирует
  `lowlife.sot_schematic` (Revit API) лениво, внутри тела функции, ровно
  затем, чтобы этот модуль оставался импортируемым для теста
  `panel_riser_x` — сама `sync_panel_buses` не тестируется вне Revit.

Не покрыто и не может быть протестировано вне Revit: `route_nodes.py`,
`route_addressing.py`, `skud.py`, `fire_alarm.py`,
`fire_alarm_circuits.py`, `geometry.py`, `params.py`, `selection.py`,
`sot_schematic.py`, `sot_levels.py`, `sot_layout_state.py`, `room_info.py`
— все они напрямую импортируют `Autodesk.Revit.DB`. Также не покрыты
сами кнопки (`LowLife.tab/**/script.py`) — они оркестрируют вызовы в
Revit и не запускаются вне его процесса.

## Требования

**Python 2.7**, не Python 3. Это намеренно — сам код в `lib/lowlife/`
написан для IronPython/CPython 2 внутри Revit (см. `CLAUDE.md`,
раздел про `unicode(...)`/`u"..."`), и `scs_circuits.py`/`fire_alarm_loops.py`
используют встроенную функцию `unicode()`, которой нет в Python 3 — тесты
для них упадут с `NameError` под Python 3. (`scs_addressing.py` встроенных
"питон-2-измов" не использует и по факту тоже отработает под Python 3, но
для единообразия весь набор ориентирован на Python 2.7.)

Современный `pytest` (5+) поддержку Python 2 не устанавливает — нужна
версия `pytest<5`:

```
pip install "pytest<5"
```

## Запуск

Из корня репозитория:

```
python -m pytest tests -v
```

`conftest.py` сам добавляет `lib/` в `sys.path`, так что тесты импортируют
модули так же, как это делают кнопки внутри Revit:
`from lowlife import scs_addressing`.

## Статус

Прогоняются: `python -m pytest tests -v` под Python 2.7.18 + pytest 4.6.11
— 63/63 проходят (последняя проверка: 2026-08-26). Раньше в среде, где
писался этот набор, не было интерпретатора Python вообще, и часть тестов
была добавлена и проверена только построчным прослеживанием логики — с тех
пор это устранено, весь набор реально выполняется.
