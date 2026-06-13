package com.helmet.monitor.ui

import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView
import com.amap.api.maps.AMap
import com.amap.api.maps.CameraUpdateFactory
import com.amap.api.maps.MapView
import com.amap.api.maps.MapsInitializer
import com.amap.api.maps.model.LatLng
import com.amap.api.maps.model.MarkerOptions
import com.amap.api.maps.model.PolylineOptions

private const val AMAP_KEY = "9522dee5bbc65c319159418a302ef3a9"

@Composable
fun MapViewComposable(
    latitude: Double?,
    longitude: Double?,
    modifier: Modifier = Modifier,
) {
    val lat = latitude ?: 30.65
    val lng = longitude ?: 104.07
    val hasGps = latitude != null && longitude != null

    var aMap by remember { mutableStateOf<AMap?>(null) }
    var marker by remember { mutableStateOf<com.amap.api.maps.model.Marker?>(null) }
    var polyline by remember { mutableStateOf<com.amap.api.maps.model.Polyline?>(null) }
    val track = remember { mutableListOf<LatLng>() }
    var mapViewRef by remember { mutableStateOf<MapView?>(null) }
    var ready by remember { mutableStateOf(false) }

    // GPS 更新 → 移动标记 + 地图跟随
    LaunchedEffect(lat, lng) {
        if (!ready || aMap == null) return@LaunchedEffect
        val pt = LatLng(lat, lng)
        marker?.position = pt
        if (hasGps) {
            aMap!!.animateCamera(CameraUpdateFactory.newLatLng(pt))
            track.add(pt)
            if (track.size > 30) track.removeFirst()
            polyline?.points = track.toList()
        }
    }

    AndroidView(
        factory = { ctx ->
            MapsInitializer.setApiKey(AMAP_KEY)
            MapView(ctx).apply {
                onCreate(null)
                getMapAsyn(object : AMap.OnMapReadyListener {
                    override fun onMapReady(map: AMap) {
                        aMap = map
                        val center = LatLng(lat, lng)
                        marker = map.addMarker(MarkerOptions().position(center).title("设备"))
                        track.add(center)
                        polyline = map.addPolyline(
                            PolylineOptions().addAll(track).color(-0xE68E30).width(8f)
                        )
                        map.moveCamera(CameraUpdateFactory.newLatLngZoom(center, 14f))
                        ready = true
                    }
                })
            }.also { mapViewRef = it }
        },
        update = { mapView ->
            mapView.onResume()  // Compose 重新组合时恢复
        },
        modifier = modifier
    )

    DisposableEffect(Unit) {
        onDispose { mapViewRef?.onDestroy() }
    }
}
