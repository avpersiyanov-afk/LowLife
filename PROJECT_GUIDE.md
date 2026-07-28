# PROJECT_GUIDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A pyRevit extension (IronPython/CPython 2 scripts run inside Revit). There is no build step, package manager, linter, or test suite — `tests/` and `examples/` exist but are currently empty. "Running" the code means loading it into Revit through pyRevit.

## Extension layout requirement (important, non-obvious)

pyRevit installs extensions added by a GitHub URL by cloning the repo directly into `%APPDATA%\pyRevit\Extensions\<name>.extension\` — pyRevit itself supplies the `.extension` wrapper folder. Because of this, **`LowLife.tab` must stay at the repo root**, not nested inside a `LowLife.extension/` folder in the repo. Wrapping it again produces a double-nested `.extension\.extension\` path and the tab won't load. Do not "fix" this by re-adding an extension wrapper folder.

## Deploying/testing a change

The user updates their Revit installation by re-pulling this repo via pyRevit's extension manager (GitHub URL), then reloading pyRevit / restarting Revit. There is no local Revit instance to run scripts against in this environment — changes can only be verified by reading the code, not by executing it. Say so explicitly rather than claiming a script "works."

One exception: `LowLife.tab/SCS.panel/SeedMySettings.pushbutton/` is local-only (excluded via `.gitignore`, along with `*.local.md`) — it hardcodes one project's real parameter/family names so the user doesn't have to fill the settings form by hand. Never commit real parameter names from that file or from `docs/scs-parameters.local.md`; the tracked docs (`docs/scs-panel.md`) intentionally describe *what* parameters are needed without naming them.

## Shared library (`lib/`)

`lib/` sits next to `LowLife.tab` at the extension root, so pyRevit adds it to `sys.path` automatically — any `script.py` can `from lowlife.xxx import yyy` with no path setup. See `lib/README.md` for the full function-by-function reference; the important structural point is the split between:
- **Discipline-agnostic helpers** (`geometry.py`, `params.py`, `selection.py`) — pure Revit-API utilities usable by any future panel.
- **SCS-specific logic** (`scs.py`, `scs_addressing.py`, `scs_circuits.py`, `scs_settings.py`) — everything for the `SCS.panel` toolset (structured cabling). New disciplines (fire alarm, security) should get their own `scs_*`-style module rather than being folded into these.

Button scripts (`script.py`) are meant to stay thin orchestration — collect elements, call library functions, write results in a transaction. Don't grow business logic back into a button script; extract it into `lib/lowlife/` instead, matching the existing pattern.

## SCS.panel pipeline

Three buttons operate on the same marker-element ecosystem and must be run in order, each consuming the previous one's output:
1. **PlaceRouteNodes** ("Узлы трассы") — classifies points along route lines into 4 categories (`riser > panel > device > route` priority) and inserts/updates the matching Generic Model family instance at each point.
2. **RenumberAddresses** ("Адреса узлов") — builds a geometric graph from route/riser markers only and BFS-assigns address strings (`F1.3`) from panel/riser roots.
3. **SyncCircuitsAndLengths** ("Синхронизация цепей") — builds a graph from the *address* parameter chain (not geometry) and A*-routes each electrical circuit from its panel to its device, writing lengths/labels/numbers.

Key architectural points that aren't obvious from any single file:
- All three buttons share **one settings window** (`scs_settings.get_settings_interactive`), because they operate on the same families/parameters. Settings persist in a plain JSON file at `%APPDATA%\pyRevit\LowLifeSCS_settings.json` — deliberately *not* `pyrevit.script.get_config()`, which didn't reliably share a config section across different `script.py` files in testing. Don't reintroduce the pyRevit-config approach without re-verifying that assumption.
- Because the form is shared, it cannot block saving on missing fields (a field required by one button may be irrelevant to another). Each button instead calls `scs_settings.require(settings, [keys...])` itself right after loading settings, listing only the keys *it* needs.
- `scs.py`'s default parameter/family-name constants are intentionally blank strings/lists — these are per-project conventions (e.g. `SMNX_...` shared parameters) and must never be hardcoded into tracked files. Classification *keywords* (коннектор, розетка, панель, стояк, ...) are treated as generic vocabulary and do get sensible defaults.
- `PlaceRouteNodes` and `RenumberAddresses`/`SyncCircuitsAndLengths` guard against stale data: `clear_stray_address_params` wipes address parameters left on elements that are no longer route/riser-typed (e.g. after a device's family got split out of a shared marker family in an earlier project iteration), and `SyncCircuitsAndLengths` reports (rather than silently overwrites) duplicate addresses.

## IronPython/Revit-API gotchas already worked around here

- `el.Name` throws an ambiguous-binding error on some element types (notably `Family`/`FamilySymbol`) under IronPython; use `Element.Name.GetValue(el)` instead (see `_safe_element_name` in `scs_settings.py`).
- Listing all loaded family types of a category (including unplaced ones) must go through `FilteredElementCollector(doc).OfClass(Family)` → `family.GetFamilySymbolIds()`, not `FilteredElementCollector(doc).OfCategory(...).OfClass(FamilySymbol)`, which can miss unplaced types.
- WPF settings windows: never set `Topmost` on a window that will itself open another WPF window (e.g. `forms.SelectFromList`) — the child window gets stuck behind it with no way to bring it forward.
- This is Python 2 (IronPython): `unicode(...)` and `u"..."` literals are used deliberately throughout; don't "modernize" to Python 3 string handling.

## Icons

Pushbutton icons are 96×96 PNGs generated programmatically with Pillow (flat style: soft rounded-square background, blue line-art glyph, occasional orange accent) rather than hand-drawn or fetched — see any prior icon-generation script for the palette/pattern if adding a new button.

---

# Русская версия

Этот файл — ориентир для Claude Code (и для людей) при работе с кодом в этом репозитории.

## Что это

pyRevit-расширение (скрипты IronPython/CPython 2, выполняются внутри Revit). Нет ни шага сборки, ни менеджера пакетов, ни линтера, ни тестов — `tests/` и `examples/` существуют, но пока пустые. «Запуск» кода означает его загрузку в Revit через pyRevit.

## Требование к структуре расширения (важно, неочевидно)

pyRevit устанавливает расширения, добавленные по ссылке GitHub, клонируя репозиторий прямо в `%APPDATA%\pyRevit\Extensions\<name>.extension\` — обёртку `.extension` создаёт сам pyRevit. Поэтому **`LowLife.tab` должен оставаться в корне репозитория**, а не быть вложенным в папку `LowLife.extension/` внутри репозитория. Повторное оборачивание даёт двойную вложенность `.extension\.extension\`, и вкладка не загружается. Не «исправляйте» это повторным добавлением папки-обёртки расширения.

## Развёртывание/проверка изменений

Пользователь обновляет расширение в Revit, повторно подтягивая этот репозиторий через менеджер расширений pyRevit (по ссылке GitHub), затем перезагружает pyRevit / перезапускает Revit. В этом окружении нет локального экземпляра Revit, на котором можно было бы запускать скрипты — изменения можно проверить только чтением кода, не выполнением. Явно так и говорите, а не утверждайте, что скрипт «работает».

Исключение: `LowLife.tab/SCS.panel/SeedMySettings.pushbutton/` — локальный файл (исключён через `.gitignore`, вместе с `*.local.md`) — в нём зашиты реальные имена параметров/семейств конкретного проекта, чтобы не заполнять форму настроек вручную. Никогда не коммитьте реальные имена параметров из этого файла или из `docs/scs-parameters.local.md`; отслеживаемая документация (`docs/scs-panel.md`) намеренно описывает, *какие* параметры нужны, без указания конкретных имён.

## Общая библиотека (`lib/`)

`lib/` лежит рядом с `LowLife.tab` на уровне расширения, поэтому pyRevit сам добавляет её в `sys.path` — любой `script.py` может писать `from lowlife.xxx import yyy` без настройки путей. Полный список функций по модулям — в `lib/README.md`; важный структурный момент — разделение на:
- **Хелперы, не привязанные к дисциплине** (`geometry.py`, `params.py`, `selection.py`) — чистые утилиты Revit API, пригодные для любой будущей панели.
- **Логика, специфичная для СКС** (`scs.py`, `scs_addressing.py`, `scs_circuits.py`, `scs_settings.py`) — всё для набора инструментов `SCS.panel` (структурированная кабельная система). Новые дисциплины (ОПС, СБ) должны получать свой модуль в стиле `scs_*`, а не подмешиваться в существующие.

Скрипты кнопок (`script.py`) должны оставаться тонкой оркестрацией — собрать элементы, вызвать функции библиотеки, записать результат в транзакции. Не давайте бизнес-логике снова разрастаться внутри скрипта кнопки — выносите её в `lib/lowlife/`, по уже устоявшемуся образцу.

## Конвейер SCS.panel

Три кнопки работают с одной и той же экосистемой элементов-маркеров и должны запускаться по порядку, каждая следующая использует результат предыдущей:
1. **PlaceRouteNodes** («Узлы трассы») — классифицирует точки вдоль линий трассы на 4 категории (приоритет `стояк > панель > устройство > маршрут`) и вставляет/обновляет в каждой точке соответствующий экземпляр семейства «Обобщённая модель».
2. **RenumberAddresses** («Адреса узлов») — строит геометрический граф только по маркерам маршрута/стояков и присваивает адреса (`F1.3`) обходом в ширину от корней (панелей/стояков).
3. **SyncCircuitsAndLengths** («Синхронизация цепей») — строит граф по цепочке параметра *адреса* (не по геометрии) и прокладывает каждую электрическую цепь алгоритмом A* от панели до устройства, записывая длины/подписи/номера.

Ключевые архитектурные моменты, не очевидные из одного файла:
- Все три кнопки используют **одно общее окно настроек** (`scs_settings.get_settings_interactive`), поскольку работают с одними и теми же семействами/параметрами. Настройки хранятся в обычном JSON-файле `%APPDATA%\pyRevit\LowLifeSCS_settings.json` — намеренно **не** через `pyrevit.script.get_config()`, который на практике не гарантированно расшаривал секцию конфига между разными `script.py`. Не возвращайтесь к подходу через pyRevit-конфиг, не перепроверив это предположение заново.
- Поскольку форма общая, она не может блокировать сохранение из-за пустых полей (поле, обязательное для одной кнопки, может быть не нужно другой). Вместо этого каждая кнопка сама вызывает `scs_settings.require(settings, [keys...])` сразу после получения настроек, перечисляя только нужные ей ключи.
- Константы имён параметров/семейств по умолчанию в `scs.py` намеренно пустые строки/списки — это соглашения конкретного проекта (например, общие параметры `SMNX_...`), и их нельзя зашивать в отслеживаемые файлы. Ключевые слова классификации (коннектор, розетка, панель, стояк, ...) считаются общей лексикой и имеют разумные значения по умолчанию.
- `PlaceRouteNodes` и `RenumberAddresses`/`SyncCircuitsAndLengths` защищаются от устаревших данных: `clear_stray_address_params` очищает параметры адреса, оставшиеся на элементах, которые больше не имеют типа маршрута/стояка (например, после того как семейство устройства было выделено из общего семейства-маркера на более ранней итерации проекта), а `SyncCircuitsAndLengths` сообщает о дублирующихся адресах, а не молча их перезаписывает.

## Грабли IronPython/Revit API, уже обойдённые здесь

- `el.Name` выбрасывает ошибку неоднозначного связывания на некоторых типах элементов (в частности `Family`/`FamilySymbol`) в IronPython; используйте вместо этого `Element.Name.GetValue(el)` (см. `_safe_element_name` в `scs_settings.py`).
- Перечисление всех загруженных типоразмеров семейства категории (включая ещё не вставленные) должно идти через `FilteredElementCollector(doc).OfClass(Family)` → `family.GetFamilySymbolIds()`, а не через `FilteredElementCollector(doc).OfCategory(...).OfClass(FamilySymbol)`, который может пропустить невставленные типы.
- Окна настроек на WPF: никогда не ставьте `Topmost` на окно, которое само открывает другое WPF-окно (например, `forms.SelectFromList`) — дочернее окно застревает позади него, и его невозможно вывести на передний план.
- Это Python 2 (IronPython): `unicode(...)` и литералы `u"..."` используются по всему коду намеренно; не «модернизируйте» их под обработку строк Python 3.

## Иконки

Иконки кнопок — это PNG 96×96, сгенерированные программно через Pillow (плоский стиль: мягкий скруглённый фон, синий силуэт-иконка, изредка оранжевый акцент), а не нарисованные вручную или взятые откуда-то ещё — при добавлении новой кнопки ориентируйтесь на палитру/паттерн любого из предыдущих скриптов генерации иконок.
