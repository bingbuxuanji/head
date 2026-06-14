package com.helmet.monitor

import android.app.AlarmManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build

/**
 * 看门狗闹钟 — 每 5 分钟检查 MonitorService 是否存活，死了就拉起来
 *
 * 这是对抗系统杀进程的最后防线。与前台服务 + 开机自启配合，
 * 达到 QQ 级别的消息到达率。
 */
class WatchdogReceiver : BroadcastReceiver() {

    companion object {
        private const val REQUEST_CODE = 9247
        private const val INTERVAL_MS = 5 * 60 * 1000L  // 5 分钟

        /** 设置下一次闹钟 */
        fun schedule(context: Context) {
            val alarm = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
            val intent = Intent(context, WatchdogReceiver::class.java)
            val pending = PendingIntent.getBroadcast(
                context, REQUEST_CODE, intent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                if (alarm.canScheduleExactAlarms()) {
                    alarm.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP,
                        System.currentTimeMillis() + INTERVAL_MS, pending)
                }
            } else {
                alarm.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP,
                    System.currentTimeMillis() + INTERVAL_MS, pending)
            }
        }

        fun cancel(context: Context) {
            val alarm = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
            val intent = Intent(context, WatchdogReceiver::class.java)
            val pending = PendingIntent.getBroadcast(
                context, REQUEST_CODE, intent,
                PendingIntent.FLAG_NO_CREATE or PendingIntent.FLAG_IMMUTABLE
            )
            pending?.let { alarm.cancel(it) }
        }
    }

    override fun onReceive(context: Context, intent: Intent) {
        // 检查 Service 是否存活，死了就拉起
        if (!MonitorService.isRunning) {
            val serviceIntent = Intent(context, MonitorService::class.java)
            context.startService(serviceIntent)
            android.util.Log.w("Watchdog", "MonitorService 已死亡，已重新拉起")
        }

        // 安排下一次检查
        schedule(context)
    }
}
