#ifndef _KEY_H
#define _KEY_H

#include "headfile.h"
#include "stm32f4xx_hal.h" 

typedef enum
{
	KEY_IDLE=0,
	KEY1,
	KEY2,
	KEY3,
	KEY4
}key_State_t;

typedef struct
{
	uint16_t pin;
	uint16_t last_tick;
	key_State_t state; 
}keyTypeDef;

void key_transmit(void);

#endif

