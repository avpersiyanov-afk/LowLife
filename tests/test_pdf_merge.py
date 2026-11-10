# -*- coding: utf-8 -*-
import os
import pytest

from lowlife.pdf_merge import plan_merges, merge_group
from lowlife._vendor.PyPDF2 import PdfFileReader, PdfFileWriter


def make_pdf(path, widths):
    writer = PdfFileWriter()
    for width in widths:
        writer.addBlankPage(width, 200)
    with open(str(path), 'wb') as stream:
        writer.write(stream)


def test_groups_numeric_order_and_no_recursion(tmpdir):
    for name in ['set_name_10.pdf', 'set_name_2.PDF', 'set_name_1.pdf',
                 'other_1.pdf', 'plain.pdf', 'set_name_x.pdf']:
        tmpdir.join(name).write('placeholder')
    tmpdir.mkdir('nested').join('set_name_3.pdf').write('placeholder')
    plans = plan_merges(str(tmpdir))
    assert len(plans) == 1
    assert os.path.basename(plans[0][0]) == 'set_name.pdf'
    assert [os.path.basename(p) for p in plans[0][1]] == [
        'set_name_1.pdf', 'set_name_2.PDF', 'set_name_10.pdf']


def test_merge_preserves_page_order_and_removes_only_sources(tmpdir):
    a, b = tmpdir.join('set_1.pdf'), tmpdir.join('set_2.pdf')
    make_pdf(a, [101, 102])
    make_pdf(b, [201])
    untouched = tmpdir.join('other.pdf')
    make_pdf(untouched, [999])
    output, sources = plan_merges(str(tmpdir))[0]
    assert merge_group(output, sources) == []
    assert not a.exists() and not b.exists() and untouched.exists()
    with open(output, 'rb') as stream:
        assert [int(p.mediaBox.getWidth()) for p in PdfFileReader(stream).pages] == [101, 102, 201]


@pytest.mark.parametrize('failure', ['corrupt', 'existing', 'empty', 'encrypted'])
def test_failure_preserves_inputs(tmpdir, failure):
    a, b, out = [tmpdir.join(n) for n in ('set_1.pdf', 'set_2.pdf', 'set.pdf')]
    make_pdf(a, [100])
    make_pdf(b, [200])
    if failure == 'corrupt':
        b.write('broken PDF')
    elif failure == 'existing':
        out.write('existing output')
    elif failure == 'empty':
        make_pdf(b, [])
    else:
        writer = PdfFileWriter()
        writer.addBlankPage(200, 200)
        writer.encrypt('secret')
        with open(str(b), 'wb') as stream:
            writer.write(stream)
    originals = (a.read_binary(), b.read_binary())
    with pytest.raises(Exception):
        merge_group(str(out), [str(a), str(b)])
    assert (a.read_binary(), b.read_binary()) == originals
    assert not list(tmpdir.visit('.lowlife-merge-*'))
    assert out.read() == 'existing output' if failure == 'existing' else not out.exists()


def test_failed_cleanup_keeps_verified_output(tmpdir, monkeypatch):
    a, b, out = [tmpdir.join(n) for n in ('set_1.pdf', 'set_2.pdf', 'set.pdf')]
    make_pdf(a, [100])
    make_pdf(b, [200])
    remove = os.remove

    def locked(path):
        if path == str(a):
            raise OSError('locked')
        remove(path)

    monkeypatch.setattr(os, 'remove', locked)
    errors = merge_group(str(out), [str(a), str(b)])
    assert errors[0][0] == str(a)
    assert a.exists() and not b.exists() and out.exists()
