# -*- coding: utf-8 -*-
import copy
from lowlife import opening_tasks_browser as b


def rows():
    return [dict(status='new',discipline='ОВ',level='01',kind='wall',issue='1',attention=True,search_text='ОВ стена 500'),
            dict(status='accepted',discipline='ВК',level='02',kind='floor',issue='2',attention=False,search_text='ВК перекрытие 300'),
            dict(status='new',discipline='ОВ',level='02',kind='wall',issue='2',attention=True,search_text='ОВ стена 700')]


def test_filters_combine_without_mutating_cached_rows():
    data=rows();before=copy.deepcopy(data)
    assert b.select_rows(data,{'discipline':'ОВ','level':'02','kind':'wall','issue':'2','status':'new'})==[data[2]]
    assert data==before
    assert b.select_rows(data,{'discipline':'ВК','status':'new'})==[]


def test_attention_and_query_are_intersections_not_alternatives():
    data=rows()
    assert b.select_rows(data,query='700',attention=True)==[data[2]]
    assert b.select_rows(data,query='300',attention=True)==[]
    assert b.select_rows(data,query='стена ОВ',attention=True)==[data[0],data[2]]
    assert b.select_rows(data,query='cntyf')==[data[0],data[2]]


def test_empty_filters_restore_all_and_row_keys_distinguish_models():
    data=rows()
    assert b.select_rows(data)==data
    assert b.row_key({'source_model':'a'},'same')!=b.row_key({'source_model':'b'},'same')
