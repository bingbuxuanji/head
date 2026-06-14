package com.helmet.monitor

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/**
 * 开机自启 — 手机启动完成后自动拉起 MonitorService
 */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Intent.ACTION_BOOT_COMPLETED) {
            val serviceIntent = Intent(context, MonitorService::class.java)
            context.startService(serviceIntent)
        }
    }
}
