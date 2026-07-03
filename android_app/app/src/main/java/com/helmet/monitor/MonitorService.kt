package com.helmet.monitor

import android.app.*
import android.content.Context
import android.content.Intent
import android.media.AudioAttributes
import android.media.AudioManager
import android.media.MediaPlayer
import android.media.RingtoneManager
import android.net.Uri
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import com.helmet.monitor.data.SensorFileStore
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

/**
 * 前台服务 — 独占 MQTT 连接，熄屏后持续运行
 *
 * 职责：
 * - 维持唯一 MQTT 连接（不再与 Activity 分用两条连接）
 * - 数据写入 DataRepository（UI 层读取）
 * - 数据写入本地 JSONL 文件（趋势图表来源）
 * - 告警通知 + 系统闹铃剧响
 */
class MonitorService : Service() {

    companion object {
        @Volatile var isRunning = false
    }

    private lateinit var mqtt: MqttManager
    private var mediaPlayer: MediaPlayer? = null
    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())

    override fun onCreate() {
        super.onCreate()
        startForeground()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        isRunning = true
        WatchdogReceiver.schedule(this)
        mqtt = MqttManager(this).apply {
            // 连接状态 → DataRepository
            scope.launch { connected.collect { DataRepository.setConnected(it) } }

            // 数据回调 → DataRepository + 本地文件
            onDataReceived { data ->
                DataRepository.updateData(data)
                val now = System.currentTimeMillis() / 1000
                scope.launch {
                    SensorFileStore.appendSensor(applicationContext, SensorFileStore.SensorRecord(
                        timestamp = now, temperature = data.temperature,
                        heartRate = data.heartRate, pressure = data.pressure,
                        ax = data.ax, ay = data.ay, az = data.az,
                        gx = data.gx, gy = data.gy, gz = data.gz))
                    if (data.longitude != null && data.latitude != null) {
                        SensorFileStore.appendGps(applicationContext, SensorFileStore.GpsPoint(
                            timestamp = now, longitude = data.longitude, latitude = data.latitude))
                    }
                }
            }

            // 告警回调 → DataRepository + 通知 + 闹铃
            connect { alert ->
                DataRepository.addAlerts(listOf(alert))
                showNotification(alert)
                playAlarm()
            }
        }
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        isRunning = false
        WatchdogReceiver.cancel(this)
        mqtt.disconnect()
        mediaPlayer?.release()
        super.onDestroy()
    }

    private fun startForeground() {
        val channelId = "monitor_service"
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationManager::class.java.let {
                getSystemService(it)?.createNotificationChannel(
                    NotificationChannel(channelId, "后台监控", NotificationManager.IMPORTANCE_LOW)
                )
            }
        }
        val notification = NotificationCompat.Builder(this, channelId)
            .setContentTitle("头盔监控运行中")
            .setContentText("正在接收设备数据...")
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setOngoing(true)
            .build()
        startForeground(1, notification)
    }

    private fun showNotification(alert: AlertItem) {
        val chId = "helmet_alerts"
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            getSystemService(NotificationManager::class.java)?.createNotificationChannel(
                NotificationChannel(chId, "头盔告警", NotificationManager.IMPORTANCE_HIGH).apply {
                    enableVibration(true)
                }
            )
        }
        val intent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val pending = PendingIntent.getActivity(this, 0, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val n = NotificationCompat.Builder(this, chId)
            .setSmallIcon(android.R.drawable.ic_dialog_alert)
            .setContentTitle(alert.msg)
            .setContentText("${alert.field}: ${alert.value} | 阈值: ${alert.threshold}")
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setContentIntent(pending)
            .build()
        NotificationManagerCompat.from(this).notify(alert.hashCode(), n)
    }

    private fun playAlarm() {
        try {
            val am = getSystemService(Context.AUDIO_SERVICE) as AudioManager
            am.setStreamVolume(AudioManager.STREAM_ALARM, am.getStreamMaxVolume(AudioManager.STREAM_ALARM), 0)

            mediaPlayer?.release()
            val alarmUri: Uri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM)
            mediaPlayer = MediaPlayer().apply {
                setDataSource(this@MonitorService, alarmUri)
                setAudioAttributes(AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ALARM)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                    .build())
                isLooping = true
                prepare()
                start()
            }
            android.os.Handler(mainLooper).postDelayed({ stopAlarm() }, 10000)
        } catch (e: Exception) {
            android.util.Log.e("MonitorService", "Alarm error: ${e.message}")
        }
    }

    private fun stopAlarm() {
        mediaPlayer?.apply { if (isPlaying) stop(); release() }
        mediaPlayer = null
    }
}
