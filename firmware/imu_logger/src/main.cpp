// BNO085 IMU logger for the parachute payload (ESP32-S3, native USB CDC).
//
// Streams, over USB serial, text lines the laptop recorder (scripts/imu_record.py) turns into the
// pipeline's observation bundle (imu.csv, led_events.csv):
//   # ...                                 comments / status
//   I,<t_s>,<ax>,<ay>,<az>,<gx>,<gy>,<gz>  one IMU sample: MCU time [s], accel [m/s^2], gyro [rad/s]
//   L,<t_s>,<state>                        sync-LED toggle (1 = on), same MCU clock
//
// Accel = SH2_ACCELEROMETER (includes gravity), gyro = SH2_GYROSCOPE_UNCALIBRATED (bias NOT removed).
// The BNO085's dynamic (background) calibration is switched off so bias stays fixed during a log:
// required for Allan-variance analysis, and it matches the pipeline, which estimates bias itself.
// All times come from the ESP32 64-bit microsecond timer (sensor sample times are back-dated by the
// SH2 driver to the actual sample instant, in the same time base).
#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_BNO08x.h>
#include "esp_timer.h"
extern "C" {
#include "sh2.h"
}

#ifndef LED_PIN
#define LED_PIN 21
#endif
#ifndef LED_ACTIVE_LOW
#define LED_ACTIVE_LOW 1
#endif
#ifndef BNO_SDA
#define BNO_SDA -1
#endif
#ifndef BNO_SCL
#define BNO_SCL -1
#endif
#ifndef IMU_PERIOD_US
#define IMU_PERIOD_US 5000
#endif

static Adafruit_BNO08x bno(-1);
static int g_sda = -1, g_scl = -1;
static uint8_t g_addr = 0;

// ---------------------------------------------------------------- sync LED: pseudo-random toggles
// on/off durations uniform in [60, 160] ms (same distribution as the simulator's LED code); every
// toggle is logged with its MCU time, which is all the pipeline needs for camera/IMU clock alignment.
static uint32_t g_rng = 77;
static uint32_t xorshift() { g_rng ^= g_rng << 13; g_rng ^= g_rng >> 17; g_rng ^= g_rng << 5; return g_rng; }
static int64_t g_next_toggle = 0;
static int g_led = 0;
static void led_write(int on) { digitalWrite(LED_PIN, (on ^ LED_ACTIVE_LOW) ? HIGH : LOW); }
static void led_service(int64_t now) {
  if (now < g_next_toggle) return;
  g_led = !g_led;
  led_write(g_led);
  Serial.printf("L,%.6f,%d\n", now * 1e-6, g_led);
  g_next_toggle = now + 60000 + (int64_t)(xorshift() % 100001);
}

// ---------------------------------------------------------------- I2C auto-detect
static bool probe(int sda, int scl, uint8_t &addr) {
  Wire.end();
  if (!Wire.begin(sda, scl, 400000)) return false;
  for (uint8_t a : {(uint8_t)0x4A, (uint8_t)0x4B}) {
    Wire.beginTransmission(a);
    if (Wire.endTransmission() == 0) { addr = a; return true; }
  }
  return false;
}

static bool find_bno() {
  if (BNO_SDA >= 0 && BNO_SCL >= 0) {
    if (probe(BNO_SDA, BNO_SCL, g_addr)) { g_sda = BNO_SDA; g_scl = BNO_SCL; return true; }
    return false;
  }
  // common ESP32-S3 board I2C pins: XIAO (5,6), DevKitC (8,9), Feather (3,4), QT Py (41,40) / STEMMA,
  // plus a few frequent custom pairs; both orientations
  static const int pairs[][2] = {{5, 6}, {8, 9}, {3, 4}, {41, 40}, {1, 2}, {4, 5}, {6, 7}, {17, 18},
                                 {10, 11}, {13, 14}, {38, 39}, {42, 41}, {7, 8}, {15, 16}};
  for (auto &p : pairs) {
    for (int o = 0; o < 2; ++o) {
      int sda = o ? p[1] : p[0], scl = o ? p[0] : p[1];
      if (sda == LED_PIN || scl == LED_PIN) continue;
      if (probe(sda, scl, g_addr)) { g_sda = sda; g_scl = scl; return true; }
    }
  }
  Wire.end();
  return false;
}

static void configure_reports() {
  bno.enableReport(SH2_ACCELEROMETER, IMU_PERIOD_US);
  bno.enableReport(SH2_GYROSCOPE_UNCALIBRATED, IMU_PERIOD_US);
  int rc = sh2_setCalConfig(0);  // dynamic calibration off (accel, gyro, mag)
  Serial.printf("# reports enabled: period_us=%d dynamic_cal=off (rc=%d)\n", IMU_PERIOD_US, rc);
}

static void header() {
  Serial.printf("# imu_logger v1 chip=ESP32-S3 sda=%d scl=%d addr=0x%02X led_pin=%d period_us=%d\n",
                g_sda, g_scl, g_addr, LED_PIN, IMU_PERIOD_US);
  Serial.println("# columns: I,t_s,ax,ay,az,gx,gy,gz | L,t_s,state");
}

void setup() {
  Serial.begin(921600);
  pinMode(LED_PIN, OUTPUT);
  led_write(0);
  uint32_t t0 = millis();
  while (!Serial && millis() - t0 < 3000) delay(10);
  while (!find_bno()) {
    Serial.println("# ERROR BNO085 not found on any probed I2C pins (set BNO_SDA/BNO_SCL); retrying");
    for (int i = 0; i < 10; ++i) { led_write(i & 1); delay(100); }
  }
  if (!bno.begin_I2C(g_addr, &Wire)) {
    Serial.println("# ERROR BNO085 answered on I2C but SH2 init failed; rebooting");
    delay(1000);
    ESP.restart();
  }
  header();
  configure_reports();
  g_next_toggle = esp_timer_get_time() + 50000;
}

static float ax, ay, az;
static bool have_acc = false;

void loop() {
  if (bno.wasReset()) {
    Serial.println("# WARN sensor reset; re-enabling reports");
    configure_reports();
  }
  sh2_SensorValue_t v;
  while (bno.getSensorEvent(&v)) {
    if (v.sensorId == SH2_ACCELEROMETER) {
      ax = v.un.accelerometer.x; ay = v.un.accelerometer.y; az = v.un.accelerometer.z;
      have_acc = true;
    } else if (v.sensorId == SH2_GYROSCOPE_UNCALIBRATED && have_acc) {
      Serial.printf("I,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f\n", v.timestamp * 1e-6, ax, ay, az,
                    v.un.gyroscopeUncal.x, v.un.gyroscopeUncal.y, v.un.gyroscopeUncal.z);
    }
  }
  led_service(esp_timer_get_time());
  while (Serial.available()) {
    int c = Serial.read();
    if (c == 'h') header();
  }
}
