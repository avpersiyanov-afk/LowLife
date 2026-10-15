/**
 * Обратная связь по LowLife — серверная часть (Google Apps Script).
 *
 * Таблица принадлежит автору расширения. Веб-приложение умеет только ДОПИСЫВАТЬ
 * строки на лист «Обратная связь» — прочитать отзывы через него нельзя, их видит
 * только владелец таблицы. Установка — docs/feedback-panel.md.
 *
 * Действие `usage` — статистика запусков кнопок (lib/pnotes/usage.py): пачки запусков
 * дописываются на лист «Запуски», лист «Статистика» считает их формулами.
 */

const SHEET = 'Обратная связь';

// Письмо владельцу таблицы о каждом новом сообщении (при первом запуске Google
// спросит разрешение на отправку почты). false — только запись в таблицу.
const NOTIFY_BY_EMAIL = false;

// Ограничения против мусора: адрес веб-приложения лежит в публичном репозитории
const MAX_FIELD = 300;
const MAX_TEXT = 5000;
const MAX_PER_MINUTE = 20;

// [ключ в запросе, заголовок столбца, ширина столбца]
const FIELDS = [
  ['received', 'Получено', 130],
  ['user', 'Пользователь Revit', 140],
  ['windows_user', 'Пользователь Windows', 140],
  ['contact', 'Контакт', 160],
  ['kind', 'Тип', 100],
  ['panel', 'Панель', 160],
  ['button', 'Кнопка', 180],
  ['text', 'Описание', 420],
  ['version', 'Версия LowLife', 140],
  ['revit', 'Revit', 160],
  ['model', 'Модель', 160],
  ['created', 'Создано у пользователя', 130],
  ['id', 'ID', 120],
  // для себя: статус и ответ заполняются вручную в таблице
  ['status', 'Статус', 110],
  ['note', 'Комментарий', 260],
];
const STATUSES = ['Новое', 'В работе', 'Сделано', 'Не будет', 'Дубль'];


function setup() {
  const ss = SpreadsheetApp.getActive();
  ensureSheet_(ss);
  ensureUsageSheets_(ss);
  const msg = 'Листы «' + SHEET + '», «' + USAGE_SHEET + '» и «' + STATS_SHEET + '» готовы.\n\nДальше: «Развернуть → Новое развертывание», тип «Веб-приложение», ' +
    'запуск от имени «Я», доступ «Все». Адрес на /exec впишите в FEEDBACK_URL в lib/pnotes/feedback.py.';
  Logger.log(msg);
  try { SpreadsheetApp.getUi().alert(msg); } catch (e) { /* запуск из редактора — смотрите журнал */ }
}

function ensureSheet_(ss) {
  let sh = ss.getSheetByName(SHEET);
  if (!sh) sh = ss.insertSheet(SHEET);
  if (sh.getLastRow() === 0) {
    sh.appendRow(FIELDS.map(f => f[1]));
    sh.setFrozenRows(1);
    sh.getRange(1, 1, 1, FIELDS.length).setFontWeight('bold').setBackground('#F2F5F9');
    FIELDS.forEach((f, i) => sh.setColumnWidth(i + 1, f[2]));
    const statusCol = FIELDS.findIndex(f => f[0] === 'status') + 1;
    sh.getRange(2, statusCol, sh.getMaxRows() - 1, 1).setDataValidation(
      SpreadsheetApp.newDataValidation().requireValueInList(STATUSES, true).setAllowInvalid(true).build());
    sh.getRange(2, 1, sh.getMaxRows() - 1, FIELDS.length).setNumberFormat('@').setWrap(true)
      .setVerticalAlignment('top');
    sh.getRange(2, 1, sh.getMaxRows() - 1, 1).setNumberFormat('dd.MM.yyyy HH:mm');
  }
  return sh;
}


function doGet() {
  return json_({ ok: true, service: 'Обратная связь LowLife', hint: 'Работает. Revit отправляет сообщения методом POST.' });
}

