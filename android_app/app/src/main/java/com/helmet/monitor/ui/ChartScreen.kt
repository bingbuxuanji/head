package com.helmet.monitor.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.helmet.monitor.data.SensorFileStore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.*

// ---- 图表主界面 ----

@Composable
fun ChartScreen() {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    var availableDates by remember { mutableStateOf<List<String>>(emptyList()) }
    var selectedDate by remember { mutableStateOf(SensorFileStore.today()) }
    var sensorData by remember { mutableStateOf<List<SensorFileStore.SensorRecord>>(emptyList()) }
    var gpsTrack by remember { mutableStateOf<List<SensorFileStore.GpsPoint>>(emptyList()) }
    var showGpsTrack by remember { mutableStateOf(false) }
    var tappedPoint by remember { mutableStateOf<Pair<Long, String>?>(null) } // 点触提示

    // 加载可用日期
    LaunchedEffect(Unit) {
        availableDates = withContext(Dispatchers.IO) { SensorFileStore.listSensorDates(context) }
        if (availableDates.isEmpty()) availableDates = listOf(SensorFileStore.today())
        if (selectedDate !in availableDates) selectedDate = availableDates.firstOrNull() ?: SensorFileStore.today()
    }

    // 日期变化时加载数据
    LaunchedEffect(selectedDate) {
        sensorData = withContext(Dispatchers.IO) { SensorFileStore.readSensors(context, selectedDate) }
        gpsTrack = withContext(Dispatchers.IO) { SensorFileStore.readGpsTrack(context, selectedDate) }
        tappedPoint = null
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        // 日期选择器
        Text("趋势图表", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)

        if (availableDates.size > 1) {
            ScrollableDateSelector(
                dates = availableDates,
                selected = selectedDate,
                onSelect = { selectedDate = it }
            )
        }

        if (sensorData.isEmpty()) {
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)
            ) {
                Text(
                    "暂无 ${selectedDate} 的数据\n等待设备上报...",
                    modifier = Modifier.padding(24.dp),
                    style = MaterialTheme.typography.bodyLarge,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        } else {
            // 体温折线图
            ChartCard(
                title = "🌡 体温趋势",
                color = Color(0xFFE53935),
                yLabel = "°C",
                yRange = 35.0f..42.0f,
                data = sensorData.mapNotNull { r ->
                    r.temperature?.let { r.timestamp to it }
                },
                tappedPoint = tappedPoint
            )

            // 心率折线图
            ChartCard(
                title = "💓 心率趋势",
                color = Color(0xFFFF6D00),
                yLabel = "BPM",
                yRange = 40f..200f,
                data = sensorData.mapNotNull { r ->
                    r.heartRate?.toFloat()?.let { r.timestamp to it }
                },
                tappedPoint = tappedPoint
            )

            // 速度折线图
            ChartCard(
                title = "🚴 速度趋势",
                color = Color(0xFF1976D2),
                yLabel = "m/s",
                yRange = 0f..20f,
                data = sensorData.mapNotNull { r ->
                    r.velocity?.toFloat()?.let { r.timestamp to it }
                },
                tappedPoint = tappedPoint
            )
        }

        // GPS 轨迹查看
        Spacer(modifier = Modifier.height(4.dp))
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text("🗺 GPS 轨迹", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
            if (gpsTrack.isNotEmpty()) {
                TextButton(onClick = { showGpsTrack = !showGpsTrack }) {
                    Text(if (showGpsTrack) "收起" else "展开 (${gpsTrack.size} 个点)")
                }
            }
        }

        if (showGpsTrack && gpsTrack.isNotEmpty()) {
            GpsTrackCard(track = gpsTrack)
        }
    }
}

// ---- Canvas 折线图 ----

@Composable
fun ChartCard(
    title: String,
    color: Color,
    yLabel: String,
    yRange: ClosedFloatingPointRange<Float>,
    data: List<Pair<Long, Float>>,  // (timestamp, value)
    tappedPoint: Pair<Long, String>?,  // 外部点触状态（本组件暂不互联）
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
        shape = RoundedCornerShape(12.dp)
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            Text(title, fontWeight = FontWeight.SemiBold, fontSize = 14.sp,
                modifier = Modifier.padding(bottom = 4.dp))

            if (data.size < 2) {
                Text("数据不足（需至少 2 个点）", fontSize = 12.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(vertical = 16.dp))
            } else {
                LineChartCanvas(
                    data = data,
                    lineColor = color,
                    yRange = yRange,
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(180.dp)
                )
                // X 轴时间标注
                val timeFmt = SimpleDateFormat("HH:mm", Locale.getDefault())
                Row(
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 8.dp),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Text(timeFmt.format(Date(data.first().first * 1000)), fontSize = 10.sp,
                        color = Color.Gray)
                    Text(timeFmt.format(Date(data.last().first * 1000)), fontSize = 10.sp,
                        color = Color.Gray)
                }
            }
        }
    }
}

