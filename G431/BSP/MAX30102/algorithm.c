// algorithm.c — MAX30102 心率和血氧饱和度计算算法
// 改编自 Maxim Integrated 官方参考实现，适配 STM32G431 HAL 平台
//
// 算法流程:
//   1. 对IR信号去直流 → 4点MA平滑 → 求差分 → 2点MA平滑 → 汉明窗滤波
//   2. 翻转波形后用峰值检测器找谷值 → 计算峰间距 → 心率 = 6000/平均间距
//   3. 在原始IR/Red信号的谷值间找DC和AC分量 → 计算比率 → 查表得SpO2

#include "algorithm.h"
#include <string.h>

/* ========== 算法全局工作数组 ========== */
int32_t an_x[BUFFER_SIZE];
int32_t an_y[BUFFER_SIZE];
int32_t an_dx[BUFFER_SIZE];

/* ========== 汉明窗系数 ========== */
// 5点汉明窗 w(n)=0.54-0.46*cos(2π*n/4)，缩放至整数和=1146
// 值: {41, 276, 512, 276, 41}, 总和 = 1146
const int16_t auw_hamm[HAMMING_SIZE] = {41, 276, 512, 276, 41};

/* ========== SpO2 查找表 ========== */
// 索引 = (AC_red/DC_red) / (AC_ir/DC_ir) * 100
// 基于公式: SpO2 = -45.060*R² + 30.354*R + 94.845 校准
// 索引 0~184 对应 SpO2 百分比
const uint8_t uch_spo2_table[185] = {
     0,  0,  0,  0,  0,  0,  0,  0,  0,  0,   //   0~9
     0,  0,  0,  0,  0,  0,  0,  0,  0,  0,   //  10~19
     0,  0,  0,  0,  0,  0,  0,  0,  0,  0,   //  20~29
     0,  0,  0,  0,  0,  0,  0,  0,  0,  0,   //  30~39
     0,  0,  0,  0,  0,  0,  0,  0,  0,  0,   //  40~49
   100,100,100,100,100,100,100, 99, 99, 99,   //  50~59
    99, 99, 99, 99, 99, 99, 98, 98, 98, 98,   //  60~69
    98, 98, 98, 97, 97, 97, 97, 97, 97, 97,   //  70~79
    96, 96, 96, 96, 96, 96, 96, 96, 95, 95,   //  80~89
    95, 95, 95, 95, 95, 95, 94, 94, 94, 94,   //  90~99
    94, 94, 94, 93, 93, 93, 93, 93, 93, 93,   // 100~109
    92, 92, 92, 92, 92, 92, 92, 91, 91, 91,   // 110~119
    91, 91, 91, 90, 90, 90, 90, 90, 90, 89,   // 120~129
    89, 89, 89, 89, 89, 88, 88, 88, 88, 88,   // 130~139
    87, 87, 87, 87, 87, 86, 86, 86, 86, 86,   // 140~149
    85, 85, 85, 85, 84, 84, 84, 84, 83, 83,   // 150~159
    83, 82, 82, 82, 81, 81, 81, 80, 80, 80,   // 160~169
    79, 79, 78, 78, 77, 77, 76, 76, 75, 75,   // 170~179
    74, 74, 73, 72, 72                                    // 180~184
};

/* ========== 内部宏 ========== */
#define MIN(a,b) ((a) < (b) ? (a) : (b))

/* ================================================================
 * maxim_heart_rate_and_oxygen_saturation()
 *   主算法 — 计算心率和SpO2
 * ================================================================ */
