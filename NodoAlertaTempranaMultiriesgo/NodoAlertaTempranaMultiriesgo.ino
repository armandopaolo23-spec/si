/**
 * ============================================================
 *  Nodo IoT de Alerta Temprana Multiriesgo
 *  Huaicos / Inundaciones
 *
 *  Placa   : ESP32 DevKitC V4
 *
 *  Bus I2C (SDA=GPIO21, SCL=GPIO22):
 *    - AHT20      — Temperatura y Humedad del Aire
 *    - BMP280     — Presión Barométrica (prueba 0x76 y 0x77)
 *    - LCD 1602   — Pantalla local (módulo I2C @ 0x27, 5V)
 *
 *  Bus OneWire (GPIO5):
 *    - DS18B20    — Temperatura del Suelo (pull-up 5.1 kΩ)
 *
 *  Nube    : ThingSpeak vía HTTP GET cada 20 s
 *            Field1 = Temp. Aire (AHT20)   [°C]
 *            Field2 = Humedad (AHT20)       [%]
 *            Field3 = Temp. Suelo (DS18B20) [°C]
 *            Field4 = Presión (BMP280)      [hPa]
 *
 *  Librerías requeridas (Gestor de Librerías del Arduino IDE):
 *    - Adafruit AHTX0
 *    - Adafruit BMP280
 *    - Adafruit Unified Sensor
 *    - LiquidCrystal I2C  (Frank de Brabander)
 *    - DallasTemperature
 *    - OneWire
 * ============================================================
 */

#include <Wire.h>
#include <Adafruit_AHTX0.h>
#include <Adafruit_BMP280.h>
#include <LiquidCrystal_I2C.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <WiFi.h>
#include <HTTPClient.h>

// ============================================================
//  CREDENCIALES — Editar antes de cargar el firmware
// ============================================================
const char* WIFI_SSID     = "TU_NOMBRE_DE_RED";
const char* WIFI_PASSWORD = "TU_CONTRASENA";
const char* TS_API_KEY    = "TU_THINGSPEAK_WRITE_API_KEY";
const char* TS_URL        = "http://api.thingspeak.com/update";

// ============================================================
//  PINES Y CONSTANTES DE HARDWARE
// ============================================================
#define ONE_WIRE_PIN       5        // GPIO del bus OneWire (DS18B20)
#define I2C_SDA            21       // Pin SDA del ESP32
#define I2C_SCL            22       // Pin SCL del ESP32
#define LCD_I2C_ADDR       0x27    // Dirección del módulo I2C de la LCD
#define LCD_COLS           16
#define LCD_ROWS           2

#define UPLOAD_INTERVAL_MS 20000UL  // Periodo de envío a ThingSpeak (ms)
#define WIFI_TIMEOUT_MS    15000UL  // Tiempo máximo de conexión WiFi (ms)

// ============================================================
//  OBJETOS DE HARDWARE
// ============================================================
LiquidCrystal_I2C lcd(LCD_I2C_ADDR, LCD_COLS, LCD_ROWS);
Adafruit_AHTX0    aht;
Adafruit_BMP280   bmp;
OneWire           oneWire(ONE_WIRE_PIN);
DallasTemperature ds18b20(&oneWire);

// ============================================================
//  FLAGS DE ESTADO (true = sensor inicializado correctamente)
// ============================================================
bool ahtOK  = false;
bool bmpOK  = false;
bool ds18OK = false;

// ============================================================
//  ÚLTIMAS LECTURAS (NAN indica que no hay dato disponible)
// ============================================================
float tempAire  = NAN;
float humedad   = NAN;
float tempSuelo = NAN;
float presion   = NAN;

unsigned long lastUploadMs = 0; // Marca de tiempo del último envío

// ============================================================
//  PROTOTIPOS
// ============================================================
void initSensors();
void initWiFi();
void readSensors();
void updateLCD();
void sendToThingSpeak();
void lcdMsg(const char* l1, const char* l2);

// ============================================================
//  SETUP
//  Orden obligatorio: LCD → Sensores → WiFi
//  Razón: la LCD consume corriente al encender su backlight.
//  Inicializarla primero estabiliza la línea de 3.3 V antes
//  de comunicarse con los sensores por I2C.
// ============================================================
void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println(F("\n========================================"));
  Serial.println(F("  Nodo IoT Alerta Temprana Multiriesgo"));
  Serial.println(F("========================================"));

  // 1. Bus I2C
  Wire.begin(I2C_SDA, I2C_SCL);

  // 2. Pantalla LCD (primero para estabilizar la línea de 3.3 V)
  lcd.init();
  lcd.backlight();
  lcdMsg("Alerta Temprana", "  Iniciando...  ");
  Serial.println(F("[LCD]     Inicializada"));
  delay(1000);

  // 3. Sensores ambientales y de suelo
  initSensors();

  // 4. WiFi (solo después de que los sensores estén activos)
  initWiFi();

  lcdMsg("Sistema Listo", " Monitoreando...");
  delay(1500);
}