function doPost(e) {
  let req;
  try {
    req = JSON.parse(e.postData.contents);
  } catch (err) {
    return json_({ ok: false, error: 'Некорректный запрос' });
  }
  try {
    if (req.action === 'feedback' && req.feedback) return json_(addFeedback_(req.feedback));
    if (req.action === 'usage' && req.usage) return json_(addUsage_(req.usage));
    return json_({ ok: false, error: 'Неизвестное действие' });
  } catch (err) {
    return json_({ ok: false, error: String((err && err.message) || err) });
  }
}

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

function clip_(value, limit) {
  // Значение начинается с = + - @ — Google принял бы его за формулу
  const s = String(value == null ? '' : value).slice(0, limit);
  return /^[=+\-@]/.test(s) ? "'" + s : s;
}

function addFeedback_(item) {
  const text = String(item.text || '').trim();
  if (!text) return { ok: false, error: 'Пустое сообщение' };

  const lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    const cache = CacheService.getScriptCache();
    const count = Number(cache.get('rate') || 0);
    if (count >= MAX_PER_MINUTE) return { ok: false, error: 'Слишком много сообщений, попробуйте через минуту' };
    cache.put('rate', String(count + 1), 60);

    const sh = ensureSheet_(SpreadsheetApp.getActive());
    // Повторная отправка из локальной очереди не должна дублировать строку
    const idCol = FIELDS.findIndex(f => f[0] === 'id') + 1;
    const id = clip_(item.id, 40);
    if (id && sh.getLastRow() > 1 &&
        sh.getRange(2, idCol, sh.getLastRow() - 1, 1).createTextFinder(id).matchEntireCell(true).findNext()) {
      return { ok: true, duplicate: true };
    }
    const row = FIELDS.map(f => {
      if (f[0] === 'received') return new Date();
      if (f[0] === 'status') return 'Новое';
      if (f[0] === 'note') return '';
      return clip_(item[f[0]], f[0] === 'text' ? MAX_TEXT : MAX_FIELD);
    });
    sh.appendRow(row);
  } finally {
    lock.releaseLock();
  }

  if (NOTIFY_BY_EMAIL) {
    try {
      const where = [item.panel, item.button].filter(String).join(' → ') || 'LowLife в целом';
      MailApp.sendEmail(Session.getEffectiveUser().getEmail(),
        'LowLife: ' + (item.kind || 'сообщение') + ' — ' + where,
        text + '\n\nОт: ' + (item.user || item.windows_user || '—') +
        (item.contact ? ' (' + item.contact + ')' : '') +
        '\nВерсия: ' + (item.version || '—') + ', Revit: ' + (item.revit || '—'));
    } catch (e) { /* письмо — не главное, строка уже записана */ }
  }
  return { ok: true };
}


// ---------------------------------------------------------------- статистика запусков

const USAGE_SHEET = 'Запуски';
const STATS_SHEET = 'Статистика';
const MAX_EVENTS = 500;            // запусков в одной пачке
const MAX_USAGE_PER_MINUTE = 60;   // пачек в минуту от всех пользователей

// [ключ в запросе, заголовок столбца, ширина столбца]; время — первым (по нему фильтры статистики)
const USAGE_FIELDS = [
  ['time', 'Время', 140],
  ['user', 'Пользователь Revit', 140],
  ['windows_user', 'Пользователь Windows', 140],
  ['panel', 'Панель', 150],
  ['button', 'Кнопка', 220],
  ['source', 'Откуда', 70],
  ['model', 'Модель', 200],
  ['version', 'Версия LowLife', 130],
  ['revit', 'Revit', 150],
  ['button_id', 'ID кнопки', 220],
];

