/**
 * Обратная связь по LowLife — серверная часть (Google Apps Script).
 *
 * Таблица принадлежит автору расширения. Веб-приложение умеет только ДОПИСЫВАТЬ
 * строки на лист «Обратная связь» — прочитать отзывы через него нельзя, их видит
 * только владелец таблицы. Установка — docs/feedback-panel.md.
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
  ensureSheet_(SpreadsheetApp.getActive());
  const msg = 'Лист «' + SHEET + '» готов.\n\nДальше: «Развернуть → Новое развертывание», тип «Веб-приложение», ' +
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
  if (req.action !== 'feedback' || !req.feedback) {
    return json_({ ok: false, error: 'Неизвестное действие' });
  }
  try {
    return json_(addFeedback_(req.feedback));
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
