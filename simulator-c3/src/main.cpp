#include <Arduino.h>
#include <U8g2lib.h>
#include <Wire.h>

namespace {

constexpr uint32_t TEST_BAUD = 9600;
constexpr int UART_RX_UNUSED_PIN = 1;
constexpr int UART_TX_PIN = 4;
constexpr uint8_t OLED_ADDRESS = 0x3C;

struct I2cPins {
  uint8_t sda;
  uint8_t scl;
};

constexpr I2cPins OLED_CANDIDATES[] = {{5, 6}, {6, 5}, {8, 9}, {9, 8}};

HardwareSerial testUart(1);
U8G2 *display = nullptr;
I2cPins detectedPins{0, 0};
uint32_t frameNumber = 0;
uint32_t lastPacketAt = 0;

const char *JOKES[] = {
    "BLAD 404: TRAWA NIE ZNALEZIONA",
    "KRET MELDUJE: TEREN CZYSTY",
    "KOSIARKA.EXE DZIALA... CHYBA",
    "UWAGA: STOKROTKA W SEKTORZE 7",
    "ROBOT PROSI O URLOP I OLEJ",
    "BEEP BOOP. TRAWNIK POKONANY",
};

bool oledResponds(uint8_t sda, uint8_t scl) {
  Wire.end();
  delay(5);
  Wire.begin(sda, scl, 100000);
  Wire.beginTransmission(OLED_ADDRESS);
  bool found = Wire.endTransmission() == 0;
  Wire.end();
  return found;
}

bool setupDisplay() {
  for (const I2cPins &pins : OLED_CANDIDATES) {
    if (!oledResponds(pins.sda, pins.scl)) continue;
    detectedPins = pins;
    display = new U8G2_SSD1306_72X40_ER_F_SW_I2C(
        U8G2_R0, pins.scl, pins.sda, U8X8_PIN_NONE);
    display->begin();
    display->setContrast(255);
    return true;
  }
  return false;
}

void drawFace(uint32_t now) {
  if (!display) return;
  const uint32_t cycle = now % 5200;
  const bool blink = (cycle > 4200 && cycle < 4350) ||
                     (cycle > 4470 && cycle < 4580);
  const int8_t lookX = static_cast<int8_t>((now / 700) % 3) - 1;
  const int8_t lookY = static_cast<int8_t>((now / 1300) % 3) - 1;

  display->clearBuffer();
  display->setFont(u8g2_font_4x6_tr);
  display->drawStr(17, 6, "UART GREMLIN");
  if (blink) {
    display->drawHLine(8, 18, 20);
    display->drawHLine(44, 18, 20);
  } else {
    display->drawRFrame(7, 9, 22, 18, 5);
    display->drawRFrame(43, 9, 22, 18, 5);
    display->drawDisc(18 + lookX * 2, 18 + lookY, 3);
    display->drawDisc(54 + lookX * 2, 18 + lookY, 3);
  }
  if ((now / 900) % 2) {
    display->drawLine(27, 31, 32, 35);
    display->drawHLine(32, 35, 9);
    display->drawLine(40, 35, 45, 31);
  } else {
    display->drawRBox(27, 30, 18, 7, 2);
    display->setDrawColor(0);
    display->drawVLine(33, 31, 5);
    display->drawVLine(39, 31, 5);
    display->setDrawColor(1);
  }
  display->sendBuffer();
}

void drawMessage(const char *top, const char *bottom) {
  if (!display) return;
  display->clearBuffer();
  display->drawRFrame(0, 0, 72, 40, 5);
  display->setFont(u8g2_font_6x10_tf);
  int topX = max(3, (72 - static_cast<int>(strlen(top)) * 6) / 2);
  int bottomX = max(3, (72 - static_cast<int>(strlen(bottom)) * 6) / 2);
  display->drawStr(topX, 16, top);
  display->drawStr(bottomX, 31, bottom);
  display->sendBuffer();
}

uint8_t textChecksum(const char *text) {
  uint8_t checksum = 0;
  while (*text) checksum ^= static_cast<uint8_t>(*text++);
  return checksum;
}

void sendAsciiPacket() {
  const char *joke = JOKES[frameNumber % (sizeof(JOKES) / sizeof(JOKES[0]))];
  char payload[180];
  snprintf(payload, sizeof(payload),
           "MOWER_SIM,%lu,VBAT=%u.%uV,BLADE=%s,RSSI=%d,MSG=%s",
           static_cast<unsigned long>(frameNumber), 23 + (frameNumber % 3),
           frameNumber % 10, (frameNumber % 4) ? "ON" : "OFF",
           -42 - static_cast<int>(frameNumber % 17), joke);
  char packet[210];
  snprintf(packet, sizeof(packet), "$%s*%02X\r\n", payload,
           textChecksum(payload));
  testUart.print(packet);
  Serial.print(packet);
  if (display && frameNumber % 6 == 0) drawMessage("UART TX", "9600 8N1");
}

void sendBinaryPacket(uint32_t now) {
  uint8_t packet[12] = {
      0xA5, 0x5A, 0x07, static_cast<uint8_t>(frameNumber),
      static_cast<uint8_t>(frameNumber >> 8), static_cast<uint8_t>(now),
      static_cast<uint8_t>(now >> 8), static_cast<uint8_t>(70 + frameNumber % 30),
      static_cast<uint8_t>(frameNumber % 2), 0xDE, 0xAD, 0x00,
  };
  uint8_t checksum = 0;
  for (size_t i = 0; i < sizeof(packet) - 1; ++i) checksum ^= packet[i];
  packet[sizeof(packet) - 1] = checksum;
  testUart.write(packet, sizeof(packet));
  Serial.print("BIN: ");
  for (uint8_t value : packet) Serial.printf("%02X ", value);
  Serial.println();
}

}  // namespace

void setup() {
  Serial.begin(115200);
  delay(300);
  testUart.begin(TEST_BAUD, SERIAL_8N1, UART_RX_UNUSED_PIN, UART_TX_PIN);
  bool oledFound = setupDisplay();
  Serial.printf("\nESP32-C3 UART TOY\nTX=GPIO%d, %lu 8N1\nOLED=%s SDA=%u SCL=%u\n",
                UART_TX_PIN, static_cast<unsigned long>(TEST_BAUD),
                oledFound ? "OK" : "BRAK", detectedPins.sda, detectedPins.scl);
  if (oledFound) drawMessage("HEJ!", "UART TIME");
  delay(1200);
}

void loop() {
  const uint32_t now = millis();
  if (now - lastPacketAt >= 1000) {
    lastPacketAt = now;
    sendAsciiPacket();
    if (frameNumber % 4 == 3) sendBinaryPacket(now);
    ++frameNumber;
  }
  if (frameNumber % 6 != 1 || now - lastPacketAt > 650) drawFace(now);
  delay(40);
}