// ============================================================
//  LOOP PRINCIPAL
// ============================================================
void loop() {
  readSensors();
  updateLCD();

  if (millis() - lastUploadMs >= UPLOAD_INTERVAL_MS) {
    lastUploadMs = millis();
    sendToThingSpeak();
  }

  delay(2000); // Refresco de LCD cada 2 s
}

// ============================================================
//  Muestra un mensaje de 2 líneas en la LCD
// ============================================================
void lcdMsg(const char* l1, const char* l2) {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print(l1);
  lcd.setCursor(0, 1);
  lcd.print(l2);
}

// ============================================================
//  Inicializa los tres sensores con manejo de errores NO bloqueante.
//  Si un sensor falla, el nodo continúa con los sensores restantes.
// ============================================================
void initSensors() {
  // --- AHT20 (Temperatura / Humedad del Aire) ---
  if (aht.begin()) {
    ahtOK = true;
    Serial.println(F("[AHT20]   OK"));
  } else {
    Serial.println(F("[AHT20]   ERROR: sensor no detectado en el bus I2C"));
    lcdMsg("ERROR AHT20", "Continuando...  ");
    delay(1500);
  }

  // --- BMP280 (Presión): intentar 0x76 y luego 0x77 ---
  if (bmp.begin(0x76) || bmp.begin(0x77)) {
    bmpOK = true;
    // Configuración recomendada para monitoreo ambiental continuo
    bmp.setSampling(
      Adafruit_BMP280::MODE_NORMAL,
      Adafruit_BMP280::SAMPLING_X2,    // sobremuestreo temperatura
      Adafruit_BMP280::SAMPLING_X16,   // sobremuestreo presión
      Adafruit_BMP280::FILTER_X16,     // filtro IIR para estabilidad
      Adafruit_BMP280::STANDBY_MS_500  // tiempo entre mediciones
    );
    Serial.println(F("[BMP280]  OK"));
  } else {
    Serial.println(F("[BMP280]  ERROR: no detectado en 0x76 ni en 0x77"));
    lcdMsg("ERROR BMP280", "Continuando...  ");
    delay(1500);
  }

  // --- DS18B20 (Temperatura del Suelo) ---
  ds18b20.begin();
  if (ds18b20.getDeviceCount() > 0) {
    ds18OK = true;
    ds18b20.setResolution(12); // 12 bits → resolución de 0.0625 °C
    Serial.println(F("[DS18B20] OK"));
  } else {
    Serial.println(F("[DS18B20] ERROR: ningún sensor detectado en OneWire"));
    lcdMsg("ERROR DS18B20", "Continuando...  ");
    delay(1500);
  }
}

// ============================================================
//  Conecta a WiFi con timeout.
//  Si no logra conectar, el nodo opera en modo offline
//  (sigue leyendo sensores y mostrando en LCD).
// ============================================================
void initWiFi() {
  Serial.printf("[WiFi]    Conectando a: %s\n", WIFI_SSID);
  lcdMsg("Conectando WiFi ", WIFI_SSID);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < WIFI_TIMEOUT_MS) {
    delay(500);
    Serial.print('.');
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print(F("[WiFi]    OK — IP: "));
    Serial.println(WiFi.localIP());
    // Mostrar los últimos 16 caracteres de la IP en la segunda fila
    char ipBuf[17];
    strncpy(ipBuf, WiFi.localIP().toString().c_str(), 16);
    ipBuf[16] = '\0';
    lcdMsg("WiFi Conectado  ", ipBuf);
  } else {
    Serial.println(F("[WiFi]    FALLO — Modo offline activo"));
    lcdMsg("WiFi FALLO", "Modo Offline    ");
  }
  delay(1500);
}

