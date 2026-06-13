package com.helmet.monitor

import android.util.Log
import com.google.gson.JsonObject
import com.google.gson.JsonParser
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import org.eclipse.paho.client.mqttv3.*
import org.eclipse.paho.client.mqttv3.persist.MemoryPersistence

/**
 * MQTT 连接管理器（纯 Paho JVM client + 协程，不依赖 Android Service）
 *
 * 避免 Paho Android Service 在 API 34+ 的兼容问题。
 */
class MqttManager {

    companion object {
        private const val TAG = "HelmetMqtt"
        const val BROKER_URL = "tcp://frp-run.com:18830"
        const val DEVICE_ID = "helmet_001"
        const val DEVICE_KEY = "helmet_key_001"
    }

    private var client: MqttClient? = null
    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())

    // ---- 可观察状态 ----
    private val _latestData = MutableStateFlow<HelmetData?>(null)
    val latestData: StateFlow<HelmetData?> = _latestData

    private val _alerts = MutableStateFlow<List<AlertItem>>(emptyList())
    val alerts: StateFlow<List<AlertItem>> = _alerts

    private val _connected = MutableStateFlow(false)
    val connected: StateFlow<Boolean> = _connected

    private var alertCallback: ((AlertItem) -> Unit)? = null

    fun connect(onAlert: ((AlertItem) -> Unit)? = null) {
        alertCallback = onAlert
        if (_connected.value && client?.isConnected == true) return

        scope.launch {
            try {
                val c = MqttClient(BROKER_URL, "android_monitor", MemoryPersistence())
                client = c
                c.setCallback(createCallback())

                val opts = MqttConnectOptions().apply {
                    userName = DEVICE_ID
                    password = DEVICE_KEY.toCharArray()
                    keepAliveInterval = 30
                    isCleanSession = true
                    isAutomaticReconnect = true
                    maxReconnectDelay = 15000
                    connectionTimeout = 10
                }

                c.connect(opts)
                Log.i(TAG, "已连接")
                _connected.value = true

                val topics = arrayOf(
                    "helmet/$DEVICE_ID/attributes",
                    "helmet/$DEVICE_ID/data/processed",
                    "helmet/$DEVICE_ID/alerts",
                    "helmet/$DEVICE_ID/events",
                )
                c.subscribe(topics, intArrayOf(0, 0, 1, 0))
                Log.i(TAG, "已订阅 ${topics.size} 个主题")

            } catch (e: Exception) {
                Log.e(TAG, "连接失败: ${e.message}", e)
                _connected.value = false
            }
        }
    }

    fun disconnect() {
        scope.launch {
            try {
                client?.disconnect()
                client?.close()
            } catch (_: Exception) {}
            client = null
            _connected.value = false
        }
    }

    private fun createCallback() = object : MqttCallback {
        override fun connectionLost(cause: Throwable?) {
            Log.w(TAG, "连接断开: ${cause?.message}")
            _connected.value = false
        }

        override fun messageArrived(topic: String, msg: MqttMessage) {
            try {
                dispatch(topic, String(msg.payload, Charsets.UTF_8))
            } catch (e: Exception) {
                Log.e(TAG, "解析异常: ${e.message}")
            }
        }

        override fun deliveryComplete(token: IMqttDeliveryToken?) {}
    }

    private fun dispatch(topic: String, payload: String) {
        val obj = try { JsonParser.parseString(payload).asJsonObject } catch (_: Exception) { null } ?: return

        when {
            topic.endsWith("/alerts")    -> handleAlert(obj)
            topic.endsWith("/attributes") -> handleAttributes(obj)
            topic.endsWith("/events")     -> Log.d(TAG, "事件: $payload")
        }
    }

    private fun handleAttributes(obj: JsonObject) {
        _latestData.value = HelmetData(
            temperature = obj.get("temperature")?.asDouble,
            heartRate = obj.get("heart_rate")?.asDouble?.toInt(),
            velocity = obj.get("velocity")?.asDouble,
            longitude = obj.get("longitude")?.asDouble,
            latitude = obj.get("latitude")?.asDouble,
        )
    }

    private fun handleAlert(obj: JsonObject) {
        val arr = obj.getAsJsonArray("alerts") ?: return
        val newAlerts = arr.mapNotNull { elem ->
            val a = elem.asJsonObject
            AlertItem(
                type = a.get("type")?.asString ?: "?",
                field = a.get("field")?.asString ?: "?",
                msg = a.get("msg")?.asString ?: "?",
                value = a.get("value")?.asDouble,
                threshold = a.get("threshold")?.asDouble,
            )
        }
        _alerts.value = (_alerts.value + newAlerts).takeLast(50)
        newAlerts.forEach { alertCallback?.invoke(it) }
    }
}

// ---- 数据模型 ----

data class HelmetData(
    val temperature: Double?,
    val heartRate: Int?,
    val velocity: Double?,
    val longitude: Double?,
    val latitude: Double?,
)

data class AlertItem(
    val type: String,
    val field: String,
    val msg: String,
    val value: Double?,
    val threshold: Double?,
)
