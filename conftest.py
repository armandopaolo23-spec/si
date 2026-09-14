"""Existe para que pytest agregue la raiz del proyecto a sys.path.

Sin esto, `from audio.yin import yin` falla al correr pytest desde tests/.
"""
