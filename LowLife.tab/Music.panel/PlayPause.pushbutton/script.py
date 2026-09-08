# -*- coding: utf-8 -*-
__title__ = u"Пуск /\nпауза"
__doc__ = u"Запускает или ставит на паузу воспроизведение в активном проигрывателе (медиаклавиша Windows Play/Pause)."
__author__ = "Pipers"

from lowlife.media_keys import press_key, VK_MEDIA_PLAY_PAUSE

press_key(VK_MEDIA_PLAY_PAUSE)
