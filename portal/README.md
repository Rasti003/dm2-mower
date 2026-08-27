# MOWBI Command Deck

Portal Raspberry Pi dla projektu OpenDM2. Pierwszy moduł tworzy i przechowuje
zweryfikowane backupy pamięci głównego MCU przez CMSIS-DAP/SWD. Interfejs jest
responsywny i przygotowany pod przyszłą telemetrię UART, planowanie misji oraz
osobny, rygorystyczny Safety Gate sterowania.

## Granica bezpieczeństwa wersji 0.1

- kod wersji 0.1 dopuszcza tylko komendę pyOCD `savemem`;
- połączenie odbywa się w trybie `attach` — portal nie żąda resetu ani haltu;
- nie ma endpointu programowania, kasowania ani odtwarzania;
- backup jest zablokowany do czasu wpisania oznaczenia MCU z konkretnej płyty;
- każdy region jest odczytywany trzy razy w trzech osobnych sesjach;
- pliki są porównywane bajt po bajcie oraz przez SHA-256, BLAKE2b-256 i CRC32;
- niezgodny zestaw zostaje oznaczony jako błąd i nie otrzymuje pliku consensus;
- dumpy, UID-y, token portalu i manifesty urządzenia są przechowywane wyłącznie
  na Pi w `~/.local/share/mowbi/` i są ignorowane przez Git.

Klon CMSIS-DAP `c251:f001` nie działa stabilnie z pyOCD. Pierwszy rzeczywisty
backup wykonano bezpiecznie przez OpenOCD z `cmsis-dap backend hid`, w trybie
attach i przy 100 kHz. Pakiet został ręcznie zarejestrowany w magazynie portalu.
Przed uruchamianiem kolejnych backupów z przycisku backend aplikacji należy
przenieść z pyOCD na zweryfikowaną metodę OpenOCD.

## Zakres backupu

Potwierdzony MCU należy do rodziny GD32F30x: 512 KiB Flash i 64 KiB SRAM.
Najbardziej prawdopodobna jest klasa GD32F303xE; dokładny wariant obudowy wymaga
odczytania pełnego napisu z układu. Potwierdzone regiony backupu MCU to:

- wewnętrzny Flash: `0x08000000`, 512 KiB;
- option bytes: `0x1FFFF800`, 16 B;
- fabryczny bootloader: `0x1FFFF000`, 2 KiB (referencyjny, nieprogramowalny);
- gęstość pamięci i UID: od `0x1FFFF7E0` (fabryczne, nieklonowalne);
- Product ID: `0x40022100` (fabryczny, tylko do identyfikacji).

Option bytes zostały odczytane trzy razy i są zgodne. Kod bezpieczeństwa `0xA5`
oznacza brak ochrony odczytu; wszystkie pary bajt/dopełnienie są poprawne.

Zewnętrzny Winbond W25Q32 został odczytany programatorem w trzech identycznych
próbach `LOCK1`–`LOCK3`. Golden obraz ma SHA-256
`32DDFF97BBD4DABD9A04276BBBEB494B195E84127972F5A11867B4CE705C3220`.
Pełna paczka `20260827-170000-full-board-recovery` łączy zweryfikowany backup MCU
z tym obrazem i jest oznaczona w portalu jako kompletny backup pamięci trwałych
płyty. Zestaw `UNLOCK4`–`UNLOCK6` jest innym wariantem i nie należy go mieszać z
golden backupem LOCK.

RAM jest celowo pominięty w golden backupie: jego zawartość jest ulotna i nie
służy do odtworzenia urządzenia.

## Instalacja na Raspberry Pi

Wymagane są Python 3, `python3-venv`, działający pyOCD oraz widoczna sonda
CMSIS-DAP. Z katalogu repozytorium:

```sh
sh portal/scripts/install-user-service.sh
```

Skrypt tworzy osobne środowisko `~/.venvs/mowbi-portal`, losowy klucz dostępu,
lokalny magazyn danych i usługę użytkownika `mowbi-portal.service`. Klucz jest
drukowany tylko przy pierwszej instalacji i zapisany z uprawnieniami `0600` w
`~/.config/mowbi/portal.env`.

Portal jest dostępny pod `http://mowbi-wan.local:8080/` albo pod adresem IP Pi.

Stan usługi:

```sh
systemctl --user status mowbi-portal.service
journalctl --user -u mowbi-portal.service -n 100 --no-pager
```

Uruchamianie usługi użytkownika od razu po starcie, bez wcześniejszego logowania,
wymaga jednorazowo:

```sh
sudo loginctl enable-linger pi
```

## Struktura archiwum

Każdy katalog backupu zawiera:

- `internal_flash-read-01.bin` … `03.bin` — niezależne surowe odczyty;
- `internal_flash.bin` — kopię consensus, tylko gdy wszystkie odczyty są zgodne;
- `manifest.json` — profil, zakresy, narzędzia, sumy i deklaracja operacji;
- odpowiadający plik ZIP do pobrania przez panel.

Manifest używa schematu `mowbi-backup/v1`. Przycisk „Sprawdź” ponownie przelicza
sumy wszystkich plików na dysku i porównuje je z manifestem.

## Testy

```sh
cd portal
PYTHONPATH=. python3 -m unittest discover -s tests -v
```
