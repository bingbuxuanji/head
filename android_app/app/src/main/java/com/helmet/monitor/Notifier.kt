package com.helmet.monitor

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat

/**
 * 告警通知管理器（Android 原生通知 API）
 *
 * 每次收到 MQTT 告警 → 弹通知栏，点击通知回到 App。
 */
class Notifier(private val context: Context) {

    companion object {
        const val CHANNEL_ID = "helmet_alerts"
        const val CHANNEL_NAME = "头盔告警"
    }

    init {
        // 创建通知渠道（Android 8.0+ 必须）
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID, CHANNEL_NAME,
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "智能头盔实时告警"
                enableVibration(true)
            }
            context.getSystemService(NotificationManager::class.java)
                ?.createNotificationChannel(channel)
        }
    }

    fun show(alert: AlertItem) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED) {
                // 权限未就绪时用 Toast 兜底，不静默丢失
                android.widget.Toast.makeText(context, "⚠ ${alert.msg}", android.widget.Toast.LENGTH_LONG).show()
                return
            }
        }

        // 点击通知 → 打开 MainActivity
        val intent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val pending = PendingIntent.getActivity(
            context, 0, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val title = when (alert.field) {
            "temperature" -> "🌡 体温异常"
            "heart_rate"  -> "❤ 心率异常"
            "velocity"    -> "🏃 速度异常"
            else          -> "⚠ ${alert.field} 告警"
        }

        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_dialog_alert)
            .setContentTitle(title)
            .setContentText(alert.msg)
            .setStyle(NotificationCompat.BigTextStyle().bigText(alert.msg))
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setContentIntent(pending)
            .build()

        NotificationManagerCompat.from(context)
            .notify(alert.hashCode(), notification)
    }
}
