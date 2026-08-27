# ESP32 UART Logger — wersja 0.3

Logger czterech kanałów UART TTL 3,3 V dla ESP32-WROOM-32D / ESP32 DevKit. Trzy kanały korzystają ze sprzętowych UART-ów, a czwarty z SoftwareSerial. Rejestrowanie jest pasywne; opcjonalny, silnie ograniczony terminal nadaje wyłącznie na konsolę DM2 po jawnym uzbrojeniu.

Repozytorium zawiera także `portal/`: rozwijany panel Raspberry Pi **MOWBI
Command Deck**. Jego pierwszy moduł wykonuje wielokrotne, weryfikowane backupy
MCU przez CMSIS-DAP/SWD i przechowuje je lokalnie poza Git. Szczegóły znajdują
się w [`portal/README.md`](portal/README.md).

Repozytorium zawiera również `simulator-c3/` — firmware testowego ESP32-C3 z ekranem OLED, który wysyła ramki ASCII i binarne w konfiguracji 9600 8N1.

## Połączenia

| Kanał | Wejście ESP32 |
|---|---|
| CH1 | GPIO16 |
| CH2 | GPIO17 |
| CH3 | GPIO32 |
| CH4 | GPIO33 (programowy) |

Każdą obserwowaną linię TX podłącz przez rezystor szeregowy 4,7 kΩ do wybranego GPIO. Połącz GND ESP32 z GND badanej płyty. Nie podłączaj żadnego TX z ESP32 do robota.

GPIO26 i GPIO27 są technicznie przypisane jako nieużywane wyjścia TX. Zostaw je całkowicie niepodłączone. GPIO25 jest wyjściem opcjonalnego terminala powiązanego z CH1 i normalnie również pozostaje niepodłączone.

## Bezpieczny terminal DM2

Terminal jest przeznaczony dla potwierdzonej konsoli głównego MCU POINT PORLMW1: **115200, 8N1, TTL 3,3 V**.

```text
DM2 TX  -> GPIO16 (CH1 RX loggera)
DM2 RX  <- 1–4,7 kΩ <- GPIO25 (TX terminala)
DM2 GND -> GND ESP32
VCC     nie łączyć
```

Po każdym restarcie terminal jest rozbrojony. Panel wymaga potwierdzenia połączenia i uzbraja nadajnik tylko na dwie minuty. Dopuszczone są wyłącznie funkcje diagnostyczne odczytujące wersję, urządzenia, wątki, timery, kolejki, skrzynki, zdarzenia, muteksy, semafory, pule i stan pamięci. Klasyczny prompt `finsh >` wymaga składni wywołania funkcji z nawiasami. Każde wysłanie wymaga dodatkowego potwierdzenia. Komendy GPIO/PWM, aktualizacji, filesystemu i silników są blokowane przez firmware loggera.

`ui_msg_test()` jest dopuszczone osobno jako fabryczny test interfejsu użytkownika, bez argumentów. Warianty z argumentami pozostają zablokowane, dopóki ich znaczenie nie zostanie potwierdzone.

Znaki są wysyłane pojedynczo z krótkim odstępem, ponieważ konsola badanego DM2 gubiła co drugi znak podczas ciągłej transmisji. Polecenie jest kończone pojedynczym `CR`, aby FinSH nie wykonywał dodatkowego pustego polecenia po `LF`.

## Użycie

1. Wgraj firmware przez USB.
2. Telefonem połącz się z siecią Wi-Fi `UART-LOGGER`.
3. Hasło: `uartlogger`.
4. Otwórz `http://192.168.4.1`.
5. Nadaj kanałom własne nazwy oraz ustaw prędkość i format osobno dla każdego z nich.

## Nagrywanie na telefonie

Panel ma przycisk `Rozpocznij nagrywanie`. Podczas nagrania przechowuje w pamięci telefonu oryginalne bajty, numer kanału, kolejność rekordów i czas w mikrosekundach. Po zatrzymaniu użyj `Pobierz .jsonl`.

