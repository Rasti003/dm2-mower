# Instrukcje projektu dm2-mower

## Cel

Projekt służy do pasywnego podsłuchiwania do czterech linii UART TTL 3,3 V robota koszącego za pomocą ESP32-WROOM-32D. Panel WWW umożliwia konfigurację, podgląd, nagrywanie bajtów oraz nagrywanie surowych zboczy do późniejszego wykrywania parametrów UART.

Przed rozpoczęciem pracy przeczytaj `PROJECT_CONTEXT.md`. Jest to bieżące źródło prawdy o stanie loggera oraz potwierdzonych odkryciach z platformy OpenDM2 / POINT PORLMW1. Zachowuj w nim rozróżnienie pomiędzy faktami potwierdzonymi, silnymi wnioskami i hipotezami.

## Zasady bezpieczeństwa

- Wszystkie kanały loggera mają pozostać odbiorcze. Jedyny wyjątek to jawnie uzbrajany terminal DM2 na GPIO25, ograniczony programowo do zatwierdzonych komend odczytowych.
- Ewentualny przyszły tryb aktywnej konsoli musi być osobną, domyślnie wyłączoną funkcją i wymaga osobnej decyzji użytkownika. Nie wolno przypadkowo zmienić pasywnego wejścia w wyjście.
- Obserwowaną linię TX podłączaj przez rezystor szeregowy 4,7 kΩ i zawsze łącz wspólną masę.
- Zakładany poziom logiczny to 3,3 V. Przed podłączeniem innego urządzenia sprawdź napięcie.
- Nigdy nie dodawaj do Git `include/wifi_config.h`, tokenów, haseł ani plików uwierzytelniających Codexa.

## Sprzęt loggera

- CH1: GPIO16, sprzętowy UART
- CH2: GPIO17, sprzętowy UART
- CH3: GPIO32, sprzętowy UART
- CH4: GPIO33, programowy UART
- GPIO25 jest opcjonalnym TX terminala DM2 i wolno go łączyć wyłącznie przez rezystor 1–4,7 kΩ z potwierdzonym RX konsoli 3,3 V. GPIO26 i GPIO27 mają pozostać niepodłączone.

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
