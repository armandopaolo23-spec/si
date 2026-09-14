"""Captura desde el microfono con sounddevice.

Es el unico modulo del proyecto que importa sounddevice. El resto del motor
trabaja con arrays de numpy, asi que se puede probar sin tarjeta de sonido.

La regla dura: el callback de audio corre en un hilo de tiempo real de
PortAudio y no puede bloquearse ni hacer trabajo pesado. Aqui solo copia el
bloque a una cola; todo el analisis ocurre en el hilo que consume la cola.
Si el callback se demorara, PortAudio reporta un underrun y se oyen clicks.
"""

import queue

import numpy as np

SR = 44100
BLOQUE = 512      # muestras por callback, ~11.6 ms
MAX_COLA = 128    # ~1.5 s de audio en espera antes de considerar que hay atasco


def cargar_sounddevice():
    """Importa sounddevice, con un mensaje util si falta la libreria de sistema."""
    try:
        import sounddevice
    except (ImportError, OSError) as error:
        raise RuntimeError(
            f"No se pudo cargar sounddevice: {error}\n"
            "Instala:  sudo apt install libportaudio2 && pip install sounddevice"
        ) from error
    return sounddevice


def dispositivos():
    """Texto con la lista de dispositivos de audio del sistema."""
    return str(cargar_sounddevice().query_devices())


class Captura:
    """Contexto que abre el stream de entrada y entrega bloques mono."""

    def __init__(self, sr=SR, bloque=BLOQUE, dispositivo=None, max_cola=MAX_COLA):
        self.sr = sr
        self.bloque = bloque
        self.dispositivo = dispositivo
        self._cola = queue.Queue(maxsize=max_cola)
        self._stream = None
        # Contadores de diagnostico: si crecen, el consumidor no alcanza.
        self.descartes = 0
        self.avisos = []

    def _callback(self, entrada, marcos, tiempo, estado):
        if estado:
            self.avisos.append(str(estado))
        try:
            self._cola.put_nowait(entrada[:, 0].copy())
        except queue.Full:
            # Descartar es mejor que bloquear el hilo de audio, pero rompe la
            # continuidad del conteo de muestras y por eso se cuenta aparte.
            self.descartes += 1

    def __enter__(self):
        sd = cargar_sounddevice()
        try:
            self._stream = sd.InputStream(
                samplerate=self.sr, blocksize=self.bloque, channels=1,
                dtype="float32", device=self.dispositivo, callback=self._callback)
        except Exception as error:
            # El caso comun en Ubuntu: el dispositivo solo acepta 48000 Hz.
            raise RuntimeError(
                f"No se pudo abrir el dispositivo de entrada a {self.sr} Hz: "
                f"{error}\n{self._sugerencia(sd)}"
            ) from error
        self._stream.start()
        return self

    def _sugerencia(self, sd):
        try:
            info = sd.query_devices(self.dispositivo, "input")
        except Exception:
            return ("Revisa los dispositivos disponibles con: "
                    "python3 detector_notas.py --lista")
        return (f"El dispositivo '{info['name']}' declara "
                f"{info['default_samplerate']:.0f} Hz y "
                f"{info['max_input_channels']} canal(es) de entrada.\n"
                f"Prueba:  python3 detector_notas.py "
                f"--sr {info['default_samplerate']:.0f}")

    def __exit__(self, *_):
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        return False

    def bloques(self, espera=1.0):
        """Generador de bloques mono (float32). Bloquea hasta que llegue audio."""
        while True:
            try:
                yield self._cola.get(timeout=espera)
            except queue.Empty:
                yield np.zeros(0, dtype=np.float32)
