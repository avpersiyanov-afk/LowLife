# -*- coding: utf-8 -*-
class LengthBreakdown(object):
    def __init__(self, total, tray, pipe, pipe_open, unknown):
        self.total = total; self.tray = tray; self.pipe = pipe; self.pipe_open = pipe_open; self.unknown = unknown

def classify_lengths(parts, unknown_as="pipe"):
    total = tray = pipe = pipe_open = unknown = 0.0
    for length, install in parts:
        length = float(length); total += length
        value = (install or "").lower()
        if "tray" in value or "лот" in value:
            tray += length
        elif "pipe_open" in value or "open" in value or "откры" in value:
            pipe_open += length
        elif "pipe" in value or "труб" in value:
            pipe += length
        else:
            unknown += length
            if unknown_as == "pipe":
                pipe += length
    return LengthBreakdown(total, tray, pipe, pipe_open, unknown)
