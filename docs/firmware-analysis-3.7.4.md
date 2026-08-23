# Analiza firmware DM2-SW-VBW 3.7.4

Data analizy: 2026-08-23. Analizowany plik ma 524 288 bajtów i SHA-256
`45823D14EC9BF15776AA9A50D859AD937CC9E39732E432403D55018DE4184C4A`.
Wszystkie adresy w tym dokumencie dotyczą wyłącznie tego obrazu. Analiza była
statyczna i nie zmieniła ani nie uruchomiła firmware kosiarki.

## Najważniejszy wniosek

Do wdrożenia własnego sterowania jazdą nie są niezbędne UART-y mniejszych MCU.
Główny firmware zawiera kompletny tor od celu ruchu `v/omega`, przez fabryczne
ograniczenia i kinematykę, do poleceń dla kontrolerów kół. Bezpieczniejszy kierunek
to dodanie nowego źródła `v/omega` w głównym MCU i pozostawienie fabrycznej pętli
oraz magistrali silników bez zmian.

## Fakty potwierdzone w kodzie

### Obraz i pamięć

- bootloader zaczyna się od `0x08000000`;
- aplikacja ma tablicę wektorów przy `0x0800A000`, SP `0x2000B620` i reset
  `0x0800A251`;
- inicjalizowane dane RAM są kompresowane mechanizmem Keil scatter-loading;
- trzy przekazane zrzuty MCU1/MCU2/MCU3 były identyczne bit w bit, więc nie są
  osobnymi firmware sterowników silników.

### UART-y głównego MCU

Wszystkie pięć urządzeń skonfigurowano jako 115200, 8N1:

| RT-Thread | Peryferium | TX | RX | Potwierdzona rola |
|---|---|---|---|---|
| `uart1` | USART1 | PA9 | PA10 | wyjście konsoli RT-Thread i logów |
| `uart2` | USART2 | PA2 | PA3 | magistrala kontrolerów silników |
| `uart3` | USART3 | PB10 | PB11 | jeszcze nieustalona |
| `uart4` | UART4 | PC10 | PC11 | jeszcze nieustalona |
| `uart5` | UART5 | PC12 | PD2 | wejście powłoki FinSH |

Konsola serwisowa jest logicznie rozdzielona: tekst wychodzi przez `uart1`/PA9,
a FinSH odbiera polecenia przez `uart5`/PD2. To wyjaśnia działające połączenie
serwisowe, mimo że nie jest ono jednym klasycznym dwukierunkowym UART-em.
Fizyczne numery wyprowadzeń obudowy wymagają dokładnego symbolu MCU i wariantu
obudowy; nazw portów PA2/PA3 nie należy zamieniać na numer nóżki na oko.

### Magistrala silników

- `uart2` jest otwierany w module silników;
- ramka nadawcza ma 11 bajtów i nagłówek `D5 E5`;
- bajt 2 to ID kontrolera, bajty 3 i 5 przenoszą dwie części 16-bitowego licznika,
  bajt 4 to komenda, a bajt 6 to suma kontrolna;
- suma kontrolna:

  `checksum = (b2 + b3 + b4 + b5 + b7 + b8 + b9 + b10) & 0x7F`;

- komenda prędkości ma kod `0x02`;
- prędkość jest ograniczana do `-4500..4500`, zapisywana jako signed int16
  big-endian: starszy bajt w `b7`, młodszy w `b9`, przy `b8=b10=0`;
- ID 0 i 1 są kołami; okresowa wysyłka odwraca znak celu dla ID 1;
- ID 3 odpowiada sterownikowi noża z bardzo wysoką pewnością.

### Fabryczny tor jazdy

- `0x0804985C`: centralny zapis dwóch wartości float odpowiadających `v` i
  `omega` do stanu sterowania;
- `0x08035160`: fabryczne limity zależne od trybu i kinematyka różnicowa;
- `0x080496C0`: ograniczenie i zapis celu lewego/prawego koła do `-4500..4500`;
- `0x0803C91C`: okresowe przekazanie celów do kontrolerów kół;
- `0x08036748`: ograniczenie pojedynczej komendy silnika;
- `0x0804DAE8`: bramka wysyłki zależna od globalnego stanu włączenia.

Ponieważ wiele fabrycznych modułów wywołuje centralny setter, podmienianie
wszystkich jego wywołań byłoby kruche. Integracja powinna dodać jawny wybór
źródła polecenia przed kinematyką albo tuż przy stanie celu, zachowując dalszą
fabryczną ścieżkę.

## Silne wnioski, jeszcze do potwierdzenia dynamicznego

- Najlepszym interfejsem Raspberry Pi będzie osobny protokół poleceń `v/omega`,
  heartbeat, uzbrojenie/rozbrojenie i telemetria, a nie emulowanie ramek UART2.
