#include "uart_DMA.h"

UART_DMA_Handdle_t YiYuan;
UART_DMA_Handdle_t GPS;

void usart_start_DMA(void)
{
    memset(&GPS, 0, sizeof(UART_DMA_Handdle_t));
    HAL_UART_Receive_DMA(&huart1,GPS.rx_buf,UART_RX_BUF_SIZE);
    __HAL_UART_ENABLE_IT(&huart1,UART_IT_IDLE);
    memset(&YiYuan, 0, sizeof(UART_DMA_Handdle_t));
    HAL_UART_Receive_DMA(&huart2,YiYuan.rx_buf,UART_RX_BUF_SIZE);
    __HAL_UART_ENABLE_IT(&huart2,UART_IT_IDLE);
}

void UART_DMA_Process(UART_DMA_Handdle_t UART_RX)
{
   if (UART_RX.rx_complete)
   {
       // 关闭中断，这里只关闭总中断，后续在开发中可修改
       __disable_irq();
       uint16_t len = UART_RX.rx_len;
       uint16_t start = (UART_RX.last_dma_pos - len) % UART_RX_BUF_SIZE;
       uint8_t temp_buffer[UART_RX_BUF_SIZE]; // 临时缓冲区，确保足够大
       if (start + len <= UART_RX_BUF_SIZE)
           memcpy(temp_buffer, &UART_RX.rx_buf[start], len);
       else
       {
           // 环形折返
           uint16_t first = UART_RX_BUF_SIZE - start;
           memcpy(temp_buffer, &UART_RX.rx_buf[start], first);
           memcpy(temp_buffer + first, UART_RX.rx_buf, len - first);
       }
       UART_RX.rx_complete = 0;
       __enable_irq();
   }
}
