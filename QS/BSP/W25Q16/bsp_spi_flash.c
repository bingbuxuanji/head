#include "./W25Q16/bsp_spi_flash.h"
#include "spi.h"

extern SPI_HandleTypeDef hspi1;

static __IO uint32_t  SPITimeout = SPIT_LONG_TIMEOUT;

static uint16_t SPI_TIMEOUT_UserCallback(uint8_t errorCode);

void SPI_FLASH_Init(void)
{
  /* SPI GPIO/clock already configured by MX_SPI1_Init() in spi.c */
  /* W25Q16 works with CPOL=Low, CPHA=1Edge (SPI Mode 0) */
  __HAL_SPI_ENABLE(&hspi1);
}


 /**
  * @brief  erase sector
  * @param  SectorAddr: sector address to erase
  * @retval none
  */
void SPI_FLASH_SectorErase(uint32_t SectorAddr)
{
  SPI_FLASH_WriteEnable();
  SPI_FLASH_WaitForWriteEnd();
  SPI_FLASH_CS_LOW();
  SPI_FLASH_SendByte(W25X_SectorErase);
  SPI_FLASH_SendByte((SectorAddr & 0xFF0000) >> 16);
  SPI_FLASH_SendByte((SectorAddr & 0xFF00) >> 8);
  SPI_FLASH_SendByte(SectorAddr & 0xFF);
  SPI_FLASH_CS_HIGH();
  SPI_FLASH_WaitForWriteEnd();
}


 /**
  * @brief  bulk erase entire chip
  * @param  none
  * @retval none
  */
void SPI_FLASH_BulkErase(void)
{
  SPI_FLASH_WriteEnable();

  SPI_FLASH_CS_LOW();
  SPI_FLASH_SendByte(W25X_ChipErase);
  SPI_FLASH_CS_HIGH();

  SPI_FLASH_WaitForWriteEnd();
}

 /**
  * @brief  page write to FLASH (max 256 bytes)
  * @param  pBuffer: data pointer
  * @param  WriteAddr: write address
  * @param  NumByteToWrite: length (<= SPI_FLASH_PerWritePageSize)
  * @retval none
  */
void SPI_FLASH_PageWrite(uint8_t* pBuffer, uint32_t WriteAddr, uint16_t NumByteToWrite)
{
  SPI_FLASH_WriteEnable();

  SPI_FLASH_CS_LOW();
  SPI_FLASH_SendByte(W25X_PageProgram);
  SPI_FLASH_SendByte((WriteAddr & 0xFF0000) >> 16);
  SPI_FLASH_SendByte((WriteAddr & 0xFF00) >> 8);
  SPI_FLASH_SendByte(WriteAddr & 0xFF);

  if(NumByteToWrite > SPI_FLASH_PerWritePageSize)
  {
     NumByteToWrite = SPI_FLASH_PerWritePageSize;
     FLASH_ERROR("SPI_FLASH_PageWrite too large!");
  }

  while (NumByteToWrite--)
  {
    SPI_FLASH_SendByte(*pBuffer);
    pBuffer++;
  }

  SPI_FLASH_CS_HIGH();
  SPI_FLASH_WaitForWriteEnd();
}


 /**
  * @brief  write buffer to FLASH with page management
  * @param  pBuffer: data pointer
  * @param  WriteAddr: write address
  * @param  NumByteToWrite: length
  * @retval none
  */
