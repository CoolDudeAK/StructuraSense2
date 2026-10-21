// StructuraSense — ESP32 -> HTTP. Posts one reading every 2 s. Replace readSensor() with your sensor code.
// Create the device in the app first (Connect Data -> Devices -> Add device) and paste its key below.
#include <WiFi.h>
#include <HTTPClient.h>

const char* WIFI_SSID  = "YOUR_WIFI";
const char* WIFI_PASS  = "YOUR_PASSWORD";
const char* URL        = "http://COMPUTER_IP:5000/api/ingest/readings";  // your computer's address, not 127.0.0.1
const char* DEVICE_ID  = "esp-strain-04";
const char* DEVICE_KEY = "PASTE_KEY_HERE";

float readSensor() { return analogRead(34) * (3.3 / 4095.0); }  // placeholder: voltage on GPIO34

void setup() {
  Serial.begin(115200);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) { delay(300); Serial.print("."); }
  Serial.println("\nWi-Fi connected");
}

void loop() {
  HTTPClient http;
  http.begin(URL);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Device-Key", DEVICE_KEY);
  String body = String("{\"device_id\":\"") + DEVICE_ID + "\",\"readings\":[{\"value\":" + String(readSensor(), 4) + "}]}";
  int code = http.POST(body);
  Serial.println(code);  // 200 = accepted, 401 = wrong key, 404 = unknown device id
  http.end();
  delay(2000);
}
