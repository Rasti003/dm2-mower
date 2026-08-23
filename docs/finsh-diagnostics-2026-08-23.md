# Diagnostyka FinSH POINT PORLMW1 — 2026-08-23

Odczyt wykonano przez ESP32 UART Logger 0.3, dwukierunkowo przez konsolę głównego MCU: 115200 8N1, GPIO16 RX, GPIO25 TX przez rezystor szeregowy. Wszystkie użyte funkcje były diagnostyczne i tylko do odczytu. Po sesji terminal rozbrojono.

## Potwierdzenie konsoli

- cold boot: RT-Thread 4.0.0, build Dec 23 2021;
- prompt: `finsh >`;
- `version()` działa;
- `list_device()` działa;
- nadajnik wymaga odstępu około 3 ms pomiędzy znakami; bez odstępu DM2 gubiło co drugi znak;
- polecenia są kończone pojedynczym `CR`.

## Wątki — `list_thread()`

| Wątek | Priorytet | Stan podczas odczytu | Stos | Maks. użycie | Lewy tick |
|---|---:|---|---:|---:|---:|
| `tshell` | 20 | running | `0x1000` | 16% | `0x09` |
| `tidle0` | 31 | ready | `0x0100` | 57% | `0x02` |
| `app` | 10 | suspend | `0x0400` | 32% | `0x01` |
| `upgrade` | 11 | suspend | `0x0800` | 14% | `0x01` |
| `business` | 7 | suspend | `0x0400` | 21% | `0x04` |
| `motion` | 6 | suspend | `0x0400` | 28% | `0x03` |
| `rtc` | 12 | suspend | `0x0400` | 15% | `0x04` |
| `Updata` | 5 | suspend | `0x0400` | 27% | `0x04` |
| `MOTOR` | 2 | suspend | `0x0600` | 13% | `0x02` |
| `Ui` | 9 | suspend | `0x0800` | 25% | `0x12` |
| `navigation` | 1 | suspend | `0x0600` | 35% | `0x05` |
| `SystemStatus` | 8 | suspend | `0x0400` | 24% | `0x05` |

Priorytety sugerują, że `navigation` (1) i `MOTOR` (2) należą do najbardziej priorytetowych zadań aplikacyjnych. Stan `suspend` oznaczał oczekiwanie/uśpienie w chwili diagnostyki, nie wyłączenie zadania.

## Timery — `list_timer()`

### Timery powiązane z wątkami

| Nazwa | Okres w tickach | Stan |
|---|---:|---|
| `MOTOR` | 4 | activated |
| `app` | 10 | activated |
| `Updata` | 10 | activated |
| `navigation` | 10 | activated |
| `SystemStatus` | 10 | activated |
| `business` | 20 | activated |
| `motion` | 60 | activated |
| `Ui` | 60 | activated |
| `upgrade` | 1000 | activated |
| `rtc` | 1000 | activated |

W chwili odczytu `current tick` wynosił `0x6DE8` około 28 sekund po uruchomieniu, co bardzo mocno wskazuje na tick RT-Thread równy 1 ms. Jeżeli to potwierdzimy, okresy wynoszą odpowiednio: MOTOR 4 ms (250 Hz), navigation/app/SystemStatus/Updata 10 ms (100 Hz), business 20 ms (50 Hz), motion/UI 60 ms, rtc/upgrade 1000 ms.

### Pozostałe timery

Aktywne: `tim07` z okresem `0x1F4` = 500 ticków oraz `tim09` z okresem `0x1D4C0` = 120000 ticków. Pozostałe `tim00`–`tim04` i `tim11`–`tim14` były nieaktywne podczas odczytu.

## Urządzenia — `list_device()`

Potwierdzone urządzenia RT-Thread:

- `uart1`, `uart2`, `uart3`, `uart4`, `uart5` — Character Device;
- `spi_flash` — Block Device;
- `spi_dev`, `imu` — SPI Device;
- `spi_bus`, `spi_bus_2` — SPI Bus;
- `rtc` — RTC;
- `key`, `pwm`, `adc`, `wdg`, `pin` — Miscellaneous Device;
- `mn_lcd` — Graphic Device.

`uart1` miał refcount 2, pozostałe UART-y refcount 1. To wspiera identyfikację `uart1` jako aktywnej konsoli, natomiast analiza firmware wcześniej wskazała `uart2` jako magistralę kontrolerów silników.

## Obiekty IPC i pamięć

- `list_msgqueue()`: brak nazwanych kolejek w globalnej liście;
- `list_mailbox()`: `mm_mailbox`, entry 0, size 1;
- `list_event()`: brak nazwanych eventów w globalnej liście;
- `list_mutex()`: `spi_dev`, `spi_bus_2`, `fslock`, `spi_bus`; wszystkie bez właściciela w chwili odczytu;
- `list_sem()`: `sem00`–`sem14` miały wartość 1; `shrx` wartość 0; `heap` wartość 1;
- `list_mempool()`: brak nazwanych pul;
- `list_mem()`: total 18888 B, used 10284 B, maximum allocated 12496 B.

Wynik `list_mem()` najpewniej dotyczy sterty zarządzanej przez RT-Thread, a nie całych 64 KiB SRAM MCU.

## Niedostępne symbole

- `help` → `Unknown symbol`;
- `help()` → `Null node`;
- `ps()` → `Null node`;
- `list_fd()` → `Null node`;
- `free()` → `Null node`;
- `time()` → `Null node`.

Ich stringi mogą znajdować się w obrazie firmware, ale nie są aktywnymi eksportami FinSH w tej konfiguracji albo wymagają innego środowiska/składni.

## Najważniejsze wnioski dla OpenDM2

1. Oryginalny system ma wyraźnie rozdzielone zadania `navigation`, `MOTOR`, `motion` i `SystemStatus`.
2. `navigation` oraz `MOTOR` mają najwyższe priorytety aplikacyjne, więc odbiornik RPi nie powinien wykonywać sterowania bezpośrednio ani zaburzać ich czasu.
3. Najlepsza architektura pozostaje bez zmian: task UART RPi aktualizuje tylko stan `v/omega`, timestamp heartbeat i tryb; stockowy task nawigacji/napędu konsumuje ten stan.
4. Potencjalny cykl MOTOR 4 ms i navigation 10 ms daje podstawę do projektu protokołu RPi 10–20 Hz z watchdogiem <=500 ms, bez potrzeby wysyłania komend w tempie wewnętrznej pętli.
5. Następny pasywny pomiar powinien skorelować aktywność UART2 z cyklem `MOTOR` i z kontrolowanymi zdarzeniami robota.