void SPI_FLASH_BufferWrite(uint8_t* pBuffer, uint32_t WriteAddr, uint16_t NumByteToWrite)
{
  uint8_t NumOfPage = 0, NumOfSingle = 0, Addr = 0, count = 0, temp = 0;

  Addr = WriteAddr % SPI_FLASH_PageSize;
  count = SPI_FLASH_PageSize - Addr;
  NumOfPage =  NumByteToWrite / SPI_FLASH_PageSize;
  NumOfSingle = NumByteToWrite % SPI_FLASH_PageSize;

  if (Addr == 0)
  {
    if (NumOfPage == 0)
    {
      SPI_FLASH_PageWrite(pBuffer, WriteAddr, NumByteToWrite);
    }
    else
    {
      while (NumOfPage--)
      {
        SPI_FLASH_PageWrite(pBuffer, WriteAddr, SPI_FLASH_PageSize);
        WriteAddr +=  SPI_FLASH_PageSize;
        pBuffer += SPI_FLASH_PageSize;
      }
      SPI_FLASH_PageWrite(pBuffer, WriteAddr, NumOfSingle);
    }
  }
  else
  {
    if (NumOfPage == 0)
    {
      if (NumOfSingle > count)
      {
        temp = NumOfSingle - count;
        SPI_FLASH_PageWrite(pBuffer, WriteAddr, count);
        WriteAddr +=  count;
        pBuffer += count;
        SPI_FLASH_PageWrite(pBuffer, WriteAddr, temp);
      }
      else
      {
        SPI_FLASH_PageWrite(pBuffer, WriteAddr, NumByteToWrite);
      }
    }
    else
    {
      NumByteToWrite -= count;
      NumOfPage =  NumByteToWrite / SPI_FLASH_PageSize;
      NumOfSingle = NumByteToWrite % SPI_FLASH_PageSize;

      SPI_FLASH_PageWrite(pBuffer, WriteAddr, count);
      WriteAddr +=  count;
      pBuffer += count;

      while (NumOfPage--)
      {
        SPI_FLASH_PageWrite(pBuffer, WriteAddr, SPI_FLASH_PageSize);
        WriteAddr +=  SPI_FLASH_PageSize;
        pBuffer += SPI_FLASH_PageSize;
      }
      if (NumOfSingle != 0)
      {
        SPI_FLASH_PageWrite(pBuffer, WriteAddr, NumOfSingle);
      }
    }
  }
}

 /**
  * @brief  read data from FLASH
  * @param  pBuffer: output buffer
  * @param  ReadAddr: read address
  * @param  NumByteToRead: length
  * @retval none
  */
void SPI_FLASH_BufferRead(uint8_t* pBuffer, uint32_t ReadAddr, uint16_t NumByteToRead)
{
  SPI_FLASH_CS_LOW();

  SPI_FLASH_SendByte(W25X_ReadData);
  SPI_FLASH_SendByte((ReadAddr & 0xFF0000) >> 16);
  SPI_FLASH_SendByte((ReadAddr& 0xFF00) >> 8);
  SPI_FLASH_SendByte(ReadAddr & 0xFF);

  while (NumByteToRead--)
  {
    *pBuffer = SPI_FLASH_SendByte(Dummy_Byte);
    pBuffer++;
  }

  SPI_FLASH_CS_HIGH();
}


 /**
  * @brief  read FLASH JEDEC ID
  * @param  none
  * @retval FLASH ID
  */
uint32_t SPI_FLASH_ReadID(void)
{
  uint32_t Temp = 0, Temp0 = 0, Temp1 = 0, Temp2 = 0;

  SPI_FLASH_CS_LOW();
  SPI_FLASH_SendByte(W25X_JedecDeviceID);
  Temp0 = SPI_FLASH_SendByte(Dummy_Byte);
  Temp1 = SPI_FLASH_SendByte(Dummy_Byte);
  Temp2 = SPI_FLASH_SendByte(Dummy_Byte);
  SPI_FLASH_CS_HIGH();

  Temp = (Temp0 << 16) | (Temp1 << 8) | Temp2;
  return Temp;
}

 /**
  * @brief  read FLASH Device ID
  * @param  none
  * @retval FLASH Device ID
  */
uint32_t SPI_FLASH_ReadDeviceID(void)
{
  uint32_t Temp = 0;

  SPI_FLASH_CS_LOW();
  SPI_FLASH_SendByte(W25X_DeviceID);
  SPI_FLASH_SendByte(Dummy_Byte);
  SPI_FLASH_SendByte(Dummy_Byte);
  SPI_FLASH_SendByte(Dummy_Byte);
  Temp = SPI_FLASH_SendByte(Dummy_Byte);
  SPI_FLASH_CS_HIGH();

  return Temp;
}

void SPI_FLASH_StartReadSequence(uint32_t ReadAddr)
{
  SPI_FLASH_CS_LOW();
  SPI_FLASH_SendByte(W25X_ReadData);
  SPI_FLASH_SendByte((ReadAddr & 0xFF0000) >> 16);
  SPI_FLASH_SendByte((ReadAddr& 0xFF00) >> 8);
  SPI_FLASH_SendByte(ReadAddr & 0xFF);
}