@Composable
fun LineChartCanvas(
    data: List<Pair<Long, Float>>,
    lineColor: Color,
    yRange: ClosedFloatingPointRange<Float>,
    modifier: Modifier
) {
    var tapIndex by remember { mutableStateOf(-1) }

    Canvas(
        modifier = modifier
            .pointerInput(data) {
                detectTapGestures { offset ->
                    if (data.isEmpty()) return@detectTapGestures
                    val stepX = size.width / (data.size - 1).coerceAtLeast(1)
                    val idx = ((offset.x / stepX).toInt()).coerceIn(0, data.size - 1)
                    tapIndex = if (tapIndex == idx) -1 else idx
                }
            }
    ) {
        if (data.isEmpty()) return@Canvas

        val w = size.width
        val h = size.height
        val padLeft = 40f   // Y 轴标签空间
        val padRight = 12f
        val padTop = 16f
        val padBot = 20f
        val chartW = w - padLeft - padRight
        val chartH = h - padTop - padBot

        val range = yRange.endInclusive - yRange.start
        if (range <= 0f) return@Canvas

        // Y 轴网格线 + 标签（3 条）
        val ySteps = 3
        for (i in 0..ySteps) {
            val yVal = yRange.start + range * i / ySteps
            val y = padTop + chartH * (1f - (yVal - yRange.start) / range)

            // 网格线
            drawLine(
                color = Color.LightGray,
                start = Offset(padLeft, y),
                end = Offset(w - padRight, y),
                strokeWidth = 0.5f
            )

            // Y 标签
            drawContext.canvas.nativeCanvas.drawText(
                "${"%.1f".format(yVal)}${
                    when {
                        yRange.endInclusive <= 50 -> "°C"
                        yRange.endInclusive <= 300 -> ""
                        else -> ""
                    }
                }",
                4f, y + 4f,
                android.graphics.Paint().apply {
                    color = android.graphics.Color.GRAY
                    textSize = 22f
                    isAntiAlias = true
                }
            )
        }

        // 映射数据点到画布坐标
        val points = data.mapIndexed { i, (ts, v) ->
            val x = padLeft + chartW * i / (data.size - 1).coerceAtLeast(1)
            val y = padTop + chartH * (1f - (v - yRange.start) / range)
            Offset(x, y)
        }

        // 折线
        if (points.size >= 2) {
            val path = Path().apply {
                moveTo(points.first().x, points.first().y)
                for (i in 1 until points.size) {
                    lineTo(points[i].x, points[i].y)
                }
            }
            drawPath(
                path = path,
                color = lineColor,
                style = Stroke(width = 3f, cap = StrokeCap.Round, join = StrokeJoin.Round)
            )
        }

        // 数据点（点稀疏时才画）
        if (points.size <= 60) {
            points.forEach { pt ->
                drawCircle(color = lineColor, radius = 3f, center = pt)
            }
        }

        // 最后一个点高亮
        if (points.isNotEmpty()) {
            val last = points.last()
            drawCircle(color = Color.White, radius = 4f, center = last)
            drawCircle(color = lineColor, radius = 8f, center = last, style = Stroke(width = 2f))
        }

        // 点击高亮
        if (tapIndex in points.indices) {
            val pt = points[tapIndex]
            drawCircle(color = lineColor, radius = 10f, center = pt, style = Stroke(width = 2.5f))

            val (ts, v) = data[tapIndex]
            val timeStr = SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date(ts * 1000))
            val label = "$timeStr  ${"%.1f".format(v)}"
            drawContext.canvas.nativeCanvas.drawText(
                label,
                pt.x + 12f,
                pt.y - 8f,
                android.graphics.Paint().apply {
                    color = android.graphics.Color.DKGRAY
                    textSize = 24f
                    isAntiAlias = true
                    isFakeBoldText = true
                }
            )
        }
    }
}

// ---- GPS 轨迹卡片 ----

@Composable
fun GpsTrackCard(track: List<SensorFileStore.GpsPoint>) {
    val timeFmt = SimpleDateFormat("HH:mm:ss", Locale.getDefault())

    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            // 摘要
            if (track.isNotEmpty()) {
                val first = track.first()
                val last = track.last()
                Text("起点: ${"%.6f".format(first.latitude)}, ${"%.6f".format(first.longitude)}  @ ${timeFmt.format(Date(first.timestamp * 1000))}",
                    fontSize = 11.sp, color = Color.Gray)
                Text("终点: ${"%.6f".format(last.latitude)}, ${"%.6f".format(last.longitude)}  @ ${timeFmt.format(Date(last.timestamp * 1000))}",
                    fontSize = 11.sp, color = Color.Gray)
                Spacer(modifier = Modifier.height(4.dp))
                Text("共 ${track.size} 个轨迹点", fontSize = 11.sp, color = Color.Gray,
                    modifier = Modifier.padding(bottom = 8.dp))
            }

            // 轨迹点列表（最多展示最近 50 条）
            val displayList = track.takeLast(50)
            displayList.forEachIndexed { i, pt ->
                Row(
                    modifier = Modifier.fillMaxWidth().padding(vertical = 2.dp),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Text("#${track.size - displayList.size + i + 1}", fontSize = 11.sp, color = Color.DarkGray,
                        modifier = Modifier.width(32.dp))
                    Text("${"%.6f".format(pt.latitude)}, ${"%.6f".format(pt.longitude)}",
                        fontSize = 11.sp, color = Color.DarkGray)
                    Text(timeFmt.format(Date(pt.timestamp * 1000)), fontSize = 10.sp, color = Color.Gray)
                }
                if (i < displayList.size - 1) {
                    HorizontalDivider(thickness = 0.5.dp, color = Color.LightGray)
                }
            }
        }
    }
}

// ---- 日期选择器 ----

@Composable
fun ScrollableDateSelector(
    dates: List<String>,
    selected: String,
    onSelect: (String) -> Unit
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        dates.take(7).forEach { date ->
            val display = try {
                val sdf = SimpleDateFormat("yyyyMMdd", Locale.getDefault())
                val parsed = sdf.parse(date)
                SimpleDateFormat("MM/dd", Locale.getDefault()).format(parsed!!)
            } catch (_: Exception) { date }

            val isSelected = date == selected
            FilterChip(
                selected = isSelected,
                onClick = { onSelect(date) },
                label = { Text(display, fontSize = 12.sp) },
                colors = FilterChipDefaults.filterChipColors(
                    selectedContainerColor = MaterialTheme.colorScheme.primaryContainer
                )
            )
        }
    }
}
