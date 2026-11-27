# -*- coding: utf-8 -*-
"""Translation resources: real JSON, frozen paths and actionable load failures."""
import io
import json
import os
import runpy
import shutil
import sys

import pytest

from lowlife import i18n


@pytest.fixture
def isolated_catalog(monkeypatch):
    monkeypatch.setattr(i18n, '_CATALOG', {})


def test_shipped_catalog_is_valid_json_and_has_mail_translation():
    # Read directly: catalog()'s Russian fallback must not hide broken JSON.
    with io.open(i18n.CATALOG_PATH, 'r', encoding='utf-8') as stream:
        data = json.load(stream)
    assert data[u'Задачи из почты'] == u'Tasks from mail'


def test_strict_catalog_loads_real_resource(isolated_catalog):
    assert i18n.catalog(strict=True)[u'Задачи из почты'] == u'Tasks from mail'


@pytest.mark.parametrize('raw', [
    b'{"first": "First"\n"second": "Second"}',  # missing comma
    b'{"first": "First",}',  # trailing comma
    b'\xff',  # invalid UTF-8
    b'[]',  # valid JSON, wrong resource shape
])
def test_catalog_reports_failure_and_strict_mode_rejects_cached_fallback(
        isolated_catalog, tmpdir, monkeypatch, caplog, raw):
    path = tmpdir.join('en.json')
    path.write_binary(raw)
    monkeypatch.setattr(i18n, 'CATALOG_PATH', str(path))
    assert i18n.catalog() == {}
    assert i18n.catalog() == {}
    with pytest.raises(RuntimeError) as error:
        i18n.catalog(strict=True)
    assert str(path) in str(error.value)
    assert 'Error' in str(error.value)
    records = [r for r in caplog.records if r.name == 'lowlife.i18n']
    assert len(records) == 1
    assert str(path) in records[0].getMessage()
    assert str(error.value) == records[0].getMessage()


def test_missing_catalog_reports_path_and_os_error(isolated_catalog, tmpdir, monkeypatch):
    path = str(tmpdir.join('missing-en.json'))
    monkeypatch.setattr(i18n, 'CATALOG_PATH', path)
    with pytest.raises(RuntimeError) as error:
        i18n.catalog(strict=True)
    assert path in str(error.value)
    assert 'Error' in str(error.value)


def test_broken_catalog_keeps_russian_fallback_in_revit(
        isolated_catalog, tmpdir, monkeypatch):
    monkeypatch.setattr(i18n, 'CATALOG_PATH', str(tmpdir.join('absent.json')))
    monkeypatch.setattr(i18n, 'current', lambda: i18n.EN)
    assert i18n.tr(u'Задачи из почты') == u'Задачи из почты'
    assert i18n.tr(u'Задачи из почты', u'Tasks from mail') == u'Tasks from mail'


def test_frozen_module_finds_bundled_catalog_independently_of_cwd(tmpdir, monkeypatch):
    root = tmpdir.mkdir('_MEI12345')
    package = root.mkdir('lowlife')
    locale = package.mkdir('locale')
    module_path = str(package.join('i18n.py'))
    source_path = i18n.__file__
    if source_path.endswith(('.pyc', '.pyo')):
        source_path = source_path[:-1]
    shutil.copyfile(source_path, module_path)
    shutil.copyfile(i18n.CATALOG_PATH, str(locale.join('en.json')))
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, '_MEIPASS', str(root), raising=False)
    monkeypatch.chdir(str(tmpdir.mkdir('unrelated-cwd')))
    module = runpy.run_path(module_path)
    assert module['CATALOG_PATH'] == os.path.join(str(locale), 'en.json')
    assert module['catalog'](strict=True)[u'Задачи из почты'] == u'Tasks from mail'


@pytest.mark.parametrize('raw, detail', [
    (b'{"broken":}', 'Expecting'),
    (b'{}', "expected 'Tasks from mail'"),
])
def test_mail_self_test_log_identifies_catalog_failure(
        isolated_catalog, tmpdir, monkeypatch, raw, detail):
    path = tmpdir.join('bad-en.json')
    path.write_binary(raw)
    monkeypatch.setattr(i18n, 'CATALOG_PATH', str(path))
    entry = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                         'apps', 'mail', 'lowlife_mail.py')
    saved_path = list(sys.path)
    try:
        module = runpy.run_path(entry)
    finally:
        sys.path[:] = saved_path
    output = str(tmpdir.join('self-test'))
    assert module['self_test'](output) == 1
    with io.open(os.path.join(output, 'self-test.log'), encoding='utf-8') as stream:
        log = stream.read()
    assert str(path) in log
    assert detail in log
    assert log.endswith('FAILED\n')
