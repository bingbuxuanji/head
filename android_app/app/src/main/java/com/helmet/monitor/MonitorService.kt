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

class MonitorService : Service() {

    private lateinit var mqtt: MqttManager
    private var mediaPlayer: MediaPlayer? = null

    override fun onCreate() {
        super.onCreate()
        startForeground()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        mqtt = MqttManager(this, "_svc").apply {
            connect { alert -> showNotification(alert); playAlarm() }
        }
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
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
            // 音量拉到最大
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
                isLooping = true  // 循环播放直到用户操作
                prepare()
                start()
            }
            // 10 秒后自动停
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
