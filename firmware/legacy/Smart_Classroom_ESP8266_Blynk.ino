/*
 * IoT-Based Smart Classroom Zone Energy Management System
 * Board: NodeMCU ESP8266 (ESP-12E)
 *
 * Pins:
 * DHT11 data : D3 (GPIO0)
 * PIR        : D5 (GPIO14)
 * LDR analog : A0
 * Relay Light: D0 (GPIO16), active LOW
 * Relay Fan  : D6 (GPIO12), active LOW
 * Relay PC   : D7 (GPIO13), active LOW
 * Relay AC   : D8 (GPIO15), active LOW
 * LCD SDA    : D2 (GPIO4)
 * LCD SCL    : D1 (GPIO5)
 *
 * IMPORTANT:
 * Dashboard mapping (matches supplied screenshot):
 * V0 Temperature, V1 Humidity, V2 Room Light, V3 Motion
 * V4 AC Status, V5 Fan Status, V6 PC Status, V7 Light Status
 * V8 Manual Mode, V9 AC Control, V10 Fan Control, V11 PC Control
 * V12 Light Control, V13 AC Temperature Threshold, V14 Light Threshold
 * If LDR ADC gets HIGHER in darkness, set LDR_DARK_ADC_HIGH to true.
 * This sketch assumes relay modules are active LOW.
 */

#define BLYNK_TEMPLATE_ID   "TMPL6xtXE9nmS"
#define BLYNK_TEMPLATE_NAME "Smart Classroom Automation"
#define BLYNK_AUTH_TOKEN    "3qRW5TluSUqEbkNDS79kQCJoqA9LCSDv"

#define BLYNK_PRINT Serial
#include <ESP8266WiFi.h>
#include <BlynkSimpleEsp8266.h>
#include <DHT.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>

// ---------- Wi-Fi credentials ----------
char ssid[] = "thefoolwifi";
char pass[] = "6334bX!7";

// ---------- Pin definitions ----------
const uint8_t PIN_DHT      = D3;
const uint8_t PIN_PIR      = D5;
const uint8_t PIN_LDR      = A0;
const uint8_t PIN_RELAY_LT = D0;
const uint8_t PIN_RELAY_FN = D6;
const uint8_t PIN_RELAY_PC = D7;
const uint8_t PIN_RELAY_AC = D8;

// ---------- Hardware ----------
#define DHTTYPE DHT11
DHT dht(PIN_DHT, DHTTYPE);
LiquidCrystal_I2C lcd(0x27, 16, 2); // Try 0x3F if your LCD address is different

// ---------- Relay logic: active LOW ----------
const uint8_t RELAY_ON  = LOW;
const uint8_t RELAY_OFF = HIGH;

// ---------- Load estimates and tariff ----------
const float WATT_LIGHT = 20.0f;
const float WATT_FAN   = 65.0f;
const float WATT_PC    = 120.0f;
const float WATT_AC    = 1200.0f;
const float TARIFF_BDT = 13.01f;

// ---------- Sensor/control settings ----------
float thresholdTempAC = 24.0f;

// These values describe estimated BRIGHTNESS, not raw ADC.
// Light turns ON at/below LIGHT_ON_BRIGHTNESS and OFF at/above LIGHT_OFF_BRIGHTNESS.
int LIGHT_ON_BRIGHTNESS  = 35;
int LIGHT_OFF_BRIGHTNESS = 45;

// Set true if raw LDR ADC is HIGH in darkness; false if ADC is LOW in darkness.
const bool LDR_DARK_ADC_HIGH = false;

// Keep occupancy active briefly after the last PIR detection, then shut down in sequence.
const unsigned long OCCUPANCY_HOLD_MS = 30000UL;
const unsigned long DELAY_OFF_AC      = 5000UL;
const unsigned long DELAY_OFF_FAN     = 7000UL;
const unsigned long DELAY_OFF_PC      = 9000UL;
const unsigned long DELAY_OFF_LIGHT  = 11000UL;

// ---------- Timing ----------
const unsigned long INTERVAL_DHT    = 2500UL;
const unsigned long INTERVAL_LCD    = 6000UL; // Change LCD page every 6 seconds
const unsigned long INTERVAL_BLYNK  = 2000UL;
const unsigned long INTERVAL_ENERGY = 1000UL;
const unsigned long INTERVAL_LDR    = 200UL;

// ---------- State ----------
bool manualMode = false;
bool motionDetected = false;
bool lightState = false;
bool fanState = false;
bool pcState = false;
bool acState = false;

