# -*- coding: utf-8 -*-

import ctypes


VK_VOLUME_DOWN = 0xAE


def press_key(key):
    ctypes.windll.user32.keybd_event(key, 0, 0, 0)
    ctypes.windll.user32.keybd_event(key, 0, 2, 0)


press_key(VK_VOLUME_DOWN)