void maxim_heart_rate_and_oxygen_saturation(
    uint32_t *pun_ir_buffer,  int32_t n_ir_buffer_length,
    uint32_t *pun_red_buffer,
    int32_t *pn_spo2, int8_t *pch_spo2_valid,
    int32_t *pn_heart_rate, int8_t *pch_hr_valid)
{
    uint32_t un_ir_mean, un_only_once;
    int32_t k, n_i_ratio_count;
    int32_t i, s, m, n_exact_ir_valley_locs_count, n_middle_idx;
    int32_t n_th1, n_npks, n_c_min;
    int32_t an_ir_valley_locs[15];
    int32_t an_exact_ir_valley_locs[15];
    int32_t an_dx_peak_locs[15];
    int32_t n_peak_interval_sum;

    int32_t n_y_ac, n_x_ac;
    int32_t n_spo2_calc;
    int32_t n_y_dc_max, n_x_dc_max;
    int32_t n_y_dc_max_idx, n_x_dc_max_idx;
    int32_t an_ratio[5], n_ratio_average;
    int32_t n_nume, n_denom;

    /* ---- 1. 去除IR信号直流分量 ---- */
    un_ir_mean = 0;
    for (k = 0; k < n_ir_buffer_length; k++)
        un_ir_mean += pun_ir_buffer[k];
    un_ir_mean = un_ir_mean / n_ir_buffer_length;
    for (k = 0; k < n_ir_buffer_length; k++)
        an_x[k] = (int32_t)(pun_ir_buffer[k] - un_ir_mean);

    /* ---- 2. 4点移动平均 ---- */
    for (k = 0; k < BUFFER_SIZE - MA4_SIZE; k++) {
        n_denom = (an_x[k] + an_x[k+1] + an_x[k+2] + an_x[k+3]);
        an_x[k] = n_denom / (int32_t)4;
    }

    /* ---- 3. 求差分 ---- */
    for (k = 0; k < BUFFER_SIZE - MA4_SIZE - 1; k++)
        an_dx[k] = (an_x[k+1] - an_x[k]);

    /* ---- 4. 差分信号的2点移动平均 ---- */
    for (k = 0; k < BUFFER_SIZE - MA4_SIZE - 2; k++)
        an_dx[k] = (an_dx[k] + an_dx[k+1]) / 2;

    /* ---- 5. 汉明窗滤波 (翻转波形以用峰值检测器找谷值) ---- */
    for (i = 0; i < BUFFER_SIZE - HAMMING_SIZE - MA4_SIZE - 2; i++) {
        s = 0;
        for (k = i; k < i + HAMMING_SIZE; k++)
            s -= an_dx[k] * auw_hamm[k - i];
        an_dx[i] = s / (int32_t)1146;   // 除以汉明窗系数总和
    }

    /* ---- 6. 动态阈值计算 ---- */
    n_th1 = 0;
    for (k = 0; k < BUFFER_SIZE - HAMMING_SIZE; k++)
        n_th1 += ((an_dx[k] > 0) ? an_dx[k] : ((int32_t)0 - an_dx[k]));
    n_th1 = n_th1 / (BUFFER_SIZE - HAMMING_SIZE);

    /* ---- 7. 峰值检测 (检测的是翻转信号的峰值 → 对应原信号的谷值) ---- */
    maxim_find_peaks(an_dx_peak_locs, &n_npks, an_dx,
                     BUFFER_SIZE - HAMMING_SIZE,
                     n_th1, 8, 5);

    /* ---- 8. 计算心率 ---- */
    n_peak_interval_sum = 0;
    if (n_npks >= 2) {
        for (k = 1; k < n_npks; k++)
            n_peak_interval_sum += (an_dx_peak_locs[k] - an_dx_peak_locs[k - 1]);
        n_peak_interval_sum = n_peak_interval_sum / (n_npks - 1);
        *pn_heart_rate = (int32_t)(6000 / n_peak_interval_sum);  // 100Hz采样 → *60s/100 = *0.6 → 60*100 = 6000
        *pch_hr_valid = 1;
    } else {
        *pn_heart_rate = -999;
        *pch_hr_valid = 0;
    }

    /* ---- 9. 由翻转信号峰值推算原始信号的谷值位置 ---- */
    for (k = 0; k < n_npks; k++)
        an_ir_valley_locs[k] = an_dx_peak_locs[k] + HAMMING_SIZE / 2;

    /* ---- 10. 准备原始 IR 和 Red 信号进行 SpO2 计算 ---- */
    for (k = 0; k < n_ir_buffer_length; k++) {
        an_x[k] = (int32_t)pun_ir_buffer[k];
        an_y[k] = (int32_t)pun_red_buffer[k];
    }

    /* ---- 11. 在谷值附近精确定位最小值 ---- */
    n_exact_ir_valley_locs_count = 0;
    for (k = 0; k < n_npks; k++) {
        un_only_once = 1;
        m = an_ir_valley_locs[k];
        n_c_min = 16777216;   // 2^24
        if (m + 5 < BUFFER_SIZE - HAMMING_SIZE && m - 5 > 0) {
            for (i = m - 5; i < m + 5; i++) {
                if (an_x[i] < n_c_min) {
                    if (un_only_once > 0)
                        un_only_once = 0;
                    n_c_min = an_x[i];
                    an_exact_ir_valley_locs[k] = i;
                }
            }
            if (un_only_once == 0)
                n_exact_ir_valley_locs_count++;
        }
    }
    if (n_exact_ir_valley_locs_count < 2) {
        *pn_spo2 = -999;       // 信号比率超出范围
        *pch_spo2_valid = 0;
        return;
    }

    /* ---- 12. 对原始信号做4点移动平均 ---- */
    for (k = 0; k < BUFFER_SIZE - MA4_SIZE; k++) {
        an_x[k] = (an_x[k] + an_x[k+1] + an_x[k+2] + an_x[k+3]) / (int32_t)4;
        an_y[k] = (an_y[k] + an_y[k+1] + an_y[k+2] + an_y[k+3]) / (int32_t)4;
    }

    /* ---- 13. 计算 SpO2 ---- */
    n_ratio_average = 0;
    n_i_ratio_count = 0;
    for (k = 0; k < 5; k++) an_ratio[k] = 0;

    // 边界检查
    for (k = 0; k < n_exact_ir_valley_locs_count; k++) {
        if (an_exact_ir_valley_locs[k] > BUFFER_SIZE) {
            *pn_spo2 = -999;
            *pch_spo2_valid = 0;
            return;
        }
    }

    // 在每对相邻谷值之间查找 DC 和 AC 分量
    for (k = 0; k < n_exact_ir_valley_locs_count - 1; k++) {
        n_y_dc_max = -16777216;
        n_x_dc_max = -16777216;
        if (an_exact_ir_valley_locs[k+1] - an_exact_ir_valley_locs[k] > 10) {
            // 在两个谷值间找 DC 最大值
            for (i = an_exact_ir_valley_locs[k]; i < an_exact_ir_valley_locs[k+1]; i++) {
                if (an_x[i] > n_x_dc_max) { n_x_dc_max = an_x[i]; n_x_dc_max_idx = i; }
                if (an_y[i] > n_y_dc_max) { n_y_dc_max = an_y[i]; n_y_dc_max_idx = i; }
            }

            // Red AC分量 (扣除线性DC分量)
            n_y_ac = (an_y[an_exact_ir_valley_locs[k+1]] - an_y[an_exact_ir_valley_locs[k]])
                   * (n_y_dc_max_idx - an_exact_ir_valley_locs[k]);
            n_y_ac = an_y[an_exact_ir_valley_locs[k]]
                   + n_y_ac / (an_exact_ir_valley_locs[k+1] - an_exact_ir_valley_locs[k]);
            n_y_ac = an_y[n_y_dc_max_idx] - n_y_ac;

            // IR AC分量 (扣除线性DC分量)
            n_x_ac = (an_x[an_exact_ir_valley_locs[k+1]] - an_x[an_exact_ir_valley_locs[k]])
                   * (n_x_dc_max_idx - an_exact_ir_valley_locs[k]);
            n_x_ac = an_x[an_exact_ir_valley_locs[k]]
                   + n_x_ac / (an_exact_ir_valley_locs[k+1] - an_exact_ir_valley_locs[k]);
            n_x_ac = an_x[n_y_dc_max_idx] - n_x_ac;

            // 计算比率 (AC_red/DC_red) / (AC_ir/DC_ir) * 100
            n_nume = (n_y_ac * n_x_dc_max) >> 7;
            n_denom = (n_x_ac * n_y_dc_max) >> 7;
            if (n_denom > 0 && n_i_ratio_count < 5 && n_nume != 0) {
                an_ratio[n_i_ratio_count] = (n_nume * 100) / n_denom;
                n_i_ratio_count++;
            }
        }
    }

    /* ---- 14. 取比率中值，查表得 SpO2 ---- */
    maxim_sort_ascend(an_ratio, n_i_ratio_count);
    n_middle_idx = n_i_ratio_count / 2;

    if (n_middle_idx > 1)
        n_ratio_average = (an_ratio[n_middle_idx - 1] + an_ratio[n_middle_idx]) / 2;
    else
        n_ratio_average = an_ratio[n_middle_idx];

    if (n_ratio_average > 2 && n_ratio_average < 184) {
        n_spo2_calc = (int32_t)uch_spo2_table[n_ratio_average];
        *pn_spo2 = n_spo2_calc;
        *pch_spo2_valid = 1;
    } else {
        *pn_spo2 = -999;
        *pch_spo2_valid = 0;
    }
}

