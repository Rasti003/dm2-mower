.syntax unified
.cpu cortex-m4
.thumb

.equ RPI_MODE_FLAG, 0x2000FFE0
.equ UI_REQUEST_REDRAW, 0x08033144
.equ STOCK_INIT_CONTINUATION, 0x0804D79C

.section .text
.align 2

.global rpi_mode_command
.type rpi_mode_command, %function
.thumb_func
rpi_mode_command:
    push    {r4, lr}
    ldr     r1, =RPI_MODE_FLAG
    movs    r0, #1
    str     r0, [r1]
    bl      UI_REQUEST_REDRAW
    movs    r0, #0
    pop     {r4, pc}
.size rpi_mode_command, . - rpi_mode_command

.global rpi_select_status_text
.type rpi_select_status_text, %function
.thumb_func
rpi_select_status_text:
    /* Instruction replaced at 0x080330BE. */
    ldr.w   r0, [r1, r5, lsl #2]
    ldr     r2, =RPI_MODE_FLAG
    ldr     r2, [r2]
    cmp     r2, #1
    bne     1f
    ldr     r0, =rpi_mode_text
1:
    bx      lr
.size rpi_select_status_text, . - rpi_select_status_text

.global rpi_init_wrapper
.type rpi_init_wrapper, %function
.thumb_func
rpi_init_wrapper:
    ldr     r0, =RPI_MODE_FLAG
    movs    r1, #0
    str     r1, [r0]
    b.w     STOCK_INIT_CONTINUATION
.size rpi_init_wrapper, . - rpi_init_wrapper

.align 2
rpi_mode_text:
    .asciz  "RPI MODE"

.ltorg
