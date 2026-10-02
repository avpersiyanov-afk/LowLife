/**
 * Заметки по проектам из Revit — серверная часть (Google Apps Script).
 *
 * Установка: откройте Google Таблицу → Расширения → Apps Script,
 * вставьте этот файл целиком, сохраните и запустите функцию setup().
 * Подробности — в docs/notes-panel.md.
 */

const SHEET_NOTES = 'Заметки';
const SHEET_SETTINGS = 'Настройки';
const SHEET_SUMMARY = 'Сводка';
const SHEET_DUE = 'Сроки';

// [ключ в запросе, заголовок столбца, формат ячейки]
const FIELDS = [
  ['id', 'ID', '@'],
  ['created', 'Создано', 'dd.MM.yyyy HH:mm'],
  ['author', 'Автор', '@'],
  ['project_key', 'Код проекта', '@'],
  ['project_name', 'Проект', '@'],
  ['type', 'Тип', '@'],
  ['section', 'Раздел', '@'],
  ['text', 'Текст', '@'],
  ['due', 'Срок', 'dd.MM.yyyy'],
  ['assignee', 'Кому', '@'],
  ['status', 'Статус', '@'],
  ['changed', 'Изменено', 'dd.MM.yyyy HH:mm'],
  ['changed_by', 'Кто изменил', '@'],
  ['file', 'Модель', '@'],
  ['view', 'Вид', '@'],
  ['elements', 'Элементы', '@'],
  ['info', 'Сведения о проекте', '@'],
];
const COL = {};
FIELDS.forEach((f, i) => { COL[f[0]] = i + 1; });
const FORMATS = FIELDS.map(f => f[2]);

const STATUSES = ['Открыто', 'В работе', 'Выполнено', 'Отменено'];

const DEFAULT_LISTS = [
  ['Типы', ['Замечание', 'Задача', 'Вопрос', 'Напоминание', 'Решение', 'Идея']],
  ['Разделы', ['Общее', 'АР', 'КР', 'ОВиК', 'ВК', 'ЭОМ', 'СС', 'ТХ', 'ГП', 'ПОС']],
  ['Сотрудники', []],
];

// [ключ, подпись на листе «Настройки», значение по умолчанию]
const SETTINGS_ROWS = [
  ['key_param', 'Параметр: код проекта', ''],
  ['name_param', 'Параметр: название проекта', ''],
  ['extra_params', 'Параметры в заметку (через ;)', ''],
  ['remind_days', 'Напоминать за, дней до срока', 1],
  ['remind_on_open', 'Напоминать при открытии модели (да/нет)', 'да'],
];


// ---------------------------------------------------------------- меню и установка

function onOpen() {
  SpreadsheetApp.getUi().createMenu('Заметки Revit')
    .addItem('Первичная настройка', 'setup')
    .addItem('Показать токен', 'showToken')
    .addToUi();
}

function setup() {
  const ss = SpreadsheetApp.getActive();
  ensureNotesSheet_(ss);
  ensureSettingsSheet_(ss);
  ensureSummarySheets_(ss);
  const token = getToken_(true);
  const msg = 'Листы созданы.\n\nТокен для Revit:\n' + token +
    '\n\nДальше: в редакторе Apps Script нажмите «Развернуть → Новое развертывание», ' +
    'тип «Веб-приложение», запуск от имени «Я», доступ «Все». Скопируйте адрес, который заканчивается на /exec.';
  Logger.log(msg);
  try { SpreadsheetApp.getUi().alert(msg); } catch (e) { /* запуск из редактора — смотрите журнал */ }
}

function showToken() {
  SpreadsheetApp.getUi().alert('Токен для Revit:\n' + getToken_(true) +
    '\n\nАдрес веб-приложения: Расширения → Apps Script → Развернуть → Управление развертываниями (адрес на /exec).');
}

