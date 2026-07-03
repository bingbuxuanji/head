// algorithm.h — MAX30102 心率和血氧计算算法
// 改编自 Maxim Integrated 官方参考实现，适配 STM32G431 HAL 平台
#ifndef __ALGORITHM_H
#define __ALGORITHM_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ========== 算法常量 ========== */
#define BUFFER_SIZE     500     // 数据缓冲区大小 (100Hz * 5秒)
#define MA4_SIZE        4       // 4点移动平均窗口
#define HAMMING_SIZE    5       // 汉明窗长度

/* ========== 算法全局工作数组 ========== */
extern int32_t an_x[BUFFER_SIZE];   // 通用计算缓冲区 (IR/Red)
extern int32_t an_y[BUFFER_SIZE];   // Red信号缓冲区
extern int32_t an_dx[BUFFER_SIZE];  // 差分/导数缓冲区

/* ========== 汉明窗系数 (缩放至整数，总和=1146) ========== */
extern const int16_t auw_hamm[HAMMING_SIZE];

/* ========== SpO2 查找表 ========== */
// 索引 = (AC_red/DC_red) / (AC_ir/DC_ir) * 100 取整
// 取值范围 0~184，存储对应 SpO2 百分比值
extern const uint8_t uch_spo2_table[185];

/* ========== 函数声明 ========== */

/**
 * @brief  计算心率和血氧饱和度
 * @param  pun_ir_buffer       红外光传感器数据缓冲区
 * @param  n_ir_buffer_length  缓冲区长度 (应为 BUFFER_SIZE=500)
 * @param  pun_red_buffer      红光传感器数据缓冲区
 * @param  pn_spo2             输出：SpO2 值 (%)
 * @param  pch_spo2_valid      输出：1=SpO2有效, 0=无效
 * @param  pn_heart_rate       输出：心率值 (bpm)
 * @param  pch_hr_valid        输出：1=心率有效, 0=无效
 */
void maxim_heart_rate_and_oxygen_saturation(
    uint32_t *pun_ir_buffer,  int32_t n_ir_buffer_length,
    uint32_t *pun_red_buffer,
    int32_t *pn_spo2, int8_t *pch_spo2_valid,
    int32_t *pn_heart_rate, int8_t *pch_hr_valid);

/**
 * @brief  查找峰值 (主入口)
 * @param  pn_locs        输出：峰值位置数组
 * @param  pn_npks        输出：找到的峰值数量
 * @param  pn_x           输入信号数组
 * @param  n_size         信号长度
 * @param  n_min_height   最小峰值高度
 * @param  n_min_distance 峰值间最小距离
 * @param  n_max_num      最多返回的峰值数
 */
void maxim_find_peaks(int32_t *pn_locs, int32_t *pn_npks,
    int32_t *pn_x, int32_t n_size,
    int32_t n_min_height, int32_t n_min_distance, int32_t n_max_num);

/**
 * @brief  找到所有高于阈值的峰值
 */
void maxim_peaks_above_min_height(int32_t *pn_locs, int32_t *pn_npks,
    int32_t *pn_x, int32_t n_size, int32_t n_min_height);

/**
 * @brief  移除距离过近的峰值 (保留较高的)
 */
void maxim_remove_close_peaks(int32_t *pn_locs, int32_t *pn_npks,
    int32_t *pn_x, int32_t n_min_distance);

/**
 * @brief  升序排序 (插入排序)
 */
void maxim_sort_ascend(int32_t *pn_x, int32_t n_size);

/**
 * @brief  根据数据值降序排列索引 (插入排序)
 */
void maxim_sort_indices_descend(int32_t *pn_x, int32_t *pn_indx, int32_t n_size);

#ifdef __cplusplus
}
#endif

#endif /* __ALGORITHM_H */