float currentTemp = 0.0f;
float currentHumidity = 0.0f;
int currentLightPct = 0;
int currentLdrAdc = 0;
bool dhtHasValidReading = false;

unsigned long lastMotionTime = 0;
unsigned long prevDhtMillis = 0;
unsigned long prevLcdMillis = 0;
unsigned long prevBlynkMillis = 0;
unsigned long prevEnergyMillis = 0;
unsigned long lastWiFiRetryMillis = 0;
unsigned long prevLdrMillis = 0;

float totalSavedEnergy_kWh = 0.0f;
float totalSavedCost_BDT = 0.0f;

// LDR moving-average filter
const uint8_t FILTER_SAMPLES = 10;
int ldrSamples[FILTER_SAMPLES];
uint8_t sampleIndex = 0;
long sampleSum = 0;

// ---------- Function declarations ----------
void readDhtSensor();
void readLdrSensor();
void executeAutomationLogic();
void handleSequentialShutdown(unsigned long vacancyElapsed);
void updateEnergyMetrics();
void updateLCD();
void sendBlynkTelemetry();
void setRelay(uint8_t pin, bool state);
void applyAllRelays();
void printLdrDebug();

void setup() {
  Serial.begin(115200);
  delay(100);
  Serial.println();
  Serial.println(F("Starting Smart Classroom Energy System..."));

  // Set relay outputs OFF as early as possible.
  digitalWrite(PIN_RELAY_LT, RELAY_OFF);
  digitalWrite(PIN_RELAY_FN, RELAY_OFF);
  digitalWrite(PIN_RELAY_PC, RELAY_OFF);
  digitalWrite(PIN_RELAY_AC, RELAY_OFF);
  pinMode(PIN_RELAY_LT, OUTPUT);
  pinMode(PIN_RELAY_FN, OUTPUT);
  pinMode(PIN_RELAY_PC, OUTPUT);
  pinMode(PIN_RELAY_AC, OUTPUT);

  pinMode(PIN_PIR, INPUT);
  pinMode(PIN_LDR, INPUT);

  Wire.begin(D2, D1); // SDA, SCL
  lcd.init();
  lcd.backlight();
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print(F("Smart Classroom"));
  lcd.setCursor(0, 1);
  lcd.print(F("Starting..."));

  dht.begin();

  // Initialize LDR filter with the current ADC value.
  currentLdrAdc = analogRead(PIN_LDR);
  for (uint8_t i = 0; i < FILTER_SAMPLES; i++) {
    ldrSamples[i] = currentLdrAdc;
    sampleSum += currentLdrAdc;
  }
  readLdrSensor();

  // Start in vacant/off state until the PIR detects movement.
  lastMotionTime = millis() - OCCUPANCY_HOLD_MS - DELAY_OFF_LIGHT;

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.persistent(false);
  WiFi.begin(ssid, pass);

  Serial.print(F("Connecting to Wi-Fi: "));
  Serial.println(ssid);
  unsigned long wifiStart = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - wifiStart < 20000UL) {
    delay(500);
    Serial.print('.');
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println(F("\nWi-Fi connected!"));
    Serial.print(F("IP address: "));
    Serial.println(WiFi.localIP());
    Serial.println(F("Connecting to Blynk..."));
    Blynk.config(BLYNK_AUTH_TOKEN);
    if (Blynk.connect(3000)) {
      Serial.println(F("Blynk connected!"));
    } else {
      Serial.println(F("Blynk not connected yet; will retry."));
    }
  } else {
    Serial.print(F("\nWi-Fi connection failed. Status code: "));
    Serial.println((int)WiFi.status());
    Serial.println(F("System will keep trying in the background."));
  }

  lcd.clear();
  prevDhtMillis = millis() - INTERVAL_DHT;
  prevLdrMillis = millis() - INTERVAL_LDR;
  prevLcdMillis = millis();
  prevBlynkMillis = millis();
  prevEnergyMillis = millis();
}