function getToken_(create) {
  const props = PropertiesService.getScriptProperties();
  let token = props.getProperty('TOKEN');
  if (!token && create) {
    token = Utilities.getUuid().replace(/-/g, '').slice(0, 24);
    props.setProperty('TOKEN', token);
  }
  return token;
}


// ---------------------------------------------------------------- веб-приложение

function doGet() {
  return json_({ ok: true, service: 'Заметки Revit', hint: 'Работает. Revit отправляет запросы методом POST.' });
}

function doPost(e) {
  let req;
  try {
    req = JSON.parse(e.postData.contents);
  } catch (err) {
    return json_({ ok: false, error: 'Некорректный запрос' });
  }
  const token = getToken_(false);
  if (!token || req.token !== token) {
    return json_({ ok: false, error: 'Неверный токен. Сверьте его с меню таблицы «Заметки Revit → Показать токен».' });
  }
  try {
    switch (req.action) {
      case 'ping': return json_({ ok: true, sheet: SpreadsheetApp.getActive().getName() });
      case 'settings': return json_(getSettings_());
      case 'saveSettings': return json_(saveSettings_(req.settings || {}));
      case 'add': return json_(addNote_(req.note || {}));
      case 'list': return json_(listNotes_(req.project_key));
      case 'setStatus': return json_(setStatus_(req.ids || [], req.status, req.by));
      default: return json_({ ok: false, error: 'Неизвестное действие: ' + req.action });
    }
  } catch (err) {
    return json_({ ok: false, error: String((err && err.message) || err) });
  }
}

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}


// ---------------------------------------------------------------- заметки

function addNote_(n) {
  if (!n.id || !String(n.text || '').trim()) return { ok: false, error: 'Пустая заметка' };
  const lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    const sh = notesSheet_();
    if (findRow_(sh, n.id)) return { ok: true, duplicate: true }; // повторная отправка из очереди
    const tz = tz_();
    const values = FIELDS.map(([key]) => {
      if (key === 'created') return parseDate_(n.created, true, tz) || new Date();
      if (key === 'due') return parseDate_(n.due, false, tz);
      if (key === 'status') return STATUSES.indexOf(n.status) >= 0 ? n.status : STATUSES[0];
      if (key === 'changed' || key === 'changed_by') return '';
      return safeText_(n[key]);
    });
    const row = sh.getLastRow() + 1;
    if (row > sh.getMaxRows()) sh.insertRowsAfter(sh.getMaxRows(), 100);
    const range = sh.getRange(row, 1, 1, FIELDS.length);
    range.setNumberFormats([FORMATS]);
    range.setValues([values]);
    return { ok: true, row: row };
  } finally {
    lock.releaseLock();
  }
}

function listNotes_(projectKey) {
  const sh = notesSheet_();
  const last = sh.getLastRow();
  if (last < 2) return { ok: true, notes: [] };
  const tz = tz_();
  const key = String(projectKey || '');
  const rows = sh.getRange(2, 1, last - 1, FIELDS.length).getValues();
  const notes = [];
  rows.forEach(r => {
    if (!r[0]) return;
    if (key && String(r[COL.project_key - 1]) !== key) return;
    const o = {};
    FIELDS.forEach(([k], j) => {
      const v = r[j];
      if (v instanceof Date) o[k] = Utilities.formatDate(v, tz, k === 'due' ? 'yyyy-MM-dd' : 'yyyy-MM-dd HH:mm');
      else o[k] = v === null || v === undefined ? '' : String(v);
    });
    notes.push(o);
  });
  return { ok: true, notes: notes };
}

function setStatus_(ids, status, by) {
  if (STATUSES.indexOf(status) < 0) return { ok: false, error: 'Неизвестный статус: ' + status };
  const lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    const sh = notesSheet_();
    let updated = 0;
    ids.forEach(id => {
      const row = findRow_(sh, id);
      if (!row) return;
      // Статус, Изменено, Кто изменил — соседние столбцы
      sh.getRange(row, COL.status, 1, 3).setValues([[status, new Date(), safeText_(by)]]);
      updated++;
    });
    return { ok: true, updated: updated };
  } finally {
    lock.releaseLock();
  }
}

