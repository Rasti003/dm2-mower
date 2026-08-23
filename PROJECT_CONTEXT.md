# Kontekst projektu dm2-mower

## Stan na 2026-08-23

Firmware loggera jest skompilowany i wgrany na klasyczny ESP32-WROOM-32D. Urządzenie łączy się z Wi-Fi, udostępnia panel pod `http://uart-logger.local/` oraz obsługuje aktualizację OTA.

Wersja 0.3 z ograniczonym terminalem DM2 została skompilowana i wgrana przez OTA 2026-08-23. Po restarcie endpoint terminala zgłosił stan rozbrojony, poprawną konfigurację CH1 115200 8N1 i TX na GPIO25.

Repozytorium jest częścią szerszego projektu **OpenDM2**, którego docelowym celem jest zachowanie fabrycznego głównego MCU, zabezpieczeń, ładowania i sterowników silników oraz dodanie Raspberry Pi jako komputera nawigacyjnego komunikującego się z głównym MCU przez UART.

Aktualnie działają:

- cztery wejścia RX z osobną nazwą, prędkością i formatem UART;
- podgląd HEX i ASCII na telefonie;
- kilkuminutowe nagrywanie bajtów w pamięci przeglądarki i eksport JSONL;
- ciągłe nagrywanie surowych zmian stanu czterech wejść z rozdzielczością 0,25 µs;
- liczniki luk rekordów, przepełnienia programowego CH4 i zgubionych zboczy;
- OTA przez stronę WWW i skrypt PowerShell.
- bezpieczny terminal DM2 na GPIO25, domyślnie rozbrojony, ograniczony do potwierdzonych komend odczytowych.
- dwa zapamiętywane profile Wi-Fi z przełącznikiem w panelu i zachowaniem awaryjnego AP.

## Ważna historia techniczna

Pierwsza wersja surowego przechwytywania używała RMT i ucinała każdą transmisję po dokładnie 128 odcinkach. Została zastąpiona ciągłymi buforami zboczy z przerwań GPIO. Aktualny format surowy ma wersję 2 i używa 32-bitowych czasów.

Niepodłączone wejścia są podciągnięte do stanu HIGH, aby nie generowały fałszywych przerwań. Panel przy pierwszym otwarciu pobiera tylko bieżący numer sekwencji, a następnie nowe rekordy, dzięki czemu nie przeciąża ESP starym buforem.

## Zweryfikowany test

Nadajnik testowy ESP32-C3 wysyła na GPIO4 ramki tekstowe i binarne w konfiguracji 9600 8N1. Logger poprawnie rozpoznał ze zboczy czas bitu około 104,2 µs, czyli około 9600 baud. Ostatni test surowy po świeżym otwarciu panelu zapisał 91 bloków i około 19,6 kB przy zerowej liczbie luk i zgubionych zboczy.

Kod nadajnika znajduje się w `simulator-c3/`.

## Potwierdzone odkrycia z POINT PORLMW1

- płyta główna: `DM2-MB-VB1.2`;
- główny MCU: GigaDevice, ARM Cortex-M4, 512 KiB Flash i 64 KiB SRAM;
- firmware: `DM2-SW-VBW 3.7.4`, aplikacja RT-Thread 4.0.0 z 23 grudnia 2021;
- zewnętrzna pamięć: Winbond W25Q32, 4 MiB;
- UART serwisowy głównego MCU: **115200, 8N1, TTL 3,3 V, bez flow control**;
- cold boot kończy się aktywnym promptem `finsh >`;
- bezpiecznie potwierdzone komendy tylko do odczytu to m.in. `help`, `version`, `list_device` i `ps`;
- firmware rejestruje urządzenia `uart1`–`uart5` oraz ma wbudowane komendy diagnostyczne FinSH.

Pierwszy zapis z kosiarki należy nadal wykonywać pasywnie: `DM2 TX -> wejście RX loggera` i wspólna masa, bez połączenia VCC oraz bez podłączania TX loggera do RX kosiarki.

## Potwierdzony tor sterowania napędem w firmware 3.7.4

Adresy dotyczą wyłącznie przeanalizowanego obrazu `DM2-SW-VBW 3.7.4` i nie mogą być przenoszone w ciemno na inne wersje:

- około `0x0804985C`: zapis celu w postaci dwóch wartości float odpowiadających `v` i `omega`;
- około `0x08035160`: ograniczenia i kinematyka różnicowa;
- około `0x080496C0`: zapis ograniczonych celów lewego i prawego koła;
- około `0x0803C91C`: okresowe przekazanie celów do silników jako ID 1 z odwróconym znakiem i ID 0 bez odwrócenia;
- około `0x08036748`: funkcja podobna do `motor_set_speed(id, speed)`, ograniczająca wartość do `-4500..4500`;
- `uart2` jest otwierany jako magistrala kontrolerów silników;
- ramki silników zaczynają się od `D5 E5` i w przeanalizowanej ścieżce mają 11 bajtów;
- komunikat wewnętrzny `0x0201` odpowiada zadawaniu prędkości (`CMD 02`);
- ID 0 i 1 odpowiadają kołom, a ID 3 jest praktycznie potwierdzonym kontrolerem noża.

Najlepszym przyszłym punktem integracji RPi jest wybór źródła `v/omega` przed fabryczną kinematyką, a nie bezpośrednie nadawanie na UART2. Odbiornik UART powinien jedynie aktualizować stan polecenia, natomiast ruch nadal ma wykonywać fabryczna okresowa pętla RT-Thread.

W trybie zewnętrznym brak poprawnego heartbeat przez maksymalnie 500 ms ma ustawiać `v=0`, `omega=0`, zatrzymywać robota i wymagać ponownego jawnego uzbrojenia. Nie wolno automatycznie wracać do fabrycznego koszenia. STOP, lift/tilt, bumper, przeciążenia, ładowanie i pozostałe zabezpieczenia fabryczne zawsze mają pierwszeństwo.

## Ważne dane NOR

- konfiguracja użytkownika ma `0x170` bajtów i jest przechowywana redundantnie przy `0x200000` i `0x201000`;
- pierwsze dwa bajty struktury to CRC16 obejmujące kolejne `0x16E` bajtów;
- PIN jest zapisany na offsetach struktury `+0x0A..+0x0D`;
- mapowanie znaków: `01=A`, `02=B`, `03=C`, `04=D`;
- licznik blokady jest `uint32 little-endian` przy `+0x150`;
- nie wolno zmieniać pojedynczych bajtów bez zachowania całego sektora 4 KiB, przeliczenia CRC i uwzględnienia obu kopii.

Golden dumpy W25Q32:

- unlocked, 4 194 304 B: `47541B17B3C9B6F20B5A6A72F7E8D43E2FBA326BEBB4FDE5B022521F67239EC3`;
- locked, 4 194 304 B: `32DDFF97BBD4DABD9A04276BBBEB494B195E84127972F5A11867B4CE705C3220`.

Samych dumpów firmware/NOR, UID urządzenia, danych Tuya i sekretów nie należy publikować w repozytorium.

## Następny etap

Podłączyć pasywnie linie TX płyty robota, nadać kanałom opisowe nazwy i wykonać równolegle:

1. zapis surowych zboczy do wykrycia prędkości i formatu;
2. zapis bajtów po ustawieniu najbardziej prawdopodobnych parametrów;
3. analizę powtarzalnych nagłówków, długości ramek, kierunków komunikacji i sum kontrolnych.

Najbliższy konkretny pomiar to pełny zapis cold boot UART-u głównego MCU przy 115200 8N1, a następnie sprawdzenie odpowiedzi na `Enter`, `help`, `version`, `list_device` i `ps` przez ograniczony terminal. Magistrale silników i czujników nadal przechwytujemy wyłącznie pasywnie podczas kontrolowanych zdarzeń.

## Zweryfikowana sesja FinSH 2026-08-23

- połączenie dwukierunkowe działa: GPIO16 odbiera TX kosiarki, GPIO25 przez rezystor nadaje do RX kosiarki;
- odebrano pełny cold boot RT-Thread i prompt `finsh >`;
- ciągłe nadawanie gubiło co drugi znak (`help` docierało jako `hp`), dlatego terminal wysyła znaki pojedynczo z odstępem 3 ms i kończy komendę pojedynczym `CR`;
- po tej poprawce polecenia docierają bezbłędnie;
- `list_device()` działa i potwierdziło urządzenia `uart1`–`uart5`, SPI flash/busy, RTC, key, PWM, ADC, LCD, IMU, watchdog i pin;
- `version()` działa i potwierdziło RT-Thread 4.0.0 build Dec 23 2021;
- `help` zwraca `Unknown symbol`, a `help()` oraz `ps()` zwracają `Null node` w tej kompilacji;
- po testach terminal został rozbrojony.

Pełny uporządkowany wynik inwentaryzacji wątków, timerów, urządzeń, IPC i pamięci znajduje się w `docs/finsh-diagnostics-2026-08-23.md`.

## Pliki lokalne i sekrety

`include/wifi_config.h`, `.pio/` oraz `tools/` nie są wersjonowane. Na nowym komputerze skopiuj `include/wifi_config.example.h` do `include/wifi_config.h` i wpisz dane Wi-Fi lokalnie. Nie umieszczaj haseł w Git.
