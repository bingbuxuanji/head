package com.helmet.monitor.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.helmet.monitor.AlertItem
import com.helmet.monitor.HelmetData
import com.helmet.monitor.MqttManager

/**
 * 主仪表盘 UI（Jetpack Compose + Material 3）
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DashboardScreen(mqtt: MqttManager) {
    val connected by mqtt.connected.collectAsState()
    val data by mqtt.latestData.collectAsState()
    val alerts by mqtt.alerts.collectAsState()

    // 本地变量副本：委托属性无法 smart-cast，用 val 拷贝后 Kotlin 可以安全推断非空
    val helmet = data

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("头盔监控") },
                actions = {
                    // 连接状态指示灯
                    Box(
                        modifier = Modifier
                            .padding(end = 12.dp)
                            .size(12.dp)
                            .clip(CircleShape)
                            .background(if (connected) Color(0xFF4CAF50) else Color(0xFFF44336))
                    )
                    Text(
                        text = if (connected) "已连接" else "未连接",
                        fontSize = 12.sp,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(end = 16.dp)
                    )
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.primaryContainer
                )
            )
        }
    ) { padding ->
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
            contentPadding = PaddingValues(vertical = 12.dp)
        ) {
            // ---- 数据卡片 ----
            item {
                Text(
                    "实时数据",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.padding(bottom = 4.dp)
                )
            }

            item {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    DataCard(
                        modifier = Modifier.weight(1f),
                        label = "体温",
                        value = data?.temperature?.let { "${"%.1f".format(it)}°C" } ?: "--",
                        icon = Icons.Default.Thermostat,
                        valueColor = helmet?.temperature?.let {
                            if (it > 37.5) Color(0xFFE53935) else Color(0xFF43A047)
                        } ?: Color.Gray
                    )
                    DataCard(
                        modifier = Modifier.weight(1f),
                        label = "心率",
                        value = data?.heartRate?.let { "$it BPM" } ?: "--",
                        icon = Icons.Default.Favorite,
                        valueColor = helmet?.heartRate?.let {
                            when {
                                it > 150 -> Color(0xFFE53935)
                                it > 100 -> Color(0xFFFFA000)
                                else -> Color(0xFF43A047)
                            }
                        } ?: Color.Gray
                    )
                }
            }

            item {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    DataCard(
                        modifier = Modifier.weight(1f),
                        label = "速度",
                        value = data?.velocity?.let { "${"%.1f".format(it)} m/s" } ?: "--",
                        icon = Icons.Default.Speed,
                        valueColor = MaterialTheme.colorScheme.primary
                    )
                    DataCard(
                        modifier = Modifier.weight(1f),
                        label = "GPS",
                        value = helmet?.let { h ->
                            if (h.latitude != null && h.longitude != null)
                                "${"%.4f".format(h.latitude)} ${"%.4f".format(h.longitude)}"
                            else "--"
                        } ?: "--",
                        icon = Icons.Default.LocationOn,
                        valueColor = MaterialTheme.colorScheme.primary,
                        smallText = true
                    )
                }
            }

            // ---- 地图 ----
            item {
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    "实时位置",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.padding(bottom = 4.dp)
                )
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
                ) {
                    MapViewComposable(
                        latitude = helmet?.latitude,
                        longitude = helmet?.longitude,
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(280.dp)
                    )
                }
            }

            // ---- 告警列表 ----
            item {
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    "告警记录 (${alerts.size})",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.padding(bottom = 4.dp)
                )
            }

            if (alerts.isEmpty()) {
                item {
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        colors = CardDefaults.cardColors(
                            containerColor = MaterialTheme.colorScheme.surfaceVariant
                        )
                    ) {
                        Text(
                            "暂无告警",
                            modifier = Modifier.padding(24.dp),
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            style = MaterialTheme.typography.bodyMedium
                        )
                    }
                }
            }

            items(alerts.reversed()) { alert ->
                AlertCard(alert)
            }
        }
    }
}

/**
 * 数据卡片组件
 */
@Composable
fun DataCard(
    modifier: Modifier = Modifier,
    label: String,
    value: String,
    icon: ImageVector,
    valueColor: Color,
    smallText: Boolean = false,
) {
    Card(
        modifier = modifier,
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surface
        ),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Icon(
                imageVector = icon,
                contentDescription = label,
                tint = valueColor,
                modifier = Modifier.size(28.dp)
            )
            Spacer(modifier = Modifier.height(8.dp))
            Text(
                text = value,
                fontSize = if (smallText) 13.sp else 20.sp,
                fontWeight = FontWeight.Bold,
                color = valueColor
            )
            Spacer(modifier = Modifier.height(2.dp))
            Text(
                text = label,
                fontSize = 12.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
    }
}

/**
 * 告警卡片
 */
@Composable
fun AlertCard(alert: AlertItem) {
    val icon: ImageVector = when (alert.field) {
        "temperature" -> Icons.Default.Thermostat
        "heart_rate"  -> Icons.Default.Favorite
        else          -> Icons.Default.Warning
    }

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = Color(0xFFFFEBEE)  // 浅红背景
        ),
        shape = RoundedCornerShape(8.dp)
    ) {
        Row(
            modifier = Modifier
                .padding(12.dp)
                .fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(
                imageVector = icon,
                contentDescription = null,
                tint = Color(0xFFE53935),
                modifier = Modifier.size(24.dp)
            )
            Spacer(modifier = Modifier.width(12.dp))
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = when (alert.field) {
                        "temperature" -> "体温异常"
                        "heart_rate"  -> "心率异常"
                        "velocity"    -> "速度异常"
                        else          -> alert.field
                    },
                    fontWeight = FontWeight.Bold,
                    fontSize = 14.sp,
                    color = Color(0xFFC62828)
                )
                Text(
                    text = alert.msg,
                    fontSize = 12.sp,
                    color = Color(0xFFB71C1C)
                )
                if (alert.value != null && alert.threshold != null) {
                    Text(
                        text = "当前: ${alert.value} | 阈值: ${alert.threshold}",
                        fontSize = 11.sp,
                        color = Color.Gray
                    )
                }
            }
        }
    }
}