Każdy wiersz pliku JSONL jest niezależnym rekordem. Pierwszy zawiera konfigurację sesji, a kolejne pola `seq`, `us`, `ch` i `hex`. Licznik `luki` informuje, że telefon nie odebrał części rekordów przed nadpisaniem bufora ESP32. Podczas kilkuminutowego nagrania pozostaw panel otwarty; program próbuje włączyć blokadę wygaszania ekranu Androida.

Kanał CH4 może zgubić dane przy dużym ruchu lub wysokiej prędkości, ponieważ jest programowy. Panel pokazuje licznik `CH4 overflow`.

## Surowe zbocza i nieznana prędkość

Przycisk `Nagrywaj zbocza` zapisuje zmiany poziomu logicznego wszystkich czterech wejść niezależnie od ustawionej prędkości UART. ESP32 używa ciągłych buforów zboczy obsługiwanych przez przerwania GPIO z rozdzielczością 0,25 µs. Po zatrzymaniu telefon pobiera plik `uart-edges-*.jsonl`.

Pierwszy rekord opisuje format, rozdzielczość i nazwy kanałów. Kolejne zawierają `seq`, `us`, `ch` oraz pole `raw`. Pole `raw` jest ciągiem 32-bitowych słów zapisanych szesnastkowo: bit 31 oznacza poziom logiczny, a bity 0–30 czas trwania poziomu w jednostkach po 0,25 µs. Taki zapis można później wielokrotnie dekodować, próbując różnych prędkości, parzystości i liczby bitów stopu.

Liczniki `luki rekordów` i `zgubione zbocza` muszą pozostać równe zero. Przy bardzo intensywnym ruchu ilość danych o zboczach jest znacznie większa niż ilość zdekodowanych bajtów. Telefon zatrzymuje nagranie po osiągnięciu około 16 MB.

ESP32 próbuje jednocześnie połączyć się z domową siecią Wi-Fi 2,4 GHz. Bieżący adres IP jest widoczny w panelu. Awaryjny punkt `UART-LOGGER` pozostaje aktywny, więc błędne hasło nie odcina dostępu do konfiguracji.

Panel przechowuje dwa profile Wi-Fi. Można przełączyć aktywny profil jednym przyciskiem; wybór jest zapisywany w pamięci ESP32 i obowiązuje po restarcie. Nazwę i hasło aktywnego profilu można zmienić bez nadpisywania drugiego. Domyślne dane obu profili pochodzą z lokalnego, ignorowanego przez Git pliku `include/wifi_config.h`.

## Aktualizacja OTA

Po pierwszym wgraniu przez USB kolejne wersje można wysyłać przez Wi-Fi. Najprościej uruchomić:

```powershell
.\ota-upload.ps1
```

Firmware można również wgrać na stronie `http://uart-logger.local/update`. Login to `admin`, a hasło OTA jest takie samo jak hasło awaryjnego punktu dostępowego. Dane domowej sieci znajdują się w ignorowanym przez Git pliku `include/wifi_config.h`; można je również zmienić w panelu WWW.

Klasyczne Arduino OTA na porcie 3232 także pozostaje aktywne, ale zapora systemowa komputera może blokować wymagane połączenie zwrotne. Aktualizacja HTTP nie wymaga takiego połączenia.

Domyślna konfiguracja to 9600, 8N1. Ustawienia są zapisywane w pamięci ESP32.

## Ograniczenia wersji 0.3

- trzy sprzętowe kanały RX i jeden programowy;
- podgląd znajduje się w buforze RAM i nie jest jeszcze zapisywany na microSD;
- surowy zapis pozwala wykryć parametry po nagraniu, ale panel nie podaje jeszcze automatycznie wyniku baud rate;
- UART0 jest przekierowany na GPIO32, dlatego po uruchomieniu firmware nie ma konsoli przez USB. Tryb programowania po resecie nadal korzysta ze standardowego portu USB-UART.
