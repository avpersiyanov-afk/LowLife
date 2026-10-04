# -*- coding: utf-8 -*-
"""Данные для окна «О программе» (кнопка _Themes.panel/About).

Версия расширения — коммит git, из которого pyRevit его поставил: pyRevit
ставит расширение по ссылке GitHub клонированием, так что в корне лежит
`.git`. Читаем HEAD напрямую из файлов (без git и без Revit API): ветка →
`refs/heads/<ветка>` или `packed-refs`; detached HEAD — хеш прямо в HEAD.
"""

import io
import os

REPO_URL = u"https://github.com/avpersiyanov-afk/LowLife"
TAGLINE = u"Слаботочные системы в Revit"
DISCIPLINES = u"СКС · СКУД · СОТ · СОУЭ · СПС · СПА · КНК"


def extension_root():
    """Корень расширения: lib/lowlife/about.py → два уровня вверх от lib."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _read(path):
    with io.open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def git_revision(root=None):
    """(ветка, полный хеш) текущего коммита или None, если .git нет/не читается.

    Ветка — None при detached HEAD."""
    git_dir = os.path.join(root or extension_root(), ".git")
    try:
        head = _read(os.path.join(git_dir, "HEAD"))
    except (IOError, OSError):
        return None
    if not head.startswith(u"ref:"):
        return (None, head) if head else None
    ref = head[len(u"ref:"):].strip()
    branch = ref[len(u"refs/heads/"):] if ref.startswith(u"refs/heads/") else ref
    try:
        return branch, _read(os.path.join(git_dir, *ref.split(u"/")))
    except (IOError, OSError):
        pass
    try:
        packed = _read(os.path.join(git_dir, "packed-refs"))
    except (IOError, OSError):
        return None
    for line in packed.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1] == ref:
            return branch, parts[0]
    return None


def version_text(root=None):
    """Строка версии для окна: «main @ 1a2b3c4» или «неизвестна»."""
    rev = git_revision(root)
    if not rev:
        return u"неизвестна"
    branch, sha = rev
    short = sha[:7]
    return u"{} @ {}".format(branch, short) if branch else short


# Название в окне «О программе» набирается шрифтом (lowlife.wordmark_wpf),
# а не картинкой. Буквы — как в авторской графике docs/brand/: отражённая L,
# o, w, перевёрнутая L (Γ), i, заглавная F, повёрнутая на 135° по часовой, e.
# Вторая часть пары — преобразование: None, "mirror_x", "mirror_y" или угол
# поворота в градусах (по часовой, как RotateTransform в WPF).
WORDMARK_LETTERS = [
    (u"L", "mirror_x"),
    (u"o", None),
    (u"w", None),
    (u"L", "mirror_y"),
    (u"i", None),
    (u"F", 135),
    (u"e", None),
]
# Геометрический гротеск, как в графике; Segoe UI — если Century Gothic нет.
WORDMARK_FONT = u"Century Gothic, Segoe UI"


def wordmark_plain_text(letters=None):
    """Буквы названия подряд, без отражений/поворотов («LowLiFe»)."""
    return u"".join(ch for ch, _ in (letters or WORDMARK_LETTERS))