uint8_t SPI_FLASH_ReadByte(void)
{
  return (SPI_FLASH_SendByte(Dummy_Byte));
}


uint8_t SPI_FLASH_SendByte(uint8_t byte)
{
  SPITimeout = SPIT_FLAG_TIMEOUT;

  while (__HAL_SPI_GET_FLAG( &hspi1, SPI_FLAG_TXE ) == RESET)
   {
    if((SPITimeout--) == 0) return SPI_TIMEOUT_UserCallback(0);
   }

  WRITE_REG(hspi1.Instance->DR, byte);

  SPITimeout = SPIT_FLAG_TIMEOUT;

  while (__HAL_SPI_GET_FLAG( &hspi1, SPI_FLAG_RXNE ) == RESET)
   {
    if((SPITimeout--) == 0) return SPI_TIMEOUT_UserCallback(1);
   }

  return READ_REG(hspi1.Instance->DR);
}

uint16_t SPI_FLASH_SendHalfWord(uint16_t HalfWord)
{
  SPITimeout = SPIT_FLAG_TIMEOUT;

  while (__HAL_SPI_GET_FLAG( &hspi1,  SPI_FLAG_TXE ) == RESET)
  {
    if((SPITimeout--) == 0) return SPI_TIMEOUT_UserCallback(2);
   }

  WRITE_REG(hspi1.Instance->DR, HalfWord);

  SPITimeout = SPIT_FLAG_TIMEOUT;

  while (__HAL_SPI_GET_FLAG( &hspi1, SPI_FLAG_RXNE ) == RESET)
   {
    if((SPITimeout--) == 0) return SPI_TIMEOUT_UserCallback(3);
   }
  return READ_REG(hspi1.Instance->DR);
}


void SPI_FLASH_WriteEnable(void)
{
  SPI_FLASH_CS_LOW();
  SPI_FLASH_SendByte(W25X_WriteEnable);
  SPI_FLASH_CS_HIGH();
}

void SPI_FLASH_WaitForWriteEnd(void)
{
  uint8_t FLASH_Status = 0;

  SPI_FLASH_CS_LOW();
  SPI_FLASH_SendByte(W25X_ReadStatusReg);

  SPITimeout = SPIT_FLAG_TIMEOUT;
  do
  {
    FLASH_Status = SPI_FLASH_SendByte(Dummy_Byte);

    {
      if((SPITimeout--) == 0)
      {
        SPI_TIMEOUT_UserCallback(4);
        return;
      }
    }
  }
  while ((FLASH_Status & WIP_Flag) == SET);

  SPI_FLASH_CS_HIGH();
}


void SPI_Flash_PowerDown(void)
{
  SPI_FLASH_CS_LOW();
  SPI_FLASH_SendByte(W25X_PowerDown);
  SPI_FLASH_CS_HIGH();
}

void SPI_Flash_WAKEUP(void)
{
  SPI_FLASH_CS_LOW();
  SPI_FLASH_SendByte(W25X_ReleasePowerDown);
  SPI_FLASH_CS_HIGH();
}




uint8_t SPI_FLASH_ReadStatusReg(void)
{
    uint8_t status;
    SPI_FLASH_CS_LOW();
    SPI_FLASH_SendByte(W25X_ReadStatusReg);
    status = SPI_FLASH_SendByte(Dummy_Byte);
    SPI_FLASH_CS_HIGH();
    return status;
}

void SPI_FLASH_ClearProtect(void)
{
    uint8_t sr = SPI_FLASH_ReadStatusReg();
    if (sr & 0x3C)  /* BP2(bit5) BP1(bit4) BP0(bit3) or SRP(bit7) */
    {
        SPI_FLASH_WriteEnable();
        SPI_FLASH_CS_LOW();
        SPI_FLASH_SendByte(W25X_WriteStatusReg);
        SPI_FLASH_SendByte(0x00);  /* Clear SRP, BP2, BP1, BP0 */
        SPI_FLASH_CS_HIGH();
        SPI_FLASH_WaitForWriteEnd();
    }
}

static  uint16_t SPI_TIMEOUT_UserCallback(uint8_t errorCode)
{
  FLASH_ERROR("SPI timeout! errorCode = %d", errorCode);
  return 0;
}

/*********************************************END OF FILE**********************/