/* ================================================================
 * maxim_find_peaks()
 *   峰值检测主入口
 * ================================================================ */
void maxim_find_peaks(int32_t *pn_locs, int32_t *pn_npks,
    int32_t *pn_x, int32_t n_size,
    int32_t n_min_height, int32_t n_min_distance, int32_t n_max_num)
{
    maxim_peaks_above_min_height(pn_locs, pn_npks, pn_x, n_size, n_min_height);
    maxim_remove_close_peaks(pn_locs, pn_npks, pn_x, n_min_distance);
    *pn_npks = MIN(*pn_npks, n_max_num);
}

/* ================================================================
 * maxim_peaks_above_min_height()
 *   找出所有高于阈值的峰值
 * ================================================================ */
void maxim_peaks_above_min_height(int32_t *pn_locs, int32_t *pn_npks,
    int32_t *pn_x, int32_t n_size, int32_t n_min_height)
{
    int32_t i = 1, n_width;
    *pn_npks = 0;

    while (i < n_size - 1) {
        // 找到峰值的左边缘
        if (pn_x[i] > n_min_height && pn_x[i] > pn_x[i-1]) {
            n_width = 1;
            // 处理平坦峰顶
            while (i + n_width < n_size && pn_x[i] == pn_x[i+n_width])
                n_width++;
            // 确认右边缘 (下降)
            if (pn_x[i] > pn_x[i+n_width] && (*pn_npks) < 15) {
                pn_locs[(*pn_npks)++] = i;       // 平坦峰取左边缘
                i += n_width + 1;
            } else {
                i += n_width;
            }
        } else {
            i++;
        }
    }
}

