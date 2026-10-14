"""Juego: maquina de estados, disposicion del highway y render con pygame.

Solo juego/render.py y juego/aplicacion.py importan pygame. La maquina de
estados y la geometria son puras, para poder probarlas sin ventana.
"""

import os

# Tiene que quedar puesto antes de que se importe pygame, y este paquete es
# lo primero que se carga en los dos modulos que lo importan.
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
