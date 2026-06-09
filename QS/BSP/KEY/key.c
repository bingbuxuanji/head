#include "key.h"

#define KEY_DEBOUNCE_MS 30

key_State_t KEY_STATE;
static volatile uint32_t last_key_tick=0;
keyTypeDef key[4]=
{
	{GPIO_PIN_4,0,KEY_IDLE},
	{GPIO_PIN_5,0,KEY_IDLE},
	{GPIO_PIN_6,0,KEY_IDLE},
	{GPIO_PIN_7,0,KEY_IDLE}
};

void HAL_GPIO_EXTI_Callback(uint16_t GPIO_Pin)
{
	uint32_t current_tick=HAL_GetTick();
	for(int i=0;i<4;i++)
	{
		if(GPIO_Pin==key[i].pin)
		{
			if((current_tick-key[i].last_tick)>KEY_DEBOUNCE_MS)
			{
				key[i].last_tick=current_tick;
				if(HAL_GPIO_ReadPin(GPIOF, key[i].pin) == GPIO_PIN_RESET)
                {
                    key[i].state = (key_State_t)(i + 1);
                }
			}
			break;
		}
		
	}
}

void key_transmit(void)
{
	for(uint8_t i = 0; i < 4; i++)
    {
        if(key[i].state != KEY_IDLE)
        {
            switch(key[i].state)
            {
                case KEY1:
                    printf("b1\r\n");
                    break;
                case KEY2:
                    printf("b2\r\n");
                    break;
                case KEY3:
                    printf("b3\r\n");
                    break;
                case KEY4:
                    printf("b4\r\n");
                    break;
                default:
                    break;
            }
            key[i].state = KEY_IDLE; 
        }
    }
}