void loop() {
  // Retry Wi-Fi if it is disconnected; do not block the sensor/control loop.
  if (WiFi.status() != WL_CONNECTED &&
      millis() - lastWiFiRetryMillis >= 10000UL) {
    lastWiFiRetryMillis = millis();
    Serial.println(F("Wi-Fi disconnected; retrying..."));
    WiFi.disconnect();
    WiFi.begin(ssid, pass);
  }

  // Keep Blynk running and reconnect at a controlled interval.
  if (WiFi.status() == WL_CONNECTED) {
    if (Blynk.connected()) {
      Blynk.run();
    } else {
      static unsigned long lastReconnectAttempt = 0;
      if (millis() - lastReconnectAttempt >= 5000UL) {
        lastReconnectAttempt = millis();
        Blynk.connect(100);
      }
    }
  }

  const unsigned long now = millis();

  if (now - prevLdrMillis >= INTERVAL_LDR) {
    prevLdrMillis = now;
    readLdrSensor();
  }

  if (now - prevDhtMillis >= INTERVAL_DHT) {
    prevDhtMillis = now;
    readDhtSensor();
  }

  // PIR is checked continuously so brief motion pulses are not missed.
  if (digitalRead(PIN_PIR) == HIGH) {
    motionDetected = true;
    lastMotionTime = now;
  } else {
    motionDetected = false;
  }

  if (!manualMode) {
    executeAutomationLogic();
  }

  if (now - prevEnergyMillis >= INTERVAL_ENERGY) {
    const unsigned long elapsedMs = now - prevEnergyMillis;
    prevEnergyMillis = now;
    updateEnergyMetrics();
    (void)elapsedMs;
  }

  if (now - prevLcdMillis >= INTERVAL_LCD) {
    prevLcdMillis = now;
    updateLCD();
  }

  if (now - prevBlynkMillis >= INTERVAL_BLYNK) {
    prevBlynkMillis = now;
    if (Blynk.connected()) {
      sendBlynkTelemetry();
    }
  }
}

void readDhtSensor() {
  float t = dht.readTemperature();
  float h = dht.readHumidity();

  // Accept only plausible DHT11 readings
  if (!isnan(t) && !isnan(h) &&
      t >= 0.0 && t <= 50.0 &&
      h >= 0.0 && h <= 100.0) {

    currentTemp = t;
    currentHumidity = h;
    dhtHasValidReading = true;

  } else {
    Serial.println("DHT11 error: Invalid sensor reading");
  }
}

void readLdrSensor() {
  sampleSum -= ldrSamples[sampleIndex];
  ldrSamples[sampleIndex] = analogRead(PIN_LDR);
  sampleSum += ldrSamples[sampleIndex];
  sampleIndex = (sampleIndex + 1) % FILTER_SAMPLES;

  currentLdrAdc = (int)(sampleSum / FILTER_SAMPLES);

  // Convert ADC to estimated brightness so 0 = dark and 100 = bright.
  if (LDR_DARK_ADC_HIGH) {
    currentLightPct = map(currentLdrAdc, 0, 1023, 100, 0);
  } else {
    currentLightPct = map(currentLdrAdc, 0, 1023, 0, 100);
  }
  currentLightPct = constrain(currentLightPct, 0, 100);
}

void executeAutomationLogic() {
  const unsigned long elapsedSinceMotion = millis() - lastMotionTime;
  const bool occupied = (elapsedSinceMotion < OCCUPANCY_HOLD_MS);

  if (occupied) {
    // Fan and PC on while the room is considered occupied.
    fanState = true;
    pcState = true;

    // AC follows temperature only when a valid DHT reading is available.
    if (dhtHasValidReading) {
      acState = (currentTemp >= thresholdTempAC);
    } else {
      acState = false;
    }

    // Hysteresis prevents rapid relay switching around one threshold.
    if (currentLightPct <= LIGHT_ON_BRIGHTNESS) {
      lightState = true;
    } else if (currentLightPct >= LIGHT_OFF_BRIGHTNESS) {
      lightState = false;
    }
  } else {
    // Start the staged shutdown only after the occupancy hold time.
    const unsigned long vacancyElapsed = elapsedSinceMotion - OCCUPANCY_HOLD_MS;
    handleSequentialShutdown(vacancyElapsed);
  }

  applyAllRelays();
}

void handleSequentialShutdown(unsigned long vacancyElapsed) {
  if (vacancyElapsed >= DELAY_OFF_AC)    acState = false;
  if (vacancyElapsed >= DELAY_OFF_FAN)   fanState = false;
  if (vacancyElapsed >= DELAY_OFF_PC)    pcState = false;
  if (vacancyElapsed >= DELAY_OFF_LIGHT) lightState = false;
}

void updateEnergyMetrics() {
  // Count estimated savings only while the room is vacant and each load is OFF.
  const unsigned long elapsedSinceMotion = millis() - lastMotionTime;
  if (elapsedSinceMotion < OCCUPANCY_HOLD_MS + DELAY_OFF_LIGHT) {
    return;
  }

  float savedWatts = 0.0f;
  if (!acState)    savedWatts += WATT_AC;
  if (!fanState)   savedWatts += WATT_FAN;
  if (!pcState)    savedWatts += WATT_PC;
  if (!lightState) savedWatts += WATT_LIGHT;

  // updateEnergyMetrics() is called approximately once per second.
  const float incrementKWh = (savedWatts / 1000.0f) / 3600.0f;
  totalSavedEnergy_kWh += incrementKWh;
  totalSavedCost_BDT = totalSavedEnergy_kWh * TARIFF_BDT;
}