function ensureUsageSheets_(ss) {
  let sh = ss.getSheetByName(USAGE_SHEET);
  if (!sh) sh = ss.insertSheet(USAGE_SHEET);
  if (sh.getLastRow() === 0) {
    sh.appendRow(USAGE_FIELDS.map(f => f[1]));
    sh.setFrozenRows(1);
    sh.getRange(1, 1, 1, USAGE_FIELDS.length).setFontWeight('bold').setBackground('#F2F5F9');
    USAGE_FIELDS.forEach((f, i) => sh.setColumnWidth(i + 1, f[2]));
    sh.getRange(2, 2, sh.getMaxRows() - 1, USAGE_FIELDS.length - 1).setNumberFormat('@');
    sh.getRange(2, 1, sh.getMaxRows() - 1, 1).setNumberFormat('dd.MM.yyyy HH:mm:ss');
  }
  if (!ss.getSheetByName(STATS_SHEET)) {
    const st = ss.insertSheet(STATS_SHEET);
    const src = "'" + USAGE_SHEET + "'!A:J";
    const blocks = [
      // [столбец, заголовок, запрос]
      [1, 'Кнопки — за всё время', "select D, E, count(A) where A is not null group by D, E order by count(A) desc label D 'Панель', E 'Кнопка', count(A) 'Запусков'"],
      [5, 'Кнопки — последние 30 дней', null],
      [9, 'Пользователи — за всё время', "select B, count(A), max(A) where A is not null group by B order by count(A) desc label B 'Пользователь', count(A) 'Запусков', max(A) 'Последний запуск'"],
      [13, 'По месяцам', "select year(A), month(A)+1, count(A) where A is not null group by year(A), month(A)+1 order by year(A) desc, month(A)+1 desc label year(A) 'Год', month(A)+1 'Месяц', count(A) 'Запусков'"],
    ];
    blocks.forEach(b => {
      st.getRange(1, b[0]).setValue(b[1]).setFontWeight('bold');
      const formula = b[2]
        ? '=QUERY(' + src + ', "' + b[2] + '", 1)'
        : `=QUERY(${src}, "select D, E, count(A) where A >= date '"&TEXT(TODAY()-30,"yyyy-mm-dd")&"' ` +
          `group by D, E order by count(A) desc label D 'Панель', E 'Кнопка', count(A) 'Запусков'", 1)`;
      st.getRange(2, b[0]).setFormula(formula);
    });
    [1, 5].forEach(c => { st.setColumnWidth(c, 150); st.setColumnWidth(c + 1, 220); });
    st.setColumnWidth(9, 160);
    st.setColumnWidth(11, 140);
    st.setFrozenRows(2);
  }
  return sh;
}

function parseTime_(text) {
  const m = /^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})$/.exec(String(text || ''));
  return m ? new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]) : new Date();
}

function addUsage_(usage) {
  const events = Array.isArray(usage.events) ? usage.events.slice(0, MAX_EVENTS) : [];
  if (!events.length) return { ok: true, added: 0 };
  const batch = clip_(usage.batch, 80);

  const lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    const cache = CacheService.getScriptCache();
    // повторная отправка той же пачки (ответ потерялся в сети) не должна дублировать строки
    if (batch && cache.get('usage_' + batch)) return { ok: true, duplicate: true };
    const count = Number(cache.get('usage_rate') || 0);
    if (count >= MAX_USAGE_PER_MINUTE) return { ok: false, error: 'Слишком много запросов, попробуйте через минуту' };
    cache.put('usage_rate', String(count + 1), 60);

    const sh = ensureUsageSheets_(SpreadsheetApp.getActive());
    const rows = events.map(ev => USAGE_FIELDS.map(f =>
      f[0] === 'time' ? parseTime_(ev.time) : clip_(ev[f[0]], MAX_FIELD)));
    sh.getRange(sh.getLastRow() + 1, 1, rows.length, USAGE_FIELDS.length).setValues(rows);
    if (batch) cache.put('usage_' + batch, '1', 21600);
    return { ok: true, added: rows.length };
  } finally {
    lock.releaseLock();
  }
}
