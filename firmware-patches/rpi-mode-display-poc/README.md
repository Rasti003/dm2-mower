# RPI MODE display proof of concept

This is a **display-only laboratory patch** for the exact DM2-SW-VBW 3.7.4
image with SHA-256:

`45823D14EC9BF15776AA9A50D859AD937CC9E39732E432403D55018DE4184C4A`

It does not add RPi motion commands and does not change the motor-control path.
After boot, the existing FinSH command `ui_msg_test()` sets an internal flag and
requests a UI redraw. The normal status text is then replaced with `RPI MODE`.
Rebooting clears the flag and restores stock display behaviour.

The patch is intentionally not uploaded automatically. `build_patch.py` only
creates a new binary file and refuses unknown input images or unexpected bytes.

## Reconstructed hooks

- `0x0805F1B8`: FinSH export pointer for the stock no-op `ui_msg_test` function;
- `0x080330BE`: localized status-string lookup in the stock UI renderer;
- `0x08033144`: helper that queues UI event 54 and requests a redraw;
- `0x08046BD6`: early application-init call wrapped to clear the new state word;
- `0x08046C08`: RT-Thread heap end, reduced by 32 bytes;
- `0x08060400`: start of previously erased Flash used for the payload;
- `0x2000FFE0..0x2000FFFF`: reserved state area, outside the reduced heap.

The stock application uses Flash only through `0x0806038F`; the remaining
130,160 bytes were erased (`0xFF`) in the analyzed image.

## Build

The script looks for the ARM GNU toolchain installed by PlatformIO under
`tools/pio-core/packages/toolchain-gccarmnoneeabi/bin`, or in `PATH`.

```powershell
python .\firmware-patches\rpi-mode-display-poc\build_patch.py `
  "C:\firmware\DM2-MCU1.bin" `
  "C:\firmware\DM2-MCU1-RPI-MODE-POC.bin"
```

Do not publish either input or output firmware. Before any SWD write, retain the
golden image, option bytes and a verified recovery procedure. The first hardware
test must be performed with the mower stationary and the blade disconnected.
