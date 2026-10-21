/*
  StructuraSense — Test Firmware for Arduino UNO
  ------------------------------------------------
  Reads 3 piezoelectric sensors on A0, A1, A2 and prints their
  peak-to-peak response over a short sampling window, once per loop,
  in the format expected by the StructuraSense Python application:

      184,126,171

  (Sensor1_P2P,Sensor2_P2P,Sensor3_P2P)

  ---------------------------------------------------------------
  SIMULATED MODE (default):
  If USE_SIMULATED_DATA is set to true below, this firmware ignores
  the actual analog pins and instead sends realistic RANDOM values so
  you can test the StructuraSense software immediately, even before
  the piezo sensors / concrete specimen are wired up.

  REAL SENSOR MODE:
  Set USE_SIMULATED_DATA to false once your piezo sensors are wired to
  A0, A1, A2. No other code changes are required — the sampling and
  serial output logic is identical in both modes.
  ---------------------------------------------------------------

  IMPORTANT SAFETY NOTE:
  This firmware assumes a basic piezo-to-analog-input circuit (e.g. a
  piezo disc with a protection resistor/diode clamp). Do not connect a
  bare piezo element directly to an Arduino analog pin without a
  current-limiting / voltage-clamping circuit, as piezo elements can
  generate voltage spikes outside the Arduino's safe input range. This
  firmware does not validate that your specific hardware circuit is
  electrically safe — verify your circuit design separately.
*/

const bool USE_SIMULATED_DATA = true;   // set to false once real sensors are wired in

const int PIN_S1 = A0;
const int PIN_S2 = A1;
const int PIN_S3 = A2;

const unsigned int SAMPLE_WINDOW_MS = 100;   // how long to sample per reading window
const unsigned int SAMPLE_DELAY_US  = 200;   // delay between individual analogReads

void setup() {
  Serial.begin(115200);
  randomSeed(analogRead(A5));  // seed RNG from a floating pin, for simulated mode
}

int samplePeakToPeak(int pin) {
  int minVal = 1023;
  int maxVal = 0;
  unsigned long start = millis();
  while (millis() - start < SAMPLE_WINDOW_MS) {
    int v = analogRead(pin);
    if (v < minVal) minVal = v;
    if (v > maxVal) maxVal = v;
    delayMicroseconds(SAMPLE_DELAY_US);
  }
  return maxVal - minVal;
}

int simulatedReading(int baseline) {
  // Baseline +/- small random noise, occasionally with a bigger jump
  // so you can also see what an "anomaly" packet looks like.
  int noise = random(-8, 9);
  return baseline + noise;
}

void loop() {
  int s1, s2, s3;

  if (USE_SIMULATED_DATA) {
    s1 = simulatedReading(180);
    s2 = simulatedReading(165);
    s3 = simulatedReading(174);
  } else {
    s1 = samplePeakToPeak(PIN_S1);
    s2 = samplePeakToPeak(PIN_S2);
    s3 = samplePeakToPeak(PIN_S3);
  }

  Serial.print(s1);
  Serial.print(",");
  Serial.print(s2);
  Serial.print(",");
  Serial.println(s3);

  delay(100);  // ~10 readings per second
}
