from lowlife import ribbon_focus


def test_lowlife_item_id_matches_tab_segment_only():
    assert ribbon_focus.is_lowlife_item_id(
        u"CustomCtrl_%CustomCtrl_%LowLife%SCS%PlaceRouteNodes")
    assert ribbon_focus.is_lowlife_item_id(
        u"CustomCtrl_%CustomCtrl_%LowLife%MyPanel1%Tool")
    assert not ribbon_focus.is_lowlife_item_id(
        u"CustomCtrl_%CustomCtrl_%Other%LowLifeTools%Tool")
    assert not ribbon_focus.is_lowlife_item_id(None)
