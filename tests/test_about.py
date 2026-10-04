# -*- coding: utf-8 -*-
"""Тесты для lowlife.about — версия расширения из файлов .git."""

import io
import os

from lowlife import about

SHA = u"1b96ac0a1b2c3d4e5f60718293a4b5c6d7e8f901"


def _write(root, rel, text):
    path = os.path.join(root, ".git", *rel.split("/"))
    folder = os.path.dirname(path)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(text)


def test_no_git_dir(tmpdir):
    assert about.git_revision(str(tmpdir)) is None
    assert about.version_text(str(tmpdir)) == u"неизвестна"


def test_loose_branch_ref(tmpdir):
    _write(str(tmpdir), "HEAD", u"ref: refs/heads/main\n")
    _write(str(tmpdir), "refs/heads/main", SHA + u"\n")
    assert about.git_revision(str(tmpdir)) == (u"main", SHA)
    assert about.version_text(str(tmpdir)) == u"main @ 1b96ac0"


def test_packed_ref(tmpdir):
    _write(str(tmpdir), "HEAD", u"ref: refs/heads/main\n")
    _write(str(tmpdir), "packed-refs",
           u"# pack-refs with: peeled fully-peeled sorted\n" + SHA + u" refs/heads/main\n")
    assert about.git_revision(str(tmpdir)) == (u"main", SHA)


def test_detached_head(tmpdir):
    _write(str(tmpdir), "HEAD", SHA + u"\n")
    assert about.version_text(str(tmpdir)) == u"1b96ac0"


def test_missing_ref(tmpdir):
    _write(str(tmpdir), "HEAD", u"ref: refs/heads/gone\n")
    assert about.git_revision(str(tmpdir)) is None


def test_extension_root_is_repo_root():
    root = about.extension_root()
    assert os.path.isdir(os.path.join(root, "LowLife.tab"))


def test_wordmark_letters_spell_lowlife():
    assert about.wordmark_plain_text() == u"LowLiFe"


def test_wordmark_transforms_match_artwork():
    ops = dict((i, op) for i, (_, op) in enumerate(about.WORDMARK_LETTERS))
    assert ops[0] == "mirror_x"      # ⅃
    assert ops[3] == "mirror_y"      # Γ
    assert ops[5] == 135             # повёрнутая F
    for i in (1, 2, 4, 6):
        assert ops[i] is None
