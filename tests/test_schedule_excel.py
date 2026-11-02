"""Exercise schedule round trips with small Revit API doubles."""
import ast
import base64
import json
from pathlib import Path
from types import SimpleNamespace as NS


class Link:
    pass


def scope():
    path = Path(__file__).parents[1] / 'lib/lowlife/schedule_excel.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    tree.body = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    ns = dict(unicode=str, TYPE_PREFIX='[Type] ', ID_HEADER='Revit ID',
              HEADER_PREFIX='LLH:', CELL_PREFIX='[Cell] ', base64=base64, json=json,
              _ID_ALIASES=('revit id',), RevitLinkInstance=Link,
              ElementId=lambda x: x, StorageType=NS(ElementId='reference'),
              ScheduleFieldType=NS(Instance=1, ElementType=2),
              tr=lambda ru, en=None: en or ru,
              _param_to_text=lambda p: p.value if p else '',
              _set_param_text=lambda p, v: setattr(p, 'value', v) is None)
    exec(compile(tree, str(path), 'exec'), ns)
    return ns


def model():
    def element(eid, tid=None):
        return NS(Id=NS(IntegerValue=eid), Parameters=[], GetTypeId=lambda: tid)
    def parameter(el, value):
        p = NS(Definition=NS(Name='Comment'), Element=el, value=value,
               IsReadOnly=False, StorageType='text')
        el.Parameters.append(p)
        return p
    typ = element(100)
    a, b = element(1, 100), element(2, 100)
    ip = parameter(a, 'instance')
    tp = parameter(typ, 'type')
    elements = {1: a, 2: b, 100: typ}
    return NS(GetElement=elements.get), a, ip, tp


def test_export_adds_id_without_a_schedule_id_field():
    ns = scope()
    doc, el, ip, tp = model()
    fields = [NS(GetName=lambda: 'Comment', FieldType=k, GridColumnWidth=1)
              for k in (1, 2)]
    ns['_visible_fields'] = lambda s: fields
    ns['_ordered_elements'] = lambda d, s: [el]
    ns['_excel_col_width'] = lambda w: w
    ns['_ID_COL_WIDTH'] = 11
    schedule = NS(GetTableData=lambda: NS(GetSectionData=lambda s: NS(NumberOfRows=1)))
    ns['SectionType'] = NS(Header='header')
    rows, count, columns, widths = ns['schedule_to_rows'](doc, schedule)
    assert rows == [['Revit ID', 'Comment', '[Type] Comment'],
                    [1, 'instance', 'type']]
    assert (count, columns) == (1, 2)
    result = ns['rows_to_model'](doc, [rows[0], [1, 'new instance', 'new type']])
    assert result['changed'] == 2
    assert (ip.value, tp.value) == ('new instance', 'new type')


def test_conflicting_type_values_are_skipped_before_any_write():
    ns = scope()
    doc, el, ip, tp = model()
    result = ns['rows_to_model'](doc, [
        ['Revit ID', '[Type] Comment'], [1, 'first'], [2, 'second']])
    assert tp.value == 'type'
    assert result['changed'] == 0
    assert len(result['errors']) == 1


def test_same_type_value_and_old_instance_files():
    ns = scope()
    doc, el, ip, tp = model()
    result = ns['rows_to_model'](doc, [
        ['Revit ID', '[Type] Comment'], [1, 'same'], [2, 'same']])
    assert result['changed'] == 1
    assert result['unchanged'] == 1
    ns['rows_to_model'](doc, [['Revit ID', 'Comment'], [1, 'old format']])
    assert ip.value == 'old format'
    assert tp.value == 'same'


def test_key_schedules_are_listed():
    ns = scope()
    key = NS(IsTemplate=False, Definition=NS(IsKeySchedule=True), Name='Key')
    template = NS(IsTemplate=True)
    revision = NS(IsTemplate=False, Definition=object(), IsTitleblockRevisionSchedule=True)
    ns['FilteredElementCollector'] = lambda d: NS(OfClass=lambda c: [key, template, revision])
    ns['ViewSchedule'] = object
    ns['schedule_name'] = lambda s: s.Name
    assert ns['list_schedules'](object()) == [key]


def manual_table():
    ns = scope()
    cells = [['Title', ''], ['Name', 'Value'], ['Manual text', '42']]
    header = NS(NumberOfRows=3, NumberOfColumns=2, FirstRowNumber=0,
                LastRowNumber=2, FirstColumnNumber=0, LastColumnNumber=1,
                GetColumnWidth=lambda c: 1)
    header.GetMergedCell = lambda r, c: NS(Top=r, Bottom=r, Left=0 if r == 0 else c,
                                         Right=1 if r == 0 else c)
    header.SetCellText = lambda r, c, text: cells[r].__setitem__(c, text)
    schedule = NS(UniqueId='schedule-uid', GetTableData=lambda: NS(GetSectionData=lambda s: header),
                  GetCellText=lambda section, r, c: cells[r][c])
    doc = NS(GetElement=lambda uid: schedule if uid == schedule.UniqueId else None)
    ns.update(SectionType=NS(Header='header'), _visible_fields=lambda s: [],
              _ordered_elements=lambda d, s: [], _excel_col_width=lambda w: w,
              _ID_COL_WIDTH=11)
    return ns, doc, schedule, header, cells


def test_manual_table_round_trip_without_model_elements():
    ns, doc, schedule, header, cells = manual_table()
    rows, count, columns, widths = ns['schedule_to_rows'](doc, schedule)
    assert (count, columns) == (3, 2)
    assert rows[0] == ['Revit ID', '[Cell] 1', '[Cell] 2']
    assert rows[1][1:] == ['Title', '']
    rows[3][1:] = ['Edited text', '99']
    result = ns['rows_to_model'](doc, rows)
    assert result['errors'] == []
    assert result['changed'] == 2
    assert cells[2] == ['Edited text', '99']


def test_changed_manual_table_structure_or_row_is_rejected():
    for change in ('structure', 'text', 'merge'):
        ns, doc, schedule, header, cells = manual_table()
        rows = ns['schedule_to_rows'](doc, schedule)[0]
        rows[3][1:] = ['Edited text', '99']
        if change == 'structure':
            header.NumberOfRows = 4
        elif change == 'text':
            cells[2][0] = 'Edited in Revit'
        else:
            header.GetMergedCell = lambda r, c: NS(Top=r, Bottom=r, Left=0, Right=1)
        result = ns['rows_to_model'](doc, [rows[0], rows[3]])
        assert len(result['errors']) == 1
        assert result['changed'] == 0
        assert cells[2][1] == '42'


def test_reexport_manual_rows_preserves_user_columns_without_duplicates():
    ns, doc, schedule, header, cells = manual_table()
    rows, count, columns, widths = ns['schedule_to_rows'](doc, schedule)
    existing = [r + ['note' if i else 'User column'] for i, r in enumerate(rows)]
    cells[2][0] = 'New Revit text'
    fresh, _, _, fresh_widths = ns['schedule_to_rows'](doc, schedule)
    merged, _, stats = ns['merge_export'](fresh, fresh_widths, existing)
    assert len(merged) == len(rows)
    assert merged[-1][1] == 'New Revit text'
    assert merged[-1][-1] == 'note'
    assert stats['matched'] == 3
