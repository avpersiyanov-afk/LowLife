# FamilyCatalog — плагин Revit «Каталог семейств» (без pyRevit)

Самостоятельный Revit add-in из двух команд. **pyRevit не нужен.** Целевая версия — **Revit 2024** (.NET Framework 4.8).

## Что делает

Отдельная вкладка **«Каталог семейств»** → панель **«Семейства из каталога»** с двумя кнопками:

- **Семейства из каталога** — сверяет семейства выбранных категорий модели с папкой-каталогом
  `.rfa`: по скрытой метке даты (ExtensibleStorage) vs дата файла показывает таблицу
  «актуально / устарело / нет метки / нет в каталоге»; отмеченные обновляет из файла
  (перезагрузка через «Загрузить в проект», при необходимости — checkout из центральной,
  замена значений параметров, при различии имён — переименование).
  **Shift+клик** — сменить папку каталога.
- **Загрузить семейства** — загружает семейства из каталога в модель: выбор разделов
  (папок), таблица файлов с галочками, затем окно выбора типоразмеров
  (для моделируемых семейств типы берутся из одноимённого `.txt`; «← Назад» —
  вернуться к таблице файлов). **Shift+клик** — сменить папку каталога.

Путь к папке-каталогу общий для обеих кнопок, хранится в
`%APPDATA%\FamilyCatalog\catalog_root.txt`.
Схема скрытой метки (`ExtensibleStorage`, GUID `d7b1e6a2-…`) совпадает с расширением
LowLife — метки читаются в обе стороны.

## Сборка (без Visual Studio)

Нужны только: Windows + установленный Revit 2024. Компилятор `csc.exe` из
.NET Framework уже есть в системе (`C:\Windows\Microsoft.NET\Framework64\v4.0.30319\`).

```
build.cmd
```

Результат — папка `bin\`:
```
bin\
├── FamilyCatalog.addin
└── FamilyCatalog\
    ├── FamilyCatalog.dll
    ├── sync.png
    └── load.png
```

## Установка

```
install.cmd
```
Копирует в `%APPDATA%\Autodesk\Revit\Addins\2024\`:
- `FamilyCatalog.addin`
- `FamilyCatalog\` (dll + иконки)

Затем **перезапустить Revit 2024**.

### Вручную

Положить `FamilyCatalog.addin` в `%APPDATA%\Autodesk\Revit\Addins\2024\`, а рядом папку
`FamilyCatalog\` с `FamilyCatalog.dll` и иконками. Путь к dll в `.addin` указан
относительно него: `FamilyCatalog\FamilyCatalog.dll`.

## Удаление

```
uninstall.cmd
```
Revit должен быть **закрыт** (пока он запущен, `FamilyCatalog.dll` заблокирован).
Скрипт удаляет `FamilyCatalog.addin` и папку `FamilyCatalog\` из
`%APPDATA%\Autodesk\Revit\Addins\2024\` и спрашивает про настройки
(`%APPDATA%\FamilyCatalog\`).

Вручную: удалить оба —
`%APPDATA%\Autodesk\Revit\Addins\2024\FamilyCatalog.addin` **и** папку
`%APPDATA%\Autodesk\Revit\Addins\2024\FamilyCatalog\`. Только папки
недостаточно: Revit будет пытаться прочитать `.addin` и ругаться на отсутствие
dll. Скрытые метки даты в `.rvt` останутся (невидимы, ничему не мешают).

## Файлы проекта

| файл | что |
|---|---|
| `Core.cs` | скан каталога, похожесть имён, метка даты (ExtensibleStorage), загрузка семейства («Load into Project»), checkout worksharing, переименование, конвейеры обновления/загрузки, парсер `.txt` |
| `Windows.cs` | окна WPF (таблицы, выбор типоразмеров, мультивыбор, отчёт), диалоги |
| `Commands.cs` | две команды `IExternalCommand` |
| `App.cs` | `IExternalApplication` — лента |
| `build.cmd` / `install.cmd` | сборка / установка |
| `FamilyCatalog.addin` | манифест add-in |

Порт логики из `lib/lowlife/family_catalog.py`. Код на C# 5 (совместим со
встроенным компилятором `csc.exe`).
