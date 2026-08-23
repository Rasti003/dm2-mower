# Instrukcje projektu dm2-mower

## Cel

Projekt służy do pasywnego podsłuchiwania do czterech linii UART TTL 3,3 V robota koszącego za pomocą ESP32-WROOM-32D. Panel WWW umożliwia konfigurację, podgląd, nagrywanie bajtów oraz nagrywanie surowych zboczy do późniejszego wykrywania parametrów UART.

## Zasady bezpieczeństwa

- Logger ma być urządzeniem tylko odbiorczym. Nie podłączaj wyjść TX ESP32 do robota.
- Obserwowaną linię TX podłączaj przez rezystor szeregowy 4,7 kΩ i zawsze łącz wspólną masę.
- Zakładany poziom logiczny to 3,3 V. Przed podłączeniem innego urządzenia sprawdź napięcie.
- Nigdy nie dodawaj do Git `include/wifi_config.h`, tokenów, haseł ani plików uwierzytelniających Codexa.

## Sprzęt loggera

- CH1: GPIO16, sprzętowy UART
- CH2: GPIO17, sprzętowy UART
- CH3: GPIO32, sprzętowy UART
- CH4: GPIO33, programowy UART
- GPIO25, GPIO26 i GPIO27 są nieużywanymi pinami TX i mają pozostać niepodłączone.

## Weryfikacja zmian

- Po zmianach firmware uruchom kompilację PlatformIO dla środowiska `esp32dev`.
- Po zmianach panelu WWW sprawdź go na działającym ESP32 w przeglądarce.
- Przy surowym nagrywaniu wymagaj `luki rekordów: 0` oraz `zgubione zbocza: 0`.
- Nie zmieniaj formatu eksportu bez zwiększenia pola `version` i aktualizacji README.

## Format danych

- Zdekodowane bajty: `uart-logger`, wersja 1, JSONL.
- Surowe zbocza: `uart-edge-logger`, wersja 2, JSONL.
- W surowym polu `raw` każde 8 cyfr HEX to słowo uint32: bit 31 oznacza poziom, a bity 0–30 czas trwania w jednostkach 0,25 µs.

## Komunikacja

Odpowiadaj użytkownikowi po polsku. Pisz konkretnie i objaśniaj połączenia sprzętowe przed próbami na robocie.
