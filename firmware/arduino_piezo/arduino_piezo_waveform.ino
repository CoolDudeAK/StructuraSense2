// StructuraSense — raw vibration capture from ONE piezo/accelerometer on A0 (Arduino UNO).
// Sends one line per capture:  W|<device_id>|<sample_rate>|v1,v2,...   (256 samples; server needs 64+)
// Create a vibration device with this id first (Connect Data -> Devices). Piezo needs a protection circuit.
const char* DEVICE_ID = "ard-piezo-01";
const int N = 256;
const unsigned long FS = 500;                // samples per second
int buf[N];

void setup() { Serial.begin(115200); }

void loop() {
  unsigned long period = 1000000UL / FS, t = micros();
  for (int i = 0; i < N; i++) {
    while (micros() - t < period) {}
    t += period;
    buf[i] = analogRead(A0);
  }
  Serial.print("W|"); Serial.print(DEVICE_ID); Serial.print("|"); Serial.print(FS); Serial.print("|");
  for (int i = 0; i < N; i++) { Serial.print(buf[i]); if (i < N - 1) Serial.print(","); }
  Serial.println();
  delay(2000);
}
