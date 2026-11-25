# Универсальный служебный расчёт цепей — план реализации

> **Для исполнителя:** перед началом каждого задания использовать `superpowers:subagent-driven-development` или `superpowers:executing-plans`. Выполнять задачи последовательно, после каждой запускать указанные проверки.

**Цель:** Добавить на `Tools.panel` служебный расчёт маршрутов и длин для СКС, СКУД, СПС и СОУЭ, не изменяя текущие кнопки дисциплин.

**Архитектура:** Общая библиотека будет строить геометрический граф трасс по всем этажам, находить переходы через шахты, рассчитывать отдельные или последовательные маршруты и создавать обновляемую маркировку. Системные различия будут изолированы адаптерами сбора цепей. Существующие кнопки и их настройки не вызываются для записи рабочих результатов.

**Стек:** Python 2/3 совместимый код pyRevit, Revit API, pytest для чистых функций, Revit MCP для проверки на модели.

**Спецификация:** `docs/superpowers/specs/2026-11-24-scs-service-routing-design.md`

## Глобальные ограничения

- Не изменять рабочие скрипты `SCS.panel`, `SKUD.panel`, `SPS.panel`, `SOUE.panel`.
- Использовать существующие функции из `lib/lowlife` после проверки `lib/README.md`.
- Новые настройки хранить отдельно и не записывать реальные имена параметров в репозиторий.
- Сохранять Python 2/3 совместимость.
- Все новые кнопки должны иметь русские и английские подписи в `bundle.yaml`.
- Перед завершением выполнить `python -m pytest tests`.

## Файловая структура

- Создать `lib/lowlife/service_circuit_graph.py` для сбора кривых, разбиения на рёбра, пересечений и поиска путей.
- Создать `lib/lowlife/service_circuit_risers.py` для шахт и вертикальных переходов.
- Создать `lib/lowlife/service_circuit_adapters.py` для общих входных записей и адаптеров СКС/СКУД/СПС/СОУЭ.
- Создать `lib/lowlife/service_circuit_lengths.py` для длины рёбер, категорий прокладки и отчётов о неизвестных участках.
- Создать `lib/lowlife/service_circuit_marks.py` для обновляемой служебной графики.
- Создать отдельное хранилище настроек `service_circuit_settings.py` по образцу существующего `settings_core`.
- Создать тонкие `script.py` и `bundle.yaml` в `Tools.panel/ServiceCircuitCalculateAndMark.pushbutton`, `ServiceCircuitGraph.pushbutton`, `ServiceCircuitRisers.pushbutton`, `ServiceCircuitLengths.pushbutton`, `ServiceCircuitMarks.pushbutton`.
- Добавить чистые тесты в `tests/test_service_circuit_graph.py`, `tests/test_service_circuit_risers.py`, `tests/test_service_circuit_adapters.py`, `tests/test_service_circuit_lengths.py`.

## Review Focus

- Два разных пути используют один и тот же участок трассы, но длина каждой цепи считается отдельно.
- СПС/СОУЭ содержат десятки устройств и требуют последовательного маршрута.
- СКУД содержит несколько устройств в одной цепи.
- Шахта проходит через несколько этажей, но трасса подключена к ней со смещением в пределах допуска.
- Путь разорван или переход между этажами отсутствует.

### Task 1: Общая модель цепи и конфигурация систем

**Files:**
- Create: `lib/lowlife/service_circuit_adapters.py`
- Create: `lib/lowlife/service_circuit_settings.py`
- Create: `tests/test_service_circuit_adapters.py`

**Interfaces:**
- `CircuitRecord(system_kind, circuit_id, source_id, device_ids, route_mode, ...)`
- `collect_circuits(doc, settings) -> list[CircuitRecord]`
- `normalize_system_kind(value) -> str`

- [ ] Написать тесты для СКС/СКУД с несколькими устройствами и СПС/СОУЭ с последовательностью.
- [ ] Запустить тесты и убедиться, что они падают до реализации.
- [ ] Реализовать адаптеры поверх существующих функций сбора цепей, не копируя их тела.
- [ ] Добавить отдельные настройки системы, маски типов и режим `sequence`/`per_device`/`ring`.
- [ ] Запустить целевые тесты.

### Task 2: Геометрический граф трасс

**Files:**
- Create: `lib/lowlife/service_circuit_graph.py`
- Create: `tests/test_service_circuit_graph.py`

**Interfaces:**
- `collect_route_curves(doc, settings) -> list[RouteCurve]`
- `build_graph(route_curves, tolerance) -> RouteGraph`
- `nearest_graph_node(graph, point, level_id=None) -> NodeMatch`
- `find_path(graph, start_id, end_id) -> PathResult`

