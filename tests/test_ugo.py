# -*- coding: utf-8 -*-
import pytest
from lowlife import ugo_core as core


def test_system_union_explicit_membership_and_exact_matches():
    rows = [dict(uid='a', systems=u'СПС, СОУЭ'),
            dict(uid='b', groups=u'Пожарная безопасность'),
            dict(uid='c', systems=u'СПС2'),
            dict(uid='d', groups=u'Другое')]
    group = dict(name=u'Пожарная безопасность', systems=u'СПС; СОУЭ')
    assert [r['uid'] for r in core.selected_rows(rows, group)] == ['a', 'b']
    assert core.selected_rows(rows, dict(name=u'Пустой', systems='')) == []


def test_catalog_preserves_edited_and_empty_labels_without_dropping_missing_types():
    saved = {'a': dict(label=u'Правка', systems=u'СПС'),
             'b': dict(label=''), 'deleted': dict(label=u'Удалён')}
    result = core.merge_catalog([('a', 'renamed'), ('b', 'B'), ('new', 'New : Type')], saved)
    assert [r['label'] for r in result] == [u'Правка', '', 'New : Type', u'Удалён']
    assert result[-1]['available'] is False
    assert result[0]['systems'] == u'СПС'
    assert saved['deleted']['label'] == u'Удалён'
    assert 'name' not in saved['a']


def test_rename_changes_only_exact_membership_and_validation_rejects_typos():
    rows = [dict(groups=u'А, АБ, Б, А')]
    core.rename_group(rows, u'А', u'Новое')
    assert rows[0]['groups'] == u'Новое, АБ, Б'
    groups = [dict(name=n) for n in [u'Новое', u'АБ', u'Б']]
    core.validate(rows, groups)
    with pytest.raises(ValueError):
        core.validate(rows, [dict(name=u'Новое')])
    with pytest.raises(ValueError):
        core.validate([], [dict(name='A'), dict(name='A')])
    with pytest.raises(ValueError):
        core.validate([], [dict(name=' ')])


def test_legend_name_is_a_valid_revit_name():
    assert core.legend_name(dict(name=u'СПС: корпус [1]')) == u'УГО - СПС корпус 1'


def test_shared_token_parser_keeps_default_normalization():
    from lowlife.slab_marks_core import split_words
    assert split_words(u'ДЫМ; Ёлка, ДЫМ') == [u'дым', u'елка']
    assert core.tokens(u'СПС; СОУЭ, СПС') == [u'СПС', u'СОУЭ']
