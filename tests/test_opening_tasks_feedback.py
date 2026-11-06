# -*- coding: utf-8 -*-
import pytest
from lowlife import opening_tasks_feedback as f
from lowlife import opening_tasks_browser as b

def task(status='issued'):
    return dict(source_model='vis',task_id='a',revision=2,status=status)

def receipt(status='accepted',revision=2):
    return dict(status=status,revisions={'vis/a':revision},comment='review')

@pytest.mark.parametrize('reply,available,exists,matches,expected',[
    (None,False,False,False,'unavailable'),
    (None,True,False,False,'pending'),
    (receipt(),True,True,True,'accepted'),
    (receipt('rejected'),True,False,False,'rejected'),
    (receipt(revision=1),True,True,True,'outdated'),
    (receipt('rejected',1),True,False,False,'outdated'),
    (receipt(),True,False,False,'missing'),
    (receipt(),True,True,False,'modified'),
    (receipt(),False,False,False,'unavailable'),
])
def test_response(reply,available,exists,matches,expected):
    assert f.evaluate(task(),reply,available,exists,matches)==expected
    assert all(f.describe(expected))

def test_withdrawal_requires_current_recipient_decision():
    assert f.evaluate(task('withdrawn'),None)=='withdraw_pending'
    assert f.evaluate(task('withdrawn'),receipt())=='withdraw_pending'
    assert f.evaluate(task('withdrawn'),receipt('withdrawn',1))=='withdraw_pending'
    assert f.evaluate(task('withdrawn'),receipt('withdrawn'))=='withdrawn'

def test_response_filter_preserves_independent_working_status():
    rows=[dict(result='accepted',status='changed',attention=True,search_text=''),
          dict(result='rejected',status='issued',attention=True,search_text='')]
    assert b.select_rows(rows,{'result':'accepted'},attention=True)==rows[:1]
