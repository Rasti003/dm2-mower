# Kontekst projektu dm2-mower

## Stan na 2026-08-23

Firmware loggera jest skompilowany i wgrany na klasyczny ESP32-WROOM-32D. Urządzenie łączy się z Wi-Fi, udostępnia panel pod `http://uart-logger.local/` oraz obsługuje aktualizację OTA.

Aktualnie działają:

- cztery wejścia RX z osobną nazwą, prędkością i formatem UART;
- podgląd HEX i ASCII na telefonie;
- kilkuminutowe nagrywanie bajtów w pamięci przeglądarki i eksport JSONL;
- ciągłe nagrywanie surowych zmian stanu czterech wejść z rozdzielczością 0,25 µs;
- liczniki luk rekordów, przepełnienia programowego CH4 i zgubionych zboczy;
- OTA przez stronę WWW i skrypt PowerShell.

## Ważna historia techniczna

Pierwsza wersja surowego przechwytywania używała RMT i ucinała każdą transmisję po dokładnie 128 odcinkach. Została zastąpiona ciągłymi buforami zboczy z przerwań GPIO. Aktualny format surowy ma wersję 2 i używa 32-bitowych czasów.

Niepodłączone wejścia są podciągnięte do stanu HIGH, aby nie generowały fałszywych przerwań. Panel przy pierwszym otwarciu pobiera tylko bieżący numer sekwencji, a następnie nowe rekordy, dzięki czemu nie przeciąża ESP starym buforem.

## Zweryfikowany test

Nadajnik testowy ESP32-C3 wysyła na GPIO4 ramki tekstowe i binarne w konfiguracji 9600 8N1. Logger poprawnie rozpoznał ze zboczy czas bitu około 104,2 µs, czyli około 9600 baud. Ostatni test surowy po świeżym otwarciu panelu zapisał 91 bloków i około 19,6 kB przy zerowej liczbie luk i zgubionych zboczy.

Kod nadajnika znajduje się w `simulator-c3/`.

## Następny etap

Podłączyć pasywnie linie TX płyty komunikacyjnej robota, nadać kanałom opisowe nazwy i wykonać równolegle:

1. zapis surowych zboczy do wykrycia prędkości i formatu;
2. zapis bajtów po ustawieniu najbardziej prawdopodobnych parametrów;
3. analizę powtarzalnych nagłówków, długości ramek, kierunków komunikacji i sum kontrolnych.

## Pliki lokalne i sekrety

`include/wifi_config.h`, `.pio/` oraz `tools/` nie są wersjonowane. Na nowym komputerze skopiuj `include/wifi_config.example.h` do `include/wifi_config.h` i wpisz dane Wi-Fi lokalnie. Nie umieszczaj haseł w Git.
