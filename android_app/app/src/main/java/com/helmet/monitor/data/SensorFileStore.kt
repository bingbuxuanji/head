package com.helmet.monitor.data

import android.content.Context
import com.google.gson.Gson
import com.google.gson.annotations.SerializedName
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.text.SimpleDateFormat
import java.util.*

/**
 * 本地 JSONL 文件存储 — 传感器数据 + GPS 轨迹
 *
 * 文件结构:
 *   filesDir/sensor/{yyyyMMdd}.jsonl  — 每行: {ts, temperature, heart_rate, velocity}
 *   filesDir/gps/{yyyyMMdd}.jsonl      — 每行: {ts, longitude, latitude}
 *
 * 用作趋势图表和轨迹回放的数据源，不依赖服务端存储。
 */
object SensorFileStore {

    private val gson = Gson()
    private val dateFormat = SimpleDateFormat("yyyyMMdd", Locale.US)

    // ---- 数据模型 ----

    data class SensorRecord(
        @SerializedName("ts") val timestamp: Long,
        val temperature: Double?,
        @SerializedName("heart_rate") val heartRate: Int?,
        val velocity: Double?,
    )

    data class GpsPoint(
        @SerializedName("ts") val timestamp: Long,
        val longitude: Double,
        val latitude: Double,
    )

    // ---- 写入 ----

    /** 追加一条传感器记录到当天文件 */
    suspend fun appendSensor(context: Context, record: SensorRecord) = withContext(Dispatchers.IO) {
        val dir = File(context.filesDir, "sensor")
        dir.mkdirs()
        val file = File(dir, "${dateFormat.format(Date(record.timestamp * 1000))}.jsonl")
        file.appendText(gson.toJson(record) + "\n")
    }

    /** 追加一条 GPS 坐标到当天文件 */
    suspend fun appendGps(context: Context, point: GpsPoint) = withContext(Dispatchers.IO) {
        val dir = File(context.filesDir, "gps")
        dir.mkdirs()
        val file = File(dir, "${dateFormat.format(Date(point.timestamp * 1000))}.jsonl")
        file.appendText(gson.toJson(point) + "\n")
    }

    // ---- 读取 ----

    /** 读取指定日期（yyyyMMdd）的传感器数据，全部返回 */
    suspend fun readSensors(context: Context, date: String): List<SensorRecord> = withContext(Dispatchers.IO) {
        val file = File(context.filesDir, "sensor/$date.jsonl")
        if (!file.exists()) return@withContext emptyList()
        file.readLines().mapNotNull { line ->
            try { gson.fromJson(line, SensorRecord::class.java) } catch (_: Exception) { null }
        }
    }

    /** 读取指定日期的 GPS 轨迹点集 */
    suspend fun readGpsTrack(context: Context, date: String): List<GpsPoint> = withContext(Dispatchers.IO) {
        val file = File(context.filesDir, "gps/$date.jsonl")
        if (!file.exists()) return@withContext emptyList()
        file.readLines().mapNotNull { line ->
            try { gson.fromJson(line, GpsPoint::class.java) } catch (_: Exception) { null }
        }
    }

    /** 列出有数据的日期（用于日期选择器） */
    suspend fun listSensorDates(context: Context): List<String> = withContext(Dispatchers.IO) {
        val dir = File(context.filesDir, "sensor")
        if (!dir.exists()) return@withContext emptyList()
        dir.listFiles()
            ?.filter { it.name.matches(Regex("\\d{8}\\.jsonl")) }
            ?.map { it.nameWithoutExtension }
            ?.sortedDescending()
            ?: emptyList()
    }

    /** 获取今天的日期字符串 */
    fun today(): String = dateFormat.format(Date())
}
