package com.helmet.monitor

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

/**
 * 全局数据仓库单例 — Service 写入，Activity 读取
 *
 * 消除 MainActivity 和 MonitorService 各自维护 MQTT 连接的问题，
 * 所有 MQTT 数据由 MonitorService 独占写入，UI 层只读。
 */
object DataRepository {

    // ---- MQTT 连接状态 ----
    private val _connected = MutableStateFlow(false)
    val connected: StateFlow<Boolean> = _connected

    // ---- 最新头盔数据 ----
    private val _latestData = MutableStateFlow<HelmetData?>(null)
    val latestData: StateFlow<HelmetData?> = _latestData

    // ---- 告警列表（最近 50 条） ----
    private val _alerts = MutableStateFlow<List<AlertItem>>(emptyList())
    val alerts: StateFlow<List<AlertItem>> = _alerts

    // ---- 内部写入（仅 MonitorService 调用） ----

    fun setConnected(value: Boolean) {
        _connected.value = value
    }

    fun updateData(data: HelmetData) {
        _latestData.value = data
    }

    fun addAlerts(newAlerts: List<AlertItem>) {
        _alerts.value = (_alerts.value + newAlerts).takeLast(50)
    }
}
