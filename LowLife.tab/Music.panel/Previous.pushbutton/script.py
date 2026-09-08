# -*- coding: utf-8 -*-
__title__ = u"Предыдущий\nтрек"
__doc__ = u"Переключает активный проигрыватель на предыдущий трек (медиаклавиша Windows Previous)."
__author__ = "Pipers"

from lowlife.media_keys import press_key, VK_MEDIA_PREV

press_key(VK_MEDIA_PREV)
