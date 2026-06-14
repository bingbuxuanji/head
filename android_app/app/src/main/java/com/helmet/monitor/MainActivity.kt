package com.helmet.monitor

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.remember
import androidx.compose.ui.graphics.Color
import androidx.core.content.ContextCompat
import com.helmet.monitor.data.SensorFileStore
import com.helmet.monitor.ui.DashboardScreen
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

/**
 * 主 Activity — 智能头盔 MQTT 监控 App
 *
 * 基于 Jetpack Compose + Eclipse Paho MQTT（均为开源方案）。
 */
class MainActivity : ComponentActivity() {

    private val mqtt by lazy { MqttManager(this) }
    private val notifier by lazy { Notifier(this) }

    // Android 13+ 通知权限请求
    private val notificationPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (!granted) {
            Toast.makeText(this, "通知权限未授予，告警不会弹通知栏", Toast.LENGTH_LONG).show()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // 启动后台保活 + 告警 Service
        startService(Intent(this, MonitorService::class.java))

        requestNotificationPermission()

        // 收到传感器/GPS 数据后自动写入本地 JSONL 文件
        val appContext = applicationContext
        mqtt.onDataReceived { data ->
            val now = System.currentTimeMillis() / 1000
            CoroutineScope(Dispatchers.IO).launch {
                SensorFileStore.appendSensor(appContext, SensorFileStore.SensorRecord(
                    timestamp = now,
                    temperature = data.temperature,
                    heartRate = data.heartRate,
                    velocity = data.velocity,
                ))
                if (data.longitude != null && data.latitude != null) {
                    SensorFileStore.appendGps(appContext, SensorFileStore.GpsPoint(
                        timestamp = now,
                        longitude = data.longitude,
                        latitude = data.latitude,
                    ))
                }
            }
        }

        // 启动 Compose UI
        setContent {
            MaterialTheme(
                colorScheme = lightColorScheme(
                    primary = Color(0xFF1976D2),
                    secondary = Color(0xFF43A047),
                    error = Color(0xFFE53935),
                )
            ) {
                val mqttRef = remember { mqtt }
                DashboardScreen(mqttRef)
            }
        }
    }

    override fun onStart() {
        super.onStart()
        try {
            mqtt.connect { alert -> notifier.show(alert) }
        } catch (e: Exception) {
            android.util.Log.e("HelmetApp", "MQTT connect error: ${e.message}", e)
        }
    }

    override fun onStop() {
        super.onStop()
    }

    override fun onDestroy() {
        super.onDestroy()
        try {
            mqtt.disconnect()
        } catch (_: Exception) {}
    }

    private fun requestNotificationPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED
            ) {
                notificationPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
            }
        }
    }
}
