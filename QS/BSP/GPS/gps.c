#include "gps.h"
#include "stdio.h"
#include "string.h"
#include "stdlib.h"
#include "./OLED/oled.h"

uint8_t rx_buffer[GPS_DMA_BUF_SIZE];
GPS_Data_Typedef GPS_DATA;
float GPS_DUG[4][2]={
	{103.985881,30.818524},
	{103.985833,30.818407},
	{103.985829,30.818403},
	{103.985469,30.81852}
};
uint8_t get_gps_flag_buf[256];
volatile uint8_t nav_text_ready = 0;
char nav_text_buf[256];
/* ��ʼ��GPS���� */
void GPS_Init(void)
{
    memset(&GPS_DATA, 0, sizeof(GPS_Data_Typedef));
    HAL_UARTEx_ReceiveToIdle_DMA(&GPS_UART_HANDLE, rx_buffer, sizeof(rx_buffer));
}

/* �ȷָ�ʽתʮ���� */
static float DM_To_DD(float dm, char dir)
{
    int deg = (int)(dm / 100);
    float min = dm - deg * 100;
    float dd = deg + min / 60.0f;
    
    if (dir == 'S' || dir == 'W') {
        dd = -dd;
    }
    return dd;
}

/* ������γ������ */
void GPS_Parse_Data(char *buf)
{
    char *gga_line;
    char line_copy[128];
    char *token;
    int i;
    float raw_lat = 0, raw_lon = 0;
    char lat_dir = 'N', lon_dir = 'E';
    
    // �ҵ� GGA ��
    gga_line = strstr(buf, "$GNGGA");
    if (!gga_line) gga_line = strstr(buf, "$GPGGA");
    if (!gga_line) return;
    
    // ��ȡ����
    char *end = strchr(gga_line, '\n');
    int len = end ? (end - gga_line) : strlen(gga_line);
    if (len >= sizeof(line_copy)) len = sizeof(line_copy) - 1;
    
    memcpy(line_copy, gga_line, len);
    line_copy[len] = '\0';
    
    // ȥ�����з�
    for (i = strlen(line_copy) - 1; i >= 0 && (line_copy[i] == '\r' || line_copy[i] == '\n'); i--) {
        line_copy[i] = '\0';
    }
    
    // �����ֶ�
    token = strtok(line_copy, ",");
    for (i = 0; i < 10 && token != NULL; i++)
    {
        switch(i)
        {
            case 2:  // γ��
                if (strlen(token) > 0) raw_lat = atof(token);
                break;
            case 3:  // N/S
                if (strlen(token) > 0) lat_dir = token[0];
                break;
            case 4:  // ����
                if (strlen(token) > 0) raw_lon = atof(token);
                break;
            case 5:  // E/W
                if (strlen(token) > 0) lon_dir = token[0];
                break;
            case 6:  // ��λ״̬
                if (strlen(token) > 0) {
                    GPS_DATA.valid = (atoi(token) == 1 || atoi(token) == 2);
                }
                break;
        }
        token = strtok(NULL, ",");
    }
    
    // ת��Ϊʮ����
    if (raw_lat != 0) GPS_DATA.latitude = DM_To_DD(raw_lat, lat_dir);
    if (raw_lon != 0) GPS_DATA.longitude = DM_To_DD(raw_lon, lon_dir);
}
uint8_t count=0;
/* DMA������ɻص� */
void HAL_UARTEx_RxEventCallback(UART_HandleTypeDef *huart, uint16_t Size)
{
    char temp_buf[256];
    uint16_t copy_len = Size < sizeof(temp_buf)-1 ? Size : sizeof(temp_buf)-1;
    
    memcpy(temp_buf, rx_buffer, copy_len);
    temp_buf[copy_len] = '\0';
    
    HAL_UARTEx_ReceiveToIdle_DMA(&GPS_UART_HANDLE, rx_buffer, sizeof(rx_buffer));
    
    GPS_Parse_Data(temp_buf);
	char tx_gps_buf[32];
	if(huart->Instance==USART2)
        {
            if (Size > 1 && get_gps_flag_buf[0] == 't')
            {
                uint16_t len = (Size - 1) < 255 ? (Size - 1) : 255;
                memcpy(nav_text_buf, (char *)&get_gps_flag_buf[1], len);
                nav_text_buf[len] = '\0';
                nav_text_ready = 1;
            }
            else if (Size > 0 && get_gps_flag_buf[0] == 'g')
            {
                count++;
                if(count>=3) count=3;
                sprintf(tx_gps_buf, "g%.6f,%.6f\r\n",
                        GPS_DUG[count][0], GPS_DUG[count][1]);
                HAL_UART_Transmit(&huart2, (uint8_t*)tx_gps_buf, strlen(tx_gps_buf), 100);
            }

            memset(get_gps_flag_buf, 0, sizeof(get_gps_flag_buf));
            HAL_UARTEx_ReceiveToIdle_DMA(&huart2, get_gps_flag_buf, sizeof(get_gps_flag_buf));
        }
}

/* ��ȡ������Ч�� */
uint8_t GPS_Is_Valid(void)
{
    return GPS_DATA.valid;
}

/* ��ȡγ�� */
float GPS_Get_Latitude(void)
{
    return GPS_DATA.latitude;
}

/* ��ȡ���� */
float GPS_Get_Longitude(void)
{
    return GPS_DATA.longitude;
}

