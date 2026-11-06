# -*- coding: utf-8 -*-
"""2D wall/floor opening projection for review before any model changes."""
from lowlife import opening_tasks_core as core


def project(records):
    geometries=[r['geometry'] for r in records]
    merged=core.merge_geometry(geometries)
    x=merged['x_dir']
    y=[0,0,1] if merged['kind']=='wall' else [-x[1],x[0],0]
    size_index=2 if merged['kind']=='wall' else 1
    def rectangle(g):
        delta=[a-b for a,b in zip(g['center_mm'],merged['center_mm'])]
        cx=sum(a*b for a,b in zip(delta,x))
        cy=sum(a*b for a,b in zip(delta,y))
        w,h=g['size_mm'][0],g['size_mm'][size_index]
        return (cx-w/2,cy-h/2,w,h)
    return dict(geometry=merged,outline=rectangle(merged),
                rectangles=[rectangle(g) for g in geometries])