/* ================================================================
 * maxim_remove_close_peaks()
 *   移除距离过近的峰值，保留较高的
 * ================================================================ */
void maxim_remove_close_peaks(int32_t *pn_locs, int32_t *pn_npks,
    int32_t *pn_x, int32_t n_min_distance)
{
    int32_t i, j, n_old_npks, n_dist;

    // 按峰值大小降序排序索引
    maxim_sort_indices_descend(pn_x, pn_locs, *pn_npks);

    for (i = -1; i < *pn_npks; i++) {
        n_old_npks = *pn_npks;
        *pn_npks = i + 1;
        for (j = i + 1; j < n_old_npks; j++) {
            n_dist = pn_locs[j] - (i == -1 ? -1 : pn_locs[i]);
            if (n_dist > n_min_distance || n_dist < -n_min_distance)
                pn_locs[(*pn_npks)++] = pn_locs[j];
        }
    }

    // 索引重新升序
    maxim_sort_ascend(pn_locs, *pn_npks);
}

/* ================================================================
 * maxim_sort_ascend()
 *   升序排序 (插入排序)
 * ================================================================ */
void maxim_sort_ascend(int32_t *pn_x, int32_t n_size)
{
    int32_t i, j, n_temp;
    for (i = 1; i < n_size; i++) {
        n_temp = pn_x[i];
        for (j = i; j > 0 && n_temp < pn_x[j-1]; j--)
            pn_x[j] = pn_x[j-1];
        pn_x[j] = n_temp;
    }
}

/* ================================================================
 * maxim_sort_indices_descend()
 *   按数据值降序排列索引 (插入排序)
 * ================================================================ */
void maxim_sort_indices_descend(int32_t *pn_x, int32_t *pn_indx, int32_t n_size)
{
    int32_t i, j, n_temp;
    for (i = 1; i < n_size; i++) {
        n_temp = pn_indx[i];
        for (j = i; j > 0 && pn_x[n_temp] > pn_x[pn_indx[j-1]]; j--)
            pn_indx[j] = pn_indx[j-1];
        pn_indx[j] = n_temp;
    }
}
