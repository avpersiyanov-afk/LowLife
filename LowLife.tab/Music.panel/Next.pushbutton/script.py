# -*- coding: utf-8 -*-
__title__ = "Следующий\nтрек"
__doc__ = "Переключает активный проигрыватель на следующий трек (медиаклавиша Windows Next)."
__author__ = "Pipers"

from lowlife.media_keys import press_key, VK_MEDIA_NEXT

press_key(VK_MEDIA_NEXT)