// Ручная смена статуса прямо в таблице тоже отмечает, кто и когда.
function onEdit(e) {
  try {
    const sh = e.range.getSheet();
    if (sh.getName() !== SHEET_NOTES || e.range.getRow() < 2) return;
    if (e.range.getNumColumns() !== 1 || e.range.getColumn() !== COL.status) return;
    const who = (e.user && e.user.getEmail && e.user.getEmail()) || '';
    for (let r = e.range.getRow(); r <= e.range.getLastRow(); r++) {
      sh.getRange(r, COL.changed, 1, 2).setValues([[new Date(), who]]);
    }
  } catch (err) { /* не мешаем редактированию */ }
}


// ---------------------------------------------------------------- настройки

function getSettings_() {
  const ss = SpreadsheetApp.getActive();
  const data = settingsSheet_().getDataRange().getValues();
  const header = data[0].map(h => String(h).trim());
  const list = name => {
    const c = header.indexOf(name);
    if (c < 0) return [];
    return data.slice(1).map(r => String(r[c]).trim()).filter(Boolean);
  };
  const kv = {};
  data.forEach(r => {
    const label = String(r[4] || '').trim();
    if (label) kv[label] = r[5];
  });
  const get = key => {
    const row = SETTINGS_ROWS.find(s => s[0] === key);
    const v = kv[row[1]];
    return v === undefined || v === '' ? row[2] : v;
  };
  return {
    ok: true,
    sheet_url: ss.getUrl(),
    settings: {
      types: list('Типы'),
      sections: list('Разделы'),
      people: list('Сотрудники'),
      key_param: String(get('key_param')),
      name_param: String(get('name_param')),
      extra_params: String(get('extra_params')).split(';').map(s => s.trim()).filter(Boolean),
      remind_days: Number(get('remind_days')) || 0,
      remind_on_open: !/^(нет|no|false|0)$/i.test(String(get('remind_on_open')).trim()),
    },
  };
}

function saveSettings_(s) {
  const lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    const sh = settingsSheet_();
    ['key_param', 'name_param', 'extra_params'].forEach(key => {
      if (!(key in s)) return;
      const value = Array.isArray(s[key]) ? s[key].join('; ') : String(s[key] || '');
      const row = settingsRow_(sh, key);
      sh.getRange(row, 6).setNumberFormat('@').setValue(value);
    });
    return { ok: true };
  } finally {
    lock.releaseLock();
  }
}

function settingsRow_(sh, key) {
  const label = SETTINGS_ROWS.find(s => s[0] === key)[1];
  const labels = sh.getRange(1, 5, Math.max(sh.getLastRow(), 1), 1).getValues();
  for (let i = 0; i < labels.length; i++) {
    if (String(labels[i][0]).trim() === label) return i + 1;
  }
  let row = 2;
  while (String(sh.getRange(row, 5).getValue()).trim()) row++;
  sh.getRange(row, 5).setValue(label);
  return row;
}


// ---------------------------------------------------------------- листы

function notesSheet_() {
  return SpreadsheetApp.getActive().getSheetByName(SHEET_NOTES) || ensureNotesSheet_(SpreadsheetApp.getActive());
}

function settingsSheet_() {
  return SpreadsheetApp.getActive().getSheetByName(SHEET_SETTINGS) || ensureSettingsSheet_(SpreadsheetApp.getActive());
}