- Globalna bramka wysyłki przy `0x20000018` jest jednym z elementów zezwolenia
  na napęd, lecz przed jej użyciem trzeba odtworzyć wszystkich zapisujących ją
  użytkowników oraz zależność od stanów bezpieczeństwa.
- `uart3` i `uart4` prawdopodobnie obsługują dodatkowe moduły komunikacyjne lub
  peryferia, ale obecne dowody nie wystarczają do przypisania konkretnych ról.

## Niewiadome blokujące bezpieczną modyfikację

1. Pełna lista warunków STOP: lift/tilt, bumper, przeciążenie, zanik łączności z
   kontrolerem, ładowanie i inne błędy.
2. Wszyscy autorzy globalnej flagi zezwolenia na napęd oraz momenty jej zmiany.
3. Jednostki i znaki `v/omega`, skala wheel target oraz zachowanie w każdym trybie.
4. Odpowiedzi i heartbeat kontrolerów silników na UART2.
5. Dokładna rola `uart3`/`uart4` i możliwość przeznaczenia jednego z nich na RPi
   bez kolizji z fabrycznym osprzętem.
6. Mechanizm weryfikacji obrazu przy starcie, mapa wolnego flash/RAM i bezpieczna
   metoda powrotu do oryginalnego firmware.

## Proponowany dalszy plan

1. Dokończyć statyczny graf zapisów do flag napędu i warunków zatrzymania.
2. Pasywnie nagrać UART2 podczas: startu, jazdy prosto, skrętu, STOP, uniesienia,
   zderzaka, błędu i wyłączenia noża. Nie podawać sygnału na magistralę.
3. Powiązać ramki odpowiedzi z warunkami i potwierdzić licznik oraz timeouty.
4. Wybrać wolny UART głównego MCU albo osobny bezpieczny interfejs dla RPi.
5. Zaprojektować bramkę źródła poleceń z heartbeat maksymalnie 500 ms. Timeout ma
   wymuszać `v=0`, `omega=0`, rozbrojenie i ręczne ponowne uzbrojenie; nie może
   automatycznie wracać do fabrycznego koszenia.
6. Najpierw wykonać wariant laboratoryjny z kołami uniesionymi i fizycznym STOP,
   dopiero po testach wszystkich zabezpieczeń rozważać próbę na ziemi.

## Odtwarzalność

Skrypt `scripts/analyze_dm2_firmware.py` sprawdza rozmiar i SHA-256, odtwarza
inicjalizowane dane RAM, weryfikuje struktury pięciu UART-ów oraz pokazuje
analityczny przykład ramki prędkości. Nie otwiera portów szeregowych i nie zapisuje
do obrazu firmware.

## Wyświetlacz i pierwszy wskaźnik trybu RPi

Firmware zawiera eksport FinSH `ui_msg_test`, ale funkcja pod adresem
`0x0804CCE8` jest pustym stubem `bx lr`. Można więc zastąpić jej wskaźnik w
tablicy eksportów własną funkcją bez odbierania działającej diagnostyki.

Główny napis stanu (`Standby`, `Mowing`, `Charging` itd.) jest wybierany z tabeli
14 wersji językowych zaczynającej się przy `0x080518A8`. Renderer przy
`0x08033094` wybiera stan i język, a następnie używa wspólnych funkcji rysowania
tekstu. Oznacza to, że napis `RPI MODE` można wprowadzić jako warunkowy zamiennik
tekstu, bez implementowania sterownika LCD ani modyfikowania wszystkich języków.

Funkcja przy `0x08033144` wysyła do UI zdarzenie 54, które powoduje odrysowanie
ekranu głównego. Przygotowany POC wykorzystuje `ui_msg_test()` do ustawienia flagi,
wysłania tego zdarzenia i pokazania `RPI MODE`. Patch nie dotyka toru napędu.

Obraz wykorzystuje Flash do `0x0806038F`; od `0x08060390` do końca 512 KiB jest
130 160 bajtów `0xFF`. RT-Thread inicjalizuje stertę jako
`0x2000B620..0x20010000`; POC zmniejsza jej koniec o 32 bajty i używa
`0x2000FFE0..0x2000FFFF` na własny stan. Bootloader przy zwykłym starcie sprawdza
wektor SP/PC aplikacji, natomiast komunikat o checksum dotyczy ścieżki aktualizacji
pliku. Pierwszy test zmodyfikowanego obrazu nadal powinien używać SWD i gotowej
procedury przywrócenia golden dumpu.

Uruchomienie:

```powershell
python .\scripts\analyze_dm2_firmware.py "C:\firmware\DM2-MCU1.bin"
```