- [ ] Написать тесты на пересечение, Т-образную ветку, общие рёбра и разорванный граф.
- [ ] Реализовать разбиение кривых на соседние рёбра с сохранением `ElementId`, уровня, способа прокладки и длины.
- [ ] Использовать длину исходной кривой или осевую длину для ортогональных участков.
- [ ] Реализовать A* или Дейкстру с длиной ребра как стоимостью.
- [ ] Запустить целевые тесты.

### Task 3: Шахты и вертикальные переходы

**Files:**
- Create: `lib/lowlife/service_circuit_risers.py`
- Create: `tests/test_service_circuit_risers.py`

**Interfaces:**
- `collect_shaft_instances(doc, keywords) -> list[ShaftRecord]`
- `find_riser_links(graph, shafts, tolerance) -> list[RiserLink]`
- `direction_for_path(path, levels) -> str`
- `missing_riser_report(...) -> list[Issue]`

- [ ] Написать тесты для направлений вверх, вниз, вверх/вниз и отсутствующего продолжения.
- [ ] Использовать bounding box семейства шахт `SMNX_GM_т_Шахта инж. коммуникаций`.
- [ ] Фильтровать типы по `СС`, `СБ`, `СПЗ`.
- [ ] Связать графы разных этажей через шахты в пределах допуска.
- [ ] Запустить целевые тесты и проверить реальные типы через Revit MCP.

### Task 4: Расчёт маршрутов и длин

**Files:**
- Create: `lib/lowlife/service_circuit_lengths.py`
- Create: `tests/test_service_circuit_lengths.py`

**Interfaces:**
- `route_circuit(graph, circuit, riser_links) -> CircuitRouteResult`
- `route_sequence(graph, source, devices, ring, riser_links) -> SequenceRouteResult`
- `calculate_route_lengths(route, classification_rules) -> LengthBreakdown`
- `validate_route_result(result) -> list[Issue]`

- [ ] Написать тесты на неизвестный способ прокладки, несколько устройств и последовательную цепь.
- [ ] Для `per_device` строить путь от источника к каждому устройству.
- [ ] Для `sequence` строить путь между соседними устройствами.
- [ ] Для `ring` добавлять обратный участок.
- [ ] Не записывать фиктивную длину при разрыве.
- [ ] Учитывать `unknown` отдельно и применять согласованное правило оценки.
- [ ] Запустить целевые тесты.

### Task 5: Запись результатов и служебная маркировка

**Files:**
- Create: `lib/lowlife/service_circuit_marks.py`
- Create: `LowLife.tab/Tools.panel/ServiceCircuitMarks.pushbutton/script.py`
- Create: `LowLife.tab/Tools.panel/ServiceCircuitMarks.pushbutton/bundle.yaml`
- Create: `LowLife.tab/Tools.panel/ServiceCircuitMarks.pushbutton/icon.png`
- Create: `LowLife.tab/Tools.panel/ServiceCircuitMarks.pushbutton/icon.dark.png`

- [ ] Написать чистые тесты построения текста марки и идентификатора обновления.
- [ ] Реализовать удаление/обновление только служебных элементов текущего запуска.
- [ ] Добавить текст номера, источника, устройств, длины, типов прокладки и статуса.
- [ ] Для разрыва показывать координату и ближайшие элементы.
- [ ] Проверить локализацию `title_en` и `tooltip_en`.

### Task 6: Диагностические кнопки

**Files:**
- Create: `Tools.panel/ServiceCircuitGraph.pushbutton/*`
- Create: `Tools.panel/ServiceCircuitRisers.pushbutton/*`
- Create: `Tools.panel/ServiceCircuitLengths.pushbutton/*`

- [ ] Реализовать тонкие скрипты, вызывающие общую библиотеку.
- [ ] Добавить отчёты без записи рабочих параметров.
- [ ] Проверить запуск на текущем виде и на всех этажах.

### Task 7: Единая кнопка

**Files:**
- Create: `Tools.panel/ServiceCircuitCalculateAndMark.pushbutton/*`
- Modify: `Tools.panel/bundle.yaml` only if required for layout.

- [ ] Собрать последовательность проверки, графа, стояков, маршрутов, записи и маркировки.
- [ ] Выполнить запись в одной транзакции после успешной валидации.
- [ ] Добавить итоговый отчёт по системам, цепям, разрывам и неизвестным участкам.
- [ ] Запустить полный набор тестов.

### Task 8: Проверка на модели

**Files:**
- Modify only if diagnostics expose a defect.

- [ ] Через Revit MCP проверить шахты `ВИС_СС`, `ВИС_СПЗ`, `ВИС_СС_СПЗ`.
- [ ] Проверить маршруты СКС и СКУД с общими участками.
- [ ] Проверить длинные цепи СПС и СОУЭ.
- [ ] Создать контролируемый разрыв и убедиться, что место отображается в отчёте.
- [ ] Запустить `python -m pytest tests`.

После завершения плана выполнить отдельный ревью служебной ветки и только затем обсуждать перенос логики в рабочие кнопки.