function ensureNotesSheet_(ss) {
  let sh = ss.getSheetByName(SHEET_NOTES);
  if (sh && sh.getLastRow() > 0) return sh;
  if (!sh) sh = ss.insertSheet(SHEET_NOTES, 0);
  const n = FIELDS.length;
  sh.getRange(1, 1, 1, n).setValues([FIELDS.map(f => f[1])])
    .setFontWeight('bold').setBackground('#e8eef7').setVerticalAlignment('middle');
  sh.setFrozenRows(1);
  const widths = { id: 90, created: 120, author: 110, project_key: 100, project_name: 180, type: 110, section: 70,
    text: 380, due: 90, assignee: 110, status: 100, changed: 120, changed_by: 140, file: 200, view: 160,
    elements: 100, info: 220 };
  FIELDS.forEach(([k], i) => sh.setColumnWidth(i + 1, widths[k] || 100));
  sh.getRange(2, COL.text, sh.getMaxRows() - 1, 1).setWrap(true);
  sh.hideColumns(COL.id);
  sh.getRange(2, 1, sh.getMaxRows() - 1, n).setNumberFormats(
    Array.from({ length: sh.getMaxRows() - 1 }, () => FORMATS));

  sh.getRange(2, COL.status, sh.getMaxRows() - 1, 1).setDataValidation(
    SpreadsheetApp.newDataValidation().requireValueInList(STATUSES, true).setAllowInvalid(true).build());

  try {
    const data = sh.getRange(2, 1, sh.getMaxRows() - 1, n);
    const K = colLetter_(COL.status), I = colLetter_(COL.due);
    sh.setConditionalFormatRules([
      SpreadsheetApp.newConditionalFormatRule()
        .whenFormulaSatisfied('=OR($' + K + '2="Выполнено",$' + K + '2="Отменено")')
        .setFontColor('#9e9e9e').setRanges([data]).build(),
      SpreadsheetApp.newConditionalFormatRule()
        .whenFormulaSatisfied('=AND($' + I + '2<>"",$' + I + '2<TODAY(),$' + K + '2<>"Выполнено",$' + K + '2<>"Отменено")')
        .setBackground('#fde7e9').setRanges([data]).build(),
    ]);
  } catch (err) { Logger.log('Условное форматирование не задано: ' + err); }
  return sh;
}

function ensureSettingsSheet_(ss) {
  let sh = ss.getSheetByName(SHEET_SETTINGS);
  const isNew = !sh;
  if (isNew) sh = ss.insertSheet(SHEET_SETTINGS);
  if (isNew || sh.getLastRow() === 0) {
    DEFAULT_LISTS.forEach(([title, items], i) => {
      sh.getRange(1, i + 1).setValue(title);
      if (items.length) sh.getRange(2, i + 1, items.length, 1).setValues(items.map(x => [x]));
    });
    sh.getRange(1, 5, 1, 2).setValues([['Настройка', 'Значение']]);
    sh.getRange(1, 1, 1, 6).setFontWeight('bold').setBackground('#e8eef7');
    sh.getRange(1, 4).setBackground(null);
    sh.getRange(2, 6, SETTINGS_ROWS.length, 1).setNumberFormat('@');
    sh.getRange(2, 5, SETTINGS_ROWS.length, 2).setValues(SETTINGS_ROWS.map(r => [r[1], String(r[2])]));
    sh.getRange(1, 8).setValue(
      'Столбцы «Типы», «Разделы», «Сотрудники» можно свободно править — Revit подхватит их при следующем открытии окна.\n' +
      '«Сотрудники» — имена пользователей Revit (Параметры → Общие → Имя пользователя).\n' +
      'Параметры кода и названия проекта проще выбирать кнопкой «Настройка» в Revit.').setWrap(true).setFontColor('#666666');
    sh.setColumnWidths(1, 3, 140);
    sh.setColumnWidth(4, 30);
    sh.setColumnWidth(5, 300);
    sh.setColumnWidth(6, 320);
    sh.setColumnWidth(8, 420);
    sh.setFrozenRows(1);
  } else {
    SETTINGS_ROWS.forEach(r => settingsRow_(sh, r[0]));
  }
  return sh;
}

