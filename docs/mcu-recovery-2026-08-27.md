# Pakiet odzyskiwania głównego MCU — 2026-08-27

## Wynik

Pakiet `20260827-164500-mcu-recovery` zawiera komplet danych programowalnych
potrzebnych do odtworzenia tego samego głównego MCU DM2. Wszystkie regiony
odczytano trzy razy przez SWD przy 100 kHz. Każda trójka jest identyczna bajt w
bajt, a MCU nie był zatrzymywany, resetowany, odblokowywany ani zapisywany.

Archiwum jest przechowywane poza Git:

- Raspberry Pi: `~/.local/share/mowbi/backups/20260827-164500-mcu-recovery.zip`;
- komputer serwisowy: `E:\Kosiarka\backups\20260827-164500-mcu-recovery.zip`.

SHA-256 archiwum:

`80629003EB1DDE77555F4218BF5BA8089D9745CCEB058FFFBE7F596D6CB7301C`

## Identyfikacja MCU

- rodzina: GD32F30x;
- prawdopodobna klasa: GD32F303xE (pełny symbol obudowy niepotwierdzony);
- Cortex-M4 CPUID: `0x410FC241`;
- DBG ID: `0x17010414`, Device ID `0x414`;
- Product ID: `0x46455A33`;
- rejestr gęstości: `0x00400200` = 512 KiB Flash i 64 KiB SRAM;
- DPIDR: `0x2BA01477`;
- firmware Flash SHA-256:
  `45823D14EC9BF15776AA9A50D859AD937CC9E39732E432403D55018DE4184C4A`.

## Zabezpieczone regiony

| Region | Adres | Rozmiar | Rola przy odzyskiwaniu |
|---|---:|---:|---|
| Internal Flash | `0x08000000` | 512 KiB | Programowalny, wymagany |
| Option bytes | `0x1FFFF800` | 16 B | Programowalne, wymagane |
| System bootloader | `0x1FFFF000` | 2 KiB | Fabryczny, tylko referencja |
| Electronic signature | `0x1FFFF7E0` | 20 B | Gęstość i UID, nieklonowalne |
| Product ID | `0x40022100` | 4 B | Fabryczna identyfikacja |
| Loaded option state | `0x4002201C` | 4 B | Kontrola interpretacji opcji |

Option bytes mają postać:

`A5 5A FF 00 FF 00 FF 00 FF 00 FF 00 FF 00 FF 00`

`0xA5` oznacza brak ochrony odczytu. Wszystkie pary wartości i dopełnienia są
poprawne, a bity ochrony zapisu są nieaktywne. Załadowany stan kontrolera
`0x03FFFFFC` potwierdza brak błędu option bytes.

## Granice odzyskiwania

Na tym etapie kompletne są dane potrzebne do odtworzenia tego samego MCU:
wewnętrzny Flash i option bytes. Fabryczny bootloader, UID oraz Product ID są
zachowane referencyjnie, ale nie powinny i zwykle nie mogą być programowane.

Przed pierwszym rzeczywistym odtworzeniem trzeba:

1. odczytać pełne oznaczenie z obudowy i dobrać dokładnie kompatybilny wariant;
2. przygotować stabilne zasilanie oraz podłączyć SWDIO, SWCLK, GND i NRST;
3. przetestować procedurę najpierw na zapasowym MCU lub bliźniaczej płycie;
4. zaprogramować Flash i zweryfikować go bajt w bajt przed zmianą option bytes;
5. option bytes programować na końcu i ponownie sprawdzić ich stan po resecie.

Nie wolno używać niezweryfikowanej procedury zapisu na jedynej działającej
płycie. Pakiet zawiera dane, ale procedura zapisu nie została jeszcze przetestowana.

## Czego nadal brakuje do kopii całej płyty

Brak zewnętrznej pamięci został uzupełniony z odczytów wykonanych programatorem.
Pliki `LOCK1.bin`, `LOCK2.bin` i `LOCK3.bin` mają po 4 MiB i są identyczne bajt w
bajt. Golden obraz W25Q32 ma SHA-256:

`32DDFF97BBD4DABD9A04276BBBEB494B195E84127972F5A11867B4CE705C3220`

Powstała pełna paczka:

- identyfikator: `20260827-170000-full-board-recovery`;
- komputer serwisowy:
  `E:\Kosiarka\backups\20260827-170000-full-board-recovery.zip`;
- Raspberry Pi:
  `~/.local/share/mowbi/backups/20260827-170000-full-board-recovery.zip`;
- SHA-256 archiwum:
  `D9A725E80046C5A568FEC08C1F65B1C7B6C9EA0179EFA59FB86BD7FB2025CAFF`.

Manifest zawiera 21 zweryfikowanych odczytów, ma
`complete_controller_board_backup=true` i nie ma oczekujących regionów. Jest to
komplet danych pamięci trwałych głównego MCU oraz W25Q32.

Pliki `UNLOCK4.bin`, `UNLOCK5.bin` i `UNLOCK6.bin` również są zgodne między sobą,
ale różnią się od zestawu LOCK. Użytkownik wskazał LOCK1–LOCK3 jako golden
backup, dlatego wariant UNLOCK nie został dodany do paczki i musi pozostać
oddzielnym materiałem porównawczym.

Nadal nie została wykonana próba zapisu/odtworzenia. Przed pierwszym odtworzeniem
trzeba potwierdzić pełne oznaczenie MCU i sprawdzić procedurę na zapasowym
układzie lub bliźniaczej płycie.
