"""Sweep-through-host envelopes, independently checked at both host faces."""
import math
import pytest
from lowlife import tray_boxes_core as g


def dot(a,b):return sum(x*y for x,y in zip(a,b))


def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])


def test_inclined_wall_passage_includes_vertical_drift_across_wall():
    s=math.sqrt(.5)
    box,reason=g.wall_box((0,0,0),(0,s,s),(1,0,0),200/s,100,50,10,20,1,60,section_x=(1,0,0))
    assert reason is None
    assert box.width==pytest.approx(120)
    assert box.height==pytest.approx(50/s+200+20)
    assert box.depth==pytest.approx(220)
    assert box.thickness==pytest.approx(200)


def test_inclined_floor_passage_includes_horizontal_drift_across_slab():
    s=math.sqrt(.5)
    box,reason=g.floor_box((0,0,0),(s,0,s),(s,0,-s),200/s,100,50,10,20,1,allow_sloped=True)
    assert reason is None
    assert box.width==pytest.approx(100/s+200+20)
    assert box.depth==pytest.approx(70)
    assert box.height==pytest.approx(220)


@pytest.mark.parametrize('kind',[g.WALL,g.FLOOR])
@pytest.mark.parametrize('roll',[0,.3,1.1])
def test_oblique_rolled_section_encloses_face_intersections(kind,roll):
    d=g.unit((.3,.7,.6))
    u=g.unit(cross(d,(0,0,1)))
    v=cross(d,u)
    u=tuple(u[i]*math.cos(roll)+v[i]*math.sin(roll) for i in range(3))
    v=cross(d,u)
    normal=(0,1,0) if kind==g.WALL else (0,0,1)
    thickness=200
    length=thickness/abs(dot(d,normal))
    width,height=100,60
    if kind==g.WALL:
        box,reason=g.wall_box((0,0,0),d,(1,0,0),length,width,height,0,0,1,80,section_x=u)
        axes=[box.x_dir,(0,0,1)];sizes=[box.width,box.height]
    else:
        box,reason=g.floor_box((0,0,0),d,u,length,width,height,0,0,1,allow_sloped=True)
        axes=[box.x_dir,(-box.x_dir[1],box.x_dir[0],0)];sizes=[box.width,box.depth]
    assert reason is None
    points=[]
    for a in (-width/2,width/2):
        for b in (-height/2,height/2):
            p=tuple(u[i]*a+v[i]*b for i in range(3))
            for face in (-thickness/2,thickness/2):
                t=(face-dot(p,normal))/dot(d,normal)
                points.append(tuple(p[i]+t*d[i] for i in range(3)))
    for axis,size in zip(axes,sizes):
        projected=[dot(p,axis) for p in points]
        assert max(projected)-min(projected)==pytest.approx(size)
        assert max(projected)==pytest.approx(size/2)


def test_round_passage_uses_ellipse_extent_not_square_section():
    d=g.unit((1,1,1));u=g.unit((1,-1,0))
    rect,_=g.wall_box((0,0,0),d,(1,0,0),300,100,100,0,0,1,80,section_x=u)
    circular,_=g.wall_box((0,0,0),d,(1,0,0),300,100,100,0,0,1,80,section_x=u,round_section=True)
    assert circular.width<=rect.width and circular.height<rect.height
    assert circular.height==pytest.approx(100*math.sqrt(2)+300/math.sqrt(3))


def test_parallel_floor_ray_and_invalid_section_frame_do_not_create_boxes():
    box,reason=g.floor_box((0,0,0),(1,0,0),(0,1,0),200,100,100,0,0,1,allow_sloped=True)
    assert box is None and reason
    with pytest.raises(ValueError):
        g.wall_box((0,0,0),(0,1,0),(1,0,0),200,100,100,0,0,1,60,section_x=(0,1,0))


def test_revit_adapter_uses_mep_frame_and_rejects_slanted_wall_before_issuance():
    import ast
    from pathlib import Path
    from types import SimpleNamespace as NS
    path=Path(__file__).parents[1]/'lib/lowlife/tray_boxes.py'
    tree=ast.parse(path.read_text())
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='box_for')
    s=math.sqrt(.5)
    route=NS(Location=NS(Curve=NS(Direction=(0,s,s))),Width=100,Height=50,
             section_x=(1,0,0),round_section=False)
    host=NS(CrossSection='Vertical')
    crossing=NS(kind=g.WALL,wall_dir=(1,0,0),host=host,center=lambda:(0,0,0),length=lambda:200/s)
    ns=dict(core=g,_t=lambda x:x,ft=lambda x:x,unicode=str,tr=lambda ru,en=None:en or ru)
    exec(compile(ast.Module(body=[fn],type_ignores=[]),str(path),'exec'),ns)
    box,reason=ns['box_for'](route,crossing,{'max_slope_deg':1,'max_wall_angle_deg':60})
    assert reason is None and box.height==pytest.approx(50/s+200)
    host.CrossSection='Slanted'
    box,reason=ns['box_for'](route,crossing,{'max_wall_angle_deg':60})
    assert box is None and 'slanted wall' in reason
