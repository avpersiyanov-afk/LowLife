# -*- coding: utf-8 -*-
"""Текст для кнопки «Приветствие» (Tools.panel/Greeting): приветствие по
времени суток и имени пользователя, большими буквами. Без Revit API."""


def part_of_day(hour):
    """Приветствие по часу (0–23): утро 5–11, день 12–16, вечер 17–22, ночь."""
    if 5 <= hour < 12:
        return u"Доброе утро"
    if 12 <= hour < 17:
        return u"Добрый день"
    if 17 <= hour < 23:
        return u"Добрый вечер"
    return u"Доброй ночи"


def greeting_lines(hour, name=None):
    """Две строки для окна: крупное приветствие и имя (или пустая строка).

    Всё в верхнем регистре — окно показывает их большими буквами.
    """
    name = (name or u"").strip()
    if not name:
        return u"{}!".format(part_of_day(hour)).upper(), u""
    return u"{},".format(part_of_day(hour)).upper(), u"{}!".format(name).upper()


# Шуточные предупреждения, если Revit запущен ночью или в выходной.
NIGHT_WARNINGS = [
    u"Ночью нормальные люди спят, а не двигают стены.",
    u"Revit в такой час? Даже лотки уже легли спать.",
    u"Цепи подождут до утра. Кабель от этого длиннее не станет.",
    u"Тёмная тема Revit — не повод работать в темноте. Иди спать.",
    u"Утром ты всё равно всё переделаешь. Ложись.",
]
WEEKEND_WARNINGS = [
    u"Выходные придуманы не для синхронизации с центральной моделью.",
    u"Сегодня выходной. Проект не убежит, а вот шашлык — может.",
    u"ГИП не узнает, что ты здесь. Но мы-то знаем.",
    u"В выходные даже стояки отдыхают.",
    u"Закрой Revit, пока не поздно. Сходи погулять.",
]
NIGHT_WEEKEND_WARNINGS = [
    u"Ночь. Выходной. Revit. Кажется, пора поговорить о балансе работы и жизни.",
    u"Ночью в выходной открывают Revit только те, у кого сдача в понедельник. Сочувствуем.",
]


def is_night(hour):
    """Ночь — те же часы, что и «Доброй ночи»: 23:00–4:59."""
    return part_of_day(hour) == u"Доброй ночи"


def is_weekend(weekday):
    """weekday как у datetime.weekday(): понедельник 0 … воскресенье 6."""
    return weekday in (5, 6)


def off_hours_warning(hour, weekday, choice=None):
    """Шуточное предупреждение для ночи/выходного или None в рабочее время.

    choice(list) выбирает одну фразу — по умолчанию random.choice;
    тесты подставляют свой, чтобы результат был предсказуем.
    """
    night, weekend = is_night(hour), is_weekend(weekday)
    if night and weekend:
        pool = NIGHT_WEEKEND_WARNINGS
    elif night:
        pool = NIGHT_WARNINGS
    elif weekend:
        pool = WEEKEND_WARNINGS
    else:
        return None
    if choice is None:
        import random
        choice = random.choice
    return choice(pool)


# Приятное пожелание утром в будни (утро выходного — WEEKEND_WARNINGS).
MORNING_WISHES = [
    u"Пусть сегодня все цепи сойдутся с первого раза.",
    u"Кофе налит, модель синхронизирована — день будет отличным.",
    u"Пусть коллизий будет ноль, а комплиментов от РГ — много.",
    u"Сегодня ты точно соберёшь самую красивую схему в отделе.",
    u"Пусть Revit не вылетает, а лотки ложатся ровно.",
    u"Хорошего дня! Замечания экспертизы сегодня обойдут тебя стороной.",
]


def morning_wish(hour, weekday, choice=None):
    """Приятное пожелание утром (часы «Доброе утро») в будни, иначе None."""
    if part_of_day(hour) != u"Доброе утро" or is_weekend(weekday):
        return None
    if choice is None:
        import random
        choice = random.choice
    return choice(MORNING_WISHES)


# Вечером в будни: рабочий день кончился, а Revit только открывается.
EVENING_WARNINGS = [
    u"Рабочий день закончился. Нормальные люди закрывают Revit, а ты открываешь.",
    u"Все уже ушли домой. Даже сервер центральной модели собирается.",
    u"Вечер — время ужина, а не синхронизации.",
    u"Домой пора! Чертежи до утра никуда не денутся.",
    u"Открыть Revit в конце дня — смело. Закрыть его прямо сейчас — мудро.",
]


def evening_warning(hour, weekday, choice=None):
    """Шутка «пора домой» вечером (часы «Добрый вечер») в будни, иначе None."""
    if part_of_day(hour) != u"Добрый вечер" or is_weekend(weekday):
        return None
    if choice is None:
        import random
        choice = random.choice
    return choice(EVENING_WARNINGS)


def extra_line(hour, weekday, choice=None):
    """Строка под приветствием: шутка ночью/в выходные, «пора домой» вечером
    в будни, пожелание утром в будни, днём в будни — None."""
    return (off_hours_warning(hour, weekday, choice)
            or evening_warning(hour, weekday, choice)
            or morning_wish(hour, weekday, choice))


# Персональные выкрики: подстрока имени пользователя (без учёта регистра) →
# строка, которую окно добавляет внизу жирным красным.
SHOUTS = [
    (u"nikandrov", u"Диииинааасстия!"),
]


def shout_for(names):
    """Выкрик для пользователя или None. names — имена, под которыми он может
    быть известен (пользователь Revit, учётная запись Windows); совпадение —
    подстрока без учёта регистра, так что «a.nikandrov» и «Nikandrov» подходят."""
    for name in names:
        low = (name or u"").lower()
        for key, text in SHOUTS:
            if key in low:
                return text
    return None
