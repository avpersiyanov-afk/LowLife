# -*- coding: utf-8 -*-
"""Эмуляция нажатий медиаклавиш Windows."""

import ctypes

VK_MEDIA_NEXT = 0xB0
VK_MEDIA_PREV = 0xB1
VK_MEDIA_PLAY_PAUSE = 0xB3
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF


def press_key(key):
    ctypes.windll.user32.keybd_event(key, 0, 0, 0)
    ctypes.windll.user32.keybd_event(key, 0, 2, 0)