// ============================================================
//  Lee todos los sensores disponibles y actualiza las variables
//  globales. Un valor NAN significa lectura no disponible.
// ============================================================
void readSensors() {
  if (ahtOK) {
    sensors_event_t evHum, evTemp;
    aht.getEvent(&evHum, &evTemp);
    tempAire = evTemp.temperature;
    humedad  = evHum.relative_humidity;
  }

  if (bmpOK) {
    presion = bmp.readPressure() / 100.0F; // Convierte Pa → hPa
  }

  if (ds18OK) {
    ds18b20.requestTemperatures();
    float t = ds18b20.getTempCByIndex(0);
    // DallasTemperature devuelve DEVICE_DISCONNECTED_C (-127) en error
    tempSuelo = (t == DEVICE_DISCONNECTED_C) ? NAN : t;
  }

  // Registro en Monitor Serie para depuración
  Serial.printf(
    "[Datos]   TA:%5.1f C  H:%5.1f%%  TS:%5.1f C  P:%6.1f hPa\n",
    isnan(tempAire)  ? 0.0f : tempAire,
    isnan(humedad)   ? 0.0f : humedad,
    isnan(tempSuelo) ? 0.0f : tempSuelo,
    isnan(presion)   ? 0.0f : presion
  );
}

// ============================================================
//  Actualiza la LCD con formato fijo de exactamente 16 columnas:
//
//   Fila 0: "TA:XX.XC H:XX.X%"   (3+4+4+4+1 = 16 chars)
//   Fila 1: "TS:XX.XC P:XXX.X"   (3+4+4+5   = 16 chars)
//
//  "---" sustituye al valor cuando el sensor no está disponible.
// ============================================================
void updateLCD() {
  char row0[17], row1[17]; // 16 chars útiles + terminador nul

  // Formatear cada campo en buffers de ancho fijo
  char taBuf[5], huBuf[5], tsBuf[5], prBuf[6];

  // Temperatura aire: 4 chars, ej. "25.5" | " ---"
  if (!isnan(tempAire))  snprintf(taBuf, sizeof(taBuf), "%4.1f", tempAire);
  else                   strncpy (taBuf, " ---", sizeof(taBuf));

  // Humedad relativa: 4 chars, ej. "60.2" | " ---"
  if (!isnan(humedad))   snprintf(huBuf, sizeof(huBuf), "%4.1f", humedad);
  else                   strncpy (huBuf, " ---", sizeof(huBuf));

  // Temperatura suelo: 4 chars, ej. "24.1" | " ---"
  if (!isnan(tempSuelo)) snprintf(tsBuf, sizeof(tsBuf), "%4.1f", tempSuelo);
  else                   strncpy (tsBuf, " ---", sizeof(tsBuf));

  // Presión: 5 chars, ej. "741.8" | " ----"
  if (!isnan(presion))   snprintf(prBuf, sizeof(prBuf), "%5.1f", presion);
  else                   strncpy (prBuf, " ----", sizeof(prBuf));

  // Ensamblar y escribir filas
  // "TA:" (3) + taBuf (4) + "C H:" (4) + huBuf (4) + "%" (1) = 16
  snprintf(row0, sizeof(row0), "TA:%sC H:%s%%", taBuf, huBuf);

  // "TS:" (3) + tsBuf (4) + "C P:" (4) + prBuf (5)          = 16
  snprintf(row1, sizeof(row1), "TS:%sC P:%s",   tsBuf, prBuf);

  lcd.setCursor(0, 0);
  lcd.print(row0);
  lcd.setCursor(0, 1);
  lcd.print(row1);
}

// ============================================================
//  Envía las lecturas a ThingSpeak vía HTTP GET.
//  Solo se incluyen en la URL los campos con datos válidos,
//  para no contaminar el canal con ceros de sensores caídos.
// ============================================================
void sendToThingSpeak() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println(F("[ThingSpeak] Sin WiFi — envío omitido"));
    return;
  }

  String url = String(TS_URL) + "?api_key=" + TS_API_KEY;
  if (!isnan(tempAire))  url += "&field1=" + String(tempAire,  2);
  if (!isnan(humedad))   url += "&field2=" + String(humedad,   2);
  if (!isnan(tempSuelo)) url += "&field3=" + String(tempSuelo, 2);
  if (!isnan(presion))   url += "&field4=" + String(presion,   2);

  HTTPClient http;
  http.begin(url);
  int httpCode = http.GET();

  if (httpCode > 0) {
    // ThingSpeak responde con el número de entrada creada (ej. "1523")
    Serial.printf("[ThingSpeak] HTTP %d — Entrada #%s\n",
                  httpCode, http.getString().c_str());
  } else {
    Serial.printf("[ThingSpeak] Error de conexión: %s\n",
                  http.errorToString(httpCode).c_str());
  }

  http.end();
}
