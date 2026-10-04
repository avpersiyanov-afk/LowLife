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
# а не картинкой. Буквы — как в авторской графике docs/brand/ и в логотипе:
# отражённая L (⅃, белая), o, w, она же, повёрнутая на 180° (Γ, оранжевая —
# как в монограмме), i, заглавная F, повёрнутая на 135° по часовой, e.
# (буква, преобразование, акцент): преобразование — None, "mirror_x",
# "mirror_x_rot180" или угол поворота в градусах (по часовой, как
# RotateTransform в WPF); акцент — красить ли букву цветом ACCENT_COLOR.
WORDMARK_LETTERS = [
    (u"L", "mirror_x", False),
    (u"o", None, False),
    (u"w", None, False),
    (u"L", "mirror_x_rot180", True),
    (u"i", None, False),
    (u"F", 135, False),
    (u"e", None, False),
]
# Длина «ноги» L (у ⅃ — влево, у Γ — перекладина вправо) относительно
# ширины L в шрифте: длиннее обычной, чтобы ⅃ не читалась как J.
WORDMARK_L_FOOT = 1.5
MAIN_COLOR = u"#FFFFFF"
ACCENT_COLOR = u"#F08C28"  # оранжевый логотипа (240, 140, 40)
# Геометрический гротеск, как в графике; Segoe UI — если Century Gothic нет.
WORDMARK_FONT = u"Century Gothic, Segoe UI"


def wordmark_plain_text(letters=None):
    """Буквы названия подряд, без отражений/поворотов («LowLiFe»)."""
    return u"".join(spec[0] for spec in (letters or WORDMARK_LETTERS))
