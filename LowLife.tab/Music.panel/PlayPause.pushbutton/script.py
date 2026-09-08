# -*- coding: utf-8 -*-
__title__ = "Пуск /\nпауза"
__doc__ = "Запускает или ставит на паузу воспроизведение в активном проигрывателе (медиаклавиша Windows Play/Pause)."
__author__ = "Pipers"

from lowlife.media_keys import press_key, VK_MEDIA_PLAY_PAUSE

press_key(VK_MEDIA_PLAY_PAUSE)
