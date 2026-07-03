package com.helmet.monitor

import android.content.Context
import android.util.Log
import com.google.gson.Gson
import com.google.gson.JsonObject
import com.google.gson.JsonParser
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlin.math.min
import org.eclipse.paho.client.mqttv3.*
import org.eclipse.paho.client.mqttv3.persist.MemoryPersistence

/**
 * MQTT 连接管理器（纯 Paho JVM client + 协程，不依赖 Android Service）
 *
 * 避免 Paho Android Service 在 API 34+ 的兼容问题。
 */
class MqttManager(context: Context, clientSuffix: String = "") {

    companion object {
        private const val TAG = "HelmetMqtt"
        const val BROKER_URL = "tcp://frp-run.com:18830"
        const val DEVICE_ID = "helmet_001"
        const val DEVICE_KEY = "helmet_key_001"
    }

    private val clientId = "android_monitor$clientSuffix"

    private val prefs = context.getSharedPreferences("helmet_cache", Context.MODE_PRIVATE)
    private val gson = Gson()
    private var client: MqttClient? = null
    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())

    // ---- 可观察状态 ----
    private val _latestData = MutableStateFlow<HelmetData?>(loadCached())
    val latestData: StateFlow<HelmetData?> = _latestData

    private val _alerts = MutableStateFlow<List<AlertItem>>(emptyList())
    val alerts: StateFlow<List<AlertItem>> = _alerts

    private fun loadCached(): HelmetData? {
        val json = prefs.getString("data", null) ?: return null
        return try { gson.fromJson(json, HelmetData::class.java) } catch (_: Exception) { null }
    }

    private val _connected = MutableStateFlow(false)
    val connected: StateFlow<Boolean> = _connected

    private var reconnectJob: Job? = null
    private var alertCallback: ((AlertItem) -> Unit)? = null
    private var dataCallback: ((HelmetData) -> Unit)? = null

    /** 注册数据接收回调（用于文件写入等外部操作） */
    fun onDataReceived(callback: (HelmetData) -> Unit) {
        dataCallback = callback
    }

    fun connect(onAlert: ((AlertItem) -> Unit)? = null) {
        alertCallback = onAlert
        if (_connected.value && client?.isConnected == true) return

        reconnectJob?.cancel()
        reconnectJob = scope.launch {
            var retryDelay = 2000L
            while (isActive) {
                try {
                    val c = MqttClient(BROKER_URL, clientId, MemoryPersistence())
                    client = c
                    c.setCallback(createCallback())
                    c.connect(MqttConnectOptions().apply {
                        userName = DEVICE_ID; password = DEVICE_KEY.toCharArray()
                        keepAliveInterval = 30; isCleanSession = true
                        connectionTimeout = 10
                    })
                    c.subscribe(
                        arrayOf("helmet/$DEVICE_ID/attributes", "helmet/$DEVICE_ID/data/processed",
                                "helmet/$DEVICE_ID/alerts", "helmet/$DEVICE_ID/events"),
                        intArrayOf(0, 0, 1, 0))
                    Log.i(TAG, "已连接")
                    _connected.value = true
                    retryDelay = 2000L
                    while (c.isConnected && isActive) { delay(1000) }
                    _connected.value = false
                } catch (e: Exception) {
                    Log.e(TAG, "连接失败: ${e.message}")
                    _connected.value = false
                }
                if (!isActive) break
                Log.i(TAG, "${retryDelay / 1000}s 后重连...")
                delay(retryDelay)
                retryDelay = min(retryDelay * 2, 60000L)
            }
        }
    }

    fun disconnect() {
        reconnectJob?.cancel()
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
        val obj = try { JsonParser.parseString(payload).asJsonObject } catch (_: Exception) {
            Log.w(TAG, "JSON 解析失败: ${payload.take(100)}")
            return
        }
        Log.d(TAG, "收到: $topic → ${payload.take(80)}")
        when {
            topic.endsWith("/alerts")     -> handleAlert(obj)
            topic.endsWith("/attributes") -> handleAttributes(obj)
            topic.endsWith("/events")     -> Log.d(TAG, "事件: $payload")
        }
    }

    private fun handleAttributes(obj: JsonObject) {
        // 合并缓存：新字段覆盖旧值，未传的保留上次值
        val prev = _latestData.value
        val merged = HelmetData(
            temperature = obj.get("temperature")?.asDouble ?: prev?.temperature,
            heartRate = obj.get("heart_rate")?.asDouble?.toInt() ?: prev?.heartRate,
            pressure = obj.get("pressure")?.asInt ?: prev?.pressure,
            longitude = obj.get("longitude")?.asDouble ?: prev?.longitude,
            latitude = obj.get("latitude")?.asDouble ?: prev?.latitude,
            ax = obj.get("ax")?.asFloat ?: prev?.ax,
            ay = obj.get("ay")?.asFloat ?: prev?.ay,
            az = obj.get("az")?.asFloat ?: prev?.az,
            gx = obj.get("gx")?.asFloat ?: prev?.gx,
            gy = obj.get("gy")?.asFloat ?: prev?.gy,
            gz = obj.get("gz")?.asFloat ?: prev?.gz,
        )
        _latestData.value = merged
        prefs.edit().putString("data", gson.toJson(merged)).apply()
        dataCallback?.invoke(merged)
    }

    private fun handleAlert(obj: JsonObject) {
        val arr = obj.getAsJsonArray("alerts") ?: run {
            Log.w(TAG, "告警 JSON 缺少 alerts 数组: ${obj.toString().take(100)}")
            return
        }
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
        if (newAlerts.isEmpty()) return
        _alerts.value = (_alerts.value + newAlerts).takeLast(50)
        newAlerts.forEach { alertCallback?.invoke(it) }
    }
}

// ---- 数据模型 ----

data class HelmetData(
    val temperature: Double?,
    val heartRate: Int?,
    val pressure: Int?,
    val longitude: Double?,
    val latitude: Double?,
    // 六轴 IMU
    val ax: Float?,
    val ay: Float?,
    val az: Float?,
    val gx: Float?,
    val gy: Float?,
    val gz: Float?,
)

data class AlertItem(
    val type: String,
    val field: String,
    val msg: String,
    val value: Double?,
    val threshold: Double?,
)
