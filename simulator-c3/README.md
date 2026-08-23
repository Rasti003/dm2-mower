# ESP32-C3 OLED UART Toy

Generator danych testowych dla loggera UART z animacją na małym ekranie OLED.

## UART testowy

- TX: GPIO4
- prędkość: 9600 bit/s
- format: 8N1
- poziom: TTL 3,3 V

Połącz GPIO4 tej płytki przez rezystor 4,7 kΩ z wejściem loggera oraz połącz masy obu płytek. Program wysyła co sekundę ramkę tekstową, a co cztery ramki również 12-bajtowy pakiet binarny.

## OLED

Program automatycznie sprawdza adres `0x3C` na typowych parach pinów:

- SDA GPIO5, SCL GPIO6;
- SDA GPIO8, SCL GPIO9;
- oraz warianty z zamienionymi przewodami.

Po wykryciu wyświetla animowanego „UART Gremlina”, mruganie, ruch oczu i krótkie komunikaty.
