#ifndef _UART_DMA_H
#define _UART_DMA_H

#include "stm32g4xx.h"
#include "main.h"
#include "stdio.h"
#include "string.h"

#include "usart.h"

#define UART_RX_BUF_SIZE  1024

typedef struct
{
     uint8_t rx_buf[UART_RX_BUF_SIZE];
     volatile uint16_t rx_len;
     volatile uint16_t rx_complete;    //一帧数据接收完成
     uint16_t last_dma_pos;
}UART_DMA_Handdle_t;

extern UART_DMA_Handdle_t YiYuan;
extern UART_DMA_Handdle_t GPS;

void usart_start_DMA(void);
void UART_DMA_Process(UART_DMA_Handdle_t UART_RX);

#endif