void setRelay(uint8_t pin, bool state) {
  digitalWrite(pin, state ? RELAY_ON : RELAY_OFF);
}

void applyAllRelays() {
  setRelay(PIN_RELAY_LT, lightState);
  setRelay(PIN_RELAY_FN, fanState);
  setRelay(PIN_RELAY_PC, pcState);
  setRelay(PIN_RELAY_AC, acState);
}

void updateLCD() {
  static bool showEnergyPage = false;
  lcd.clear();

  if (!showEnergyPage) {
    lcd.setCursor(0, 0);
    lcd.print(F("T:"));
    if (dhtHasValidReading) lcd.print(currentTemp, 1);
    else lcd.print(F("--.-"));
    lcd.print(F("C H:"));
    if (dhtHasValidReading) lcd.print(currentHumidity, 0);
    else lcd.print(F("--"));
    lcd.print(F("%"));

    lcd.setCursor(0, 1);
    lcd.print(F("L:"));
    lcd.print(currentLightPct);
    lcd.print(F("% Occ:"));
    const bool occupied = (millis() - lastMotionTime < OCCUPANCY_HOLD_MS);
    lcd.print(occupied ? F("YES") : F("NO"));
  } else {
    lcd.setCursor(0, 0);
    lcd.print(F("Saved:"));
    lcd.print(totalSavedEnergy_kWh, 3);
    lcd.print(F("kWh"));

    lcd.setCursor(0, 1);
    lcd.print(F("Cut: Tk "));
    lcd.print(totalSavedCost_BDT, 2);
  }

  showEnergyPage = !showEnergyPage;
}

void sendBlynkTelemetry() {
  // V0-V7 are OUTPUT/monitoring datastreams on the user's dashboard.
  // V8-V14 are control inputs, so do not overwrite them with telemetry.
  Blynk.virtualWrite(V0, currentTemp);
  Blynk.virtualWrite(V1, currentHumidity);
  Blynk.virtualWrite(V2, currentLightPct);
  Blynk.virtualWrite(V3, (millis() - lastMotionTime < OCCUPANCY_HOLD_MS) ? 1 : 0);
  Blynk.virtualWrite(V4, acState ? 1 : 0);
  Blynk.virtualWrite(V5, fanState ? 1 : 0);
  Blynk.virtualWrite(V6, pcState ? 1 : 0);
  Blynk.virtualWrite(V7, lightState ? 1 : 0);
}

// Restore dashboard input values after reconnect.
BLYNK_CONNECTED() {
  Blynk.syncVirtual(V8, V9, V10, V11, V12, V13, V14);
}

// ---------- Blynk controls: MATCHES THE PROVIDED DASHBOARD ----------
BLYNK_WRITE(V8) { // Manual Mode switch
  manualMode = (param.asInt() == 1);
  if (manualMode) {
    // Apply the latest values stored by V9-V12 controls.
    applyAllRelays();
  }
  // When OFF, automatic control resumes in loop().
}

BLYNK_WRITE(V9) { // AC Control switch
  acState = (param.asInt() == 1);
  if (manualMode) setRelay(PIN_RELAY_AC, acState);
}

BLYNK_WRITE(V10) { // Fan Control switch
  fanState = (param.asInt() == 1);
  if (manualMode) setRelay(PIN_RELAY_FN, fanState);
}

BLYNK_WRITE(V11) { // PC Control switch
  pcState = (param.asInt() == 1);
  if (manualMode) setRelay(PIN_RELAY_PC, pcState);
}

BLYNK_WRITE(V12) { // Light Control switch
  lightState = (param.asInt() == 1);
  if (manualMode) setRelay(PIN_RELAY_LT, lightState);
}

BLYNK_WRITE(V13) { // AC temperature threshold slider
  thresholdTempAC = param.asFloat();
}

BLYNK_WRITE(V14) { // Light ON brightness threshold slider
  LIGHT_ON_BRIGHTNESS = constrain(param.asInt(), 0, 100);
  LIGHT_OFF_BRIGHTNESS = min(100, LIGHT_ON_BRIGHTNESS + 10);
}

void printLdrDebug() {
  Serial.print(F("LDR ADC: "));
  Serial.print(currentLdrAdc);
  Serial.print(F(" | Brightness: "));
  Serial.print(currentLightPct);
  Serial.println(F("%"));
}
