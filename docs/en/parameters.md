[Русский](../parameters.md) | **English**

# The parameters LowLife works with

This page lists the parameters that have to be created in the project for the LowLife buttons to work.

**Name the parameters according to your shared parameters file.** The «Example name» column shows what a parameter might be called (`LL_` is a placeholder project prefix). If your shared parameters file already has a parameter with the right meaning, there's no need to create a new one — use it.

## How to prepare a project

**The easiest way is the «Shared parameters» button** (the «Tools» panel). It shows the parameters from the table below for the chosen systems, suggests similar parameters already in your shared parameters file right away (for example «Wire length» with the project's prefix), lets you fix the names, binds the parameters to the right project categories and writes the names into the buttons' settings. It adds missing parameters to the shared parameters file only if «Write to shared parameters file» is on (off by default).

By hand:

1. Find the parameters from the table below in your shared parameters file and add the missing ones (data type — by the «Data» column).
2. In Revit: **Manage → Project Parameters → Add → Shared parameter**, pick the parameter, choose «Instance» or «Type» (the «Inst./Type» column) and tick the categories from the first column.
3. Shift+click on a LowLife button opens its settings — enter your parameters' names there. The field is recognised by the meaning of the example name: for `LL_Адрес_узла` (node address) it's the field «[Адресация] Параметр «Адрес узла»», for `LL_Длина_в_лотке` (length in tray) — «Параметр цепи «Длина проводника в лотке»».

If a parameter is needed by several disciplines (for example «Device address»), create **one** parameter and enter its name in each discipline's settings.

Once a parameter name has been entered in one button's settings, the other buttons fill it in by themselves: the same role has the same name in every button (for example «Device address» — for SCS, ACS, fire alarm, CCTV and SS1).

For SCS and ACS, part of steps 1–2 is also done by the «Bind parameters» button on their panels: it binds to categories the parameters already present in the connected shared parameters file.

Notation: **Inst.** — an instance parameter, **Type** — a type parameter. «Needed for» — which sections need the parameter; «Req.» — whether those buttons run without it.

## Which parameters to create

The example names are Russian (as in a Russian project's shared parameters file); their meaning is given in brackets.

| For which categories | Example name | Inst./Type | Data | Req. | Needed for |
|---|---|---|---|---|---|
| Generic Models | `LL_Тип_прокладки_кабеля` (cable installation type) | Inst. | Text | yes | SCS, ACS |
| Generic Models | `LL_Тип_трассы` (route type) | Inst. | Text | yes | SCS, ACS |
| Generic Models | `LL_Адрес_узла` (node address) | Inst. | Text | yes | SCS, ACS |
| Generic Models; Fire Alarm Devices, Security Devices, Communication Devices, Electrical Fixtures, Data Devices | `LL_Предыдущий_адрес` (previous address) | Inst. | Text | yes | SCS, ACS, fire alarm/voice alarm/fire automation |
| Generic Models | `LL_Список_цепей` (circuit list) | Inst. | Multiline text | yes | SCS, ACS |
| Communication Devices, Electrical Fixtures, Data Devices, Electrical Equipment | `LL_Ближайший_узел` (nearest node) | Inst. | Text | yes | SCS, ACS |
| Communication Devices, Electrical Fixtures, Data Devices, Electrical Equipment, Fire Alarm Devices, Security Devices, Nurse Call Devices; Detail Items; Generic Models (SS1 cable entries) | `LL_Адрес_устройства` (device address) | Inst. | Text | yes | SCS, ACS, fire alarm/voice alarm/fire automation, CCTV, SS1 |
| Communication Devices, Electrical Fixtures, Data Devices, Electrical Equipment, Fire Alarm Devices, Security Devices, Nurse Call Devices | `LL_Обозначение` (designation — a short code: «Р», «ИП», «ARK»; always a **type** parameter) | Type | Text | yes | SCS, ACS, fire alarm/voice alarm/fire automation |
| Communication Devices, Electrical Fixtures, Data Devices, Fire Alarm Devices, Security Devices, Nurse Call Devices | `LL_Марка_устройства` (device tag) | Inst. | Text | yes | ACS, fire alarm/voice alarm/fire automation |
| Communication Devices, Electrical Fixtures, Data Devices | `LL_Номер_точки_прохода` (access point number) | Inst. | Text | no | ACS |
| Electrical Equipment (controllers) | `LL_Маркировка_контроллера` (controller tag) | Inst. | Text | yes | ACS |
| Electrical Circuits | `LL_Наименование_цепи` (circuit name — the circuit kind is taken from it: fibre, twisted pair, power) | Inst. | Text | yes | SCS |
| Electrical Circuits | `LL_Номер_цепи` (circuit number) | Inst. | Text | yes | SCS, fire alarm/voice alarm/fire automation |
| Electrical Circuits | `LL_Маршрут_цепи` (circuit route) | Inst. | Text | yes | SCS, ACS, fire alarm/voice alarm/fire automation |
| Electrical Circuits | `LL_Способ_прокладки` (installation method) | Inst. | Text | yes | SCS, ACS, fire alarm/voice alarm/fire automation |
| Electrical Circuits | `LL_Длина_проводника` (wire length) | Inst. | Number (metres) | yes | SCS, ACS, fire alarm/voice alarm/fire automation |
| Electrical Circuits | `LL_Длина_в_лотке` (length in tray) | Inst. | Number (metres) | yes | SCS, ACS, fire alarm/voice alarm/fire automation |
| Electrical Circuits | `LL_Длина_в_трубе` (length in conduit) | Inst. | Number (metres) | yes | SCS, ACS, fire alarm/voice alarm/fire automation |
| Communication Devices, Electrical Fixtures, Data Devices, Electrical Equipment, Fire Alarm Devices, Security Devices; Detail Items; and any other categories you write the room to | `LL_Помещение` (room) | Inst. | Text | yes | Riser diagrams, «Write room number», voice alarm «Typical floor», SS1 |
| Fire Alarm Devices, Security Devices, Communication Devices, Electrical Equipment | `LL_Уровень` (level) | Inst. | Text | no | Fire alarm and CCTV riser diagrams |
| Fire Alarm Devices, Security Devices, Communication Devices, Electrical Equipment | `LL_Корпус`, `LL_Секция` (building, section) | Inst. | Text | no | Fire alarm and CCTV riser diagrams |
| Detail Items | `LL_UID_устройства` (device UID) — service, don't fill in | Inst. | Text | yes | Riser diagrams |
| Views | `LL_Раскладка_схемы` (diagram layout) — service, don't fill in | Inst. | Multiline text | yes | Riser diagrams |
| All categories whose elements need the floor filled in | `LL_Этаж` (floor) | Inst. | Text | yes | «Fill floor» |

## What doesn't need to be created

- **«Load Name», «Wire», «Panel»** of electrical circuits — Revit's built-in parameters. They aren't in the buttons' settings: «Panel» is set by connecting the circuit to a panel, the buttons write «Load Name» themselves, and «Wire» gets the cable catalog row chosen in the settings.
- **Elevation** of nodes and devices — usually the built-in «Offset» (or «Offset from Level») parameter. In the «Possible elevation parameter names» field, list the variants that occur in your families, comma-separated.
- **«Mark» of fire alarm wiring lines** — the built-in «Mark» parameter will do.
- **«Workset»** — the buttons always take the element's own workset; no separate parameter is needed.
- **Camera parameters** («Focal length», «Range», «Sensor format», «Horizontal resolution», «Mounting height», «Camera rotation», «Downward optical axis tilt») — these are camera family parameters; enter their names in the settings of the «Fields of view» button (several variants separated with `;`). Only the focal length and range are required.
- **Room parameters in the linked architectural model** («Lot name», «Section number», room number, the grouping parameter) — maintained by the architect; in the settings, enter what they are called in the architectural model.
- **Parameters for «Place relay, control modules» and «Fill LOI»** — these are existing parameters whose values the buttons carry from one element to another; the list is set in the settings.
- **The cable catalog row marker** — optional: needed only if the project has several circuit key schedules and the cable catalog has to be told apart from the others.

## What else is needed besides parameters

- **Worksets.** The buttons tell elements of their discipline by a word in the workset name. The word is set in the settings (Shift+click) and can be changed to suit your project:

  | What | Settings field | Default |
  |---|---|---|
  | SCS target panels | «[Критерии панели] Ключевое слово рабочего набора целевых панелей» (target panel workset keyword) | empty — no workset filter; enter, for example, «СКС» |
  | ACS route nodes | «[Узлы трассы] Ключевое слово рабочего набора элементов СКУД» (ACS element workset keyword) | empty — no workset filter; enter, for example, «СКУД» |
  | ACS controllers | «[Контроллеры] Ключевое слово рабочего набора контроллеров» (controller workset keyword) | empty — no workset filter; enter, for example, «СКУД» |
  | Fire alarm / voice alarm / fire automation devices | «[Оборудование] Ключевое слово рабочего набора» (workset keyword) | fire automation — «СПА», fire alarm and voice alarm empty — no workset filter; enter, for example, «СПС» |
  | Cable trays | «Workset» in the shared tray settings window (Shift+click on any tray button) | «КНК» |

  SCS and ACS route nodes use the same parameters — the disciplines are separated by workset.
- **Family and type names.** Nodes, panels, risers, route segments and fire alarm isolators are recognised by a word in the family or type name; the words are set in the settings too.
- **Cable tray types** have to be created in the project beforehand: the button looks for a type whose name contains the given text (for example `СБ_ЛЛ_1.5_СЦ`). The table of default names for all 20 buttons and the setting — in [cable-tray-panels.md](cable-tray-panels.md).

## Details by panel

[scs-panel.md](scs-panel.md), [skud-panel.md](skud-panel.md), [skud-schematic-setup.md](skud-schematic-setup.md), [fire-alarm-panels.md](fire-alarm-panels.md), [camera-fov.md](camera-fov.md), [room-info.md](room-info.md), [companion-placement.md](companion-placement.md), [schematics.md](schematics.md), [soue-typical-floor.md](soue-typical-floor.md), [ss1.md](ss1.md), [loi-panel.md](loi-panel.md), [cable-catalog.md](cable-catalog.md), [rooms-panel.md](rooms-panel.md).