function ensureSummarySheets_(ss) {
  const src = "'" + SHEET_NOTES + "'!";
  const L = k => colLetter_(COL[k]);
  const notClosed = L('status') + " <> 'Выполнено' and " + L('status') + " <> 'Отменено'";

  let sh = ss.getSheetByName(SHEET_SUMMARY) || ss.insertSheet(SHEET_SUMMARY);
  sh.clear();
  // setFormula разбирает формулу в локали таблицы: в русской аргументы идут через «;»,
  // столбцы массива {…} — через «\». Поэтому разделители подбираются под таблицу.
  const [S, C] = formulaSeparators_(sh);
  sh.getRange('A1').setValue('Открытые заметки: проекты × разделы (обновляется автоматически)').setFontWeight('bold');
  sh.getRange('A3').setFormula('=IFERROR(QUERY(' + src + 'A1:' + colLetter_(FIELDS.length) + S + ' "select ' +
    L('project_key') + ', ' + L('project_name') + ', count(' + L('id') + ') where ' + L('id') + ' is not null and ' +
    notClosed + ' group by ' + L('project_key') + ', ' + L('project_name') + ' pivot ' + L('section') +
    '"' + S + ' 1)' + S + ' "Открытых заметок нет")');
  sh.setFrozenRows(3);

  const col = k => src + L(k) + '2:' + L(k);
  sh = ss.getSheetByName(SHEET_DUE) || ss.insertSheet(SHEET_DUE);
  sh.clear();
  sh.getRange('A1').setValue('Просроченные и ближайшие (3 дня) открытые заметки').setFontWeight('bold');
  sh.getRange('A3:I3').setValues([['Срок', 'Код проекта', 'Проект', 'Тип', 'Раздел', 'Текст', 'Кому', 'Автор', 'Статус']])
    .setFontWeight('bold').setBackground('#e8eef7');
  sh.getRange('A4').setFormula('=IFERROR(SORT(FILTER({' +
    [col('due'), src + L('project_key') + '2:' + L('text'), col('assignee'), col('author'), col('status')].join(C + ' ') +
    '}' + S + ' ' + col('due') + '<>""' + S + ' ' + col('due') + '<=TODAY()+3' + S + ' ' +
    col('status') + '<>"Выполнено"' + S + ' ' + col('status') + '<>"Отменено")' + S + ' 1' + S + ' TRUE)' + S +
    ' "Ничего срочного")');
  sh.getRange('A4:A').setNumberFormat('dd.MM.yyyy');
  sh.setColumnWidth(6, 380);
  sh.setFrozenRows(3);
}

// [разделитель аргументов, разделитель столбцов массива] для локали таблицы.
// Пробная формула =SUM(1,2): там, где запятая — разделитель аргументов, получится 3,
// а там, где запятая десятичная (ru_RU и др.), — 1,2.
function formulaSeparators_(sh) {
  const probe = sh.getRange('A1');
  probe.setFormula('=SUM(1,2)');
  SpreadsheetApp.flush();
  const comma = probe.getValue() === 3;
  probe.clear();
  return comma ? [',', ','] : [';', '\\'];
}


// ---------------------------------------------------------------- утилиты

function findRow_(sh, id) {
  const last = sh.getLastRow();
  if (last < 2) return 0;
  const cell = sh.getRange(2, COL.id, last - 1, 1)
    .createTextFinder(String(id)).matchEntireCell(true).findNext();
  return cell ? cell.getRow() : 0;
}

function tz_() {
  return SpreadsheetApp.getActive().getSpreadsheetTimeZone();
}

function parseDate_(s, withTime, tz) {
  if (!s) return '';
  try {
    return Utilities.parseDate(String(s), tz, withTime ? 'yyyy-MM-dd HH:mm' : 'yyyy-MM-dd');
  } catch (e) {
    return '';
  }
}

function safeText_(v) {
  const s = v === null || v === undefined ? '' : String(v);
  return /^=/.test(s) ? "'" + s : s; // текст, начинающийся с «=», не должен стать формулой
}

function colLetter_(n) {
  let s = '';
  while (n > 0) {
    const m = (n - 1) % 26;
    s = String.fromCharCode(65 + m) + s;
    n = Math.floor((n - 1) / 26);
  }
  return s;
}
