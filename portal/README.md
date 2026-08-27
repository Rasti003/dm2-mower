# MOWBI Command Deck

Portal Raspberry Pi dla projektu OpenDM2. Pierwszy moduł tworzy i przechowuje
zweryfikowane backupy pamięci głównego MCU przez CMSIS-DAP/SWD. Interfejs jest
responsywny i przygotowany pod przyszłą telemetrię UART, planowanie misji oraz
osobny, rygorystyczny Safety Gate sterowania.

## Granica bezpieczeństwa wersji 0.1

- backend dopuszcza tylko komendę pyOCD `savemem`;
- połączenie odbywa się w trybie `attach` — portal nie żąda resetu ani haltu;
- nie ma endpointu programowania, kasowania ani odtwarzania;
- backup jest zablokowany do czasu wpisania oznaczenia MCU z konkretnej płyty;
- każdy region jest odczytywany trzy razy w trzech osobnych sesjach;
- pliki są porównywane bajt po bajcie oraz przez SHA-256, BLAKE2b-256 i CRC32;
- niezgodny zestaw zostaje oznaczony jako błąd i nie otrzymuje pliku consensus;
- dumpy, UID-y, token portalu i manifesty urządzenia są przechowywane wyłącznie
  na Pi w `~/.local/share/mowbi/` i są ignorowane przez Git.

## Zakres backupu

Pierwszy aktywny region to wewnętrzny Flash MCU: `0x08000000`, 512 KiB. Ten
zakres wynika z dotychczasowego obrazu, ale przed pierwszym odczytem profil wymaga
potwierdzenia oznaczenia procesora z badanej płyty.

Zewnętrzny Winbond W25Q32 (4 MiB) i option bytes są pokazane jako wymagane, lecz
zablokowane. SWD nie gwarantuje bezpośredniego dostępu do pamięci SPI, a mapa
option bytes zależy od dokładnego modelu MCU. Portal nie oznaczy zestawu jako
pełnego backupu wszystkich pamięci trwałych, dopóki te regiony nie dostaną
zweryfikowanych metod odczytu.

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
