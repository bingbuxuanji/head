#ifndef _GPS_H
#define _GPS_H

#include "headfile.h"

#define GPS_UART_HANDLE    huart1
#define GPS_DMA_BUF_SIZE   1024

typedef struct
{
    uint8_t gps_state;      // ��λ����״̬��0=��Ч,1=���㶨λ,2=��ֶ�λ
    float longitude;        // ���ȣ�ʮ���ƣ�
    float latitude;         // γ�ȣ�ʮ���ƣ�
    float altitude;         // ���Σ��ף�
    uint8_t sat_num;        // ��������
    uint8_t valid;          // ������Ч��־��1=��Ч,0=��Ч��
    uint8_t lat_dir;        // γ�ȷ���'N' �� 'S'
    uint8_t lon_dir;        // ���ȷ���'E' �� 'W'
    
} GPS_Data_Typedef;

// ��������
void GPS_Init(void);
uint8_t GPS_Is_Valid(void);
float GPS_Get_Latitude(void);
float GPS_Get_Longitude(void);
float GPS_Get_Altitude(void);
uint8_t GPS_Get_SatNum(void);
void GPS_Print_Data(void);
void GPS_Parse_data(char *buf);

// 导航文本缓冲区
extern volatile uint8_t nav_text_ready;
extern char nav_text_buf[256];

// ȫ�ֱ�������
extern GPS_Data_Typedef GPS_DATA;

#endif

