MEMORY
{
    FLASH (rx) : ORIGIN = 0x08060400, LENGTH = 0x200
}

SECTIONS
{
    .text :
    {
        KEEP(*(.text*))
        KEEP(*(.rodata*))
        . = ALIGN(4);
    } > FLASH

    /DISCARD/ :
    {
        *(.ARM.attributes)
        *(.comment)
        *(.data*)
        *(.bss*)
    }
}
