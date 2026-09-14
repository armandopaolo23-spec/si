# Tutor de guitarra tipo juego ritmico

Aplicacion de escritorio que baja una pista de notas en pantalla, escucha la
guitarra acustica por el microfono de la laptop y solo avanza si la nota suena
correcta.

Este repositorio tambien contiene `NodoAlertaTempranaMultiriesgo/`, un
proyecto distinto y sin relacion con el tutor.

Estado: **fase 1 (motor de audio) terminada**. Faltan las fases 2 a 6
(modelo de pista, evaluador, juego, acordes, generador).

## Instalacion

```bash
sudo apt install libportaudio2
pip install numpy sounddevice pytest
```

`pygame` se agrega en la fase 4.

## Como verificar la fase 1

Las pruebas no usan microfono ni audio grabado: todas las señales se
sintetizan dentro de `tests/sintesis.py`.

```bash
python3 -m pytest tests/ -q          # 54 pruebas, ~4 s
```

Con la guitarra, una linea por cada pulsacion detectada:

```bash
python3 detector_notas.py --lista        # ver dispositivos de entrada
python3 detector_notas.py                # modo ataques
```

```
   t (s)  nota            Hz    cents   conf    nivel
   1.243  E2 (Mi2)     82.35     -1.3   0.98   0.0412
   1.836  A2 (La2)    110.12     +1.9   0.97   0.0388
```

Al salir con Ctrl+C imprime el nivel maximo registrado. **Si con la 6a cuerda
no pasa de ~0.01, el microfono esta cortando los graves**: acerca la laptop a
la boca de la guitarra, sube la ganancia de entrada, o baja la puerta de ruido
con `--umbral 0.0015`.

Para comprobar que el microfono capta bien cada cuerda y para afinar:

```bash
python3 detector_notas.py --afinador
```

Que conviene probar a mano:

- Las seis cuerdas al aire: deben salir E2, A2, D3, G3, B3, E4.
- Una nota sostenida 3 segundos: **una sola linea**, no una por ventana.
- Repicar la misma cuerda sin dejarla apagar: una linea por golpe.
- Guitarra en silencio con ruido de ambiente: ninguna linea. Si aparecen,
  sube `--umbral`.
- Un golpe en la caja: no debe salir nota; se cuenta como descartado.

## Estructura

```
audio/
  notas.py       frecuencia <-> MIDI <-> nombre de nota, cents
  yin.py         deteccion de pitch (YIN sobre numpy)
  onset.py       deteccion de ataques por flujo espectral
  analizador.py  canalizacion pura: bloques de muestras -> ataques con nota
  captura.py     envoltorio de sounddevice (unico modulo que lo importa)
tests/
  sintesis.py    generador de pulsaciones de guitarra para las pruebas
detector_notas.py  CLI de diagnostico (modo ataques y modo afinador)
```

`audio/analizador.py` y todo lo que esta debajo son funciones puras sobre
arrays: no importan `sounddevice` ni `pygame`, asi que las fases siguientes
se pueden testear sin audio ni ventana.

## Numeros medidos

| | |
|---|---|
| Exactitud de pitch, seis cuerdas al aire | < 0.2 cents |
| Exactitud con el fundamental ausente (E2 sin 82 Hz) | octava correcta, < 1 cent |
| Error de timestamp del ataque | < 20 ms (sesgo ~ -5 ms) |
| Retraso entre el golpe y la emision del evento | ~70 ms |
| CPU | 4.7 % de un nucleo (0.54 ms por ventana de 11.6 ms) |

## Parametros ajustables

En `audio/analizador.py` y `audio/onset.py`, todos como argumentos del
constructor:

| Parametro | Defecto | Que hace |
|---|---|---|
| `umbral_ruido` | 0.003 | Puerta de ruido RMS. Bajar si el micro entrega poco nivel. |
| `factor` (onset) | 6.0 | Cuantas veces la mediana reciente del flujo hay que superar. Bajar si pierde pulsaciones suaves. |
| `refractario_s` | 0.08 | Minimo entre dos ataques. Subir si un golpe cuenta doble. |
| `retardo_onset_s` | 0.014 | Correccion del timestamp. Recalibrar contra un metronomo en la fase 4. |
| `saltos_espera` / `saltos_pitch` | 3 / 3 | Cuanto esperar y cuantas lecturas promediar. Bajar da feedback mas rapido y pitch menos estable. |
