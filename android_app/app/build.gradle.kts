plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "com.helmet.monitor"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.helmet.monitor"
        minSdk = 26
        targetSdk = 34
        versionCode = 1
        versionName = "1.0.0"
    }

    buildFeatures {
        compose = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    // ---- 高德轻量 3D 地图 SDK ----
    implementation(fileTree(mapOf("dir" to "libs", "include" to listOf("*.jar"))))

    // ---- MQTT (Eclipse Paho JVM client — 纯协程，不依赖 Android Service) ----
    implementation("org.eclipse.paho:org.eclipse.paho.client.mqttv3:1.2.5")

    // ---- Jetpack Compose (Google 官方 UI 框架) ----
    val composeBom = platform("androidx.compose:compose-bom:2024.06.00")
    implementation(composeBom)
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-graphics")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.activity:activity-compose:1.9.0")

    // ---- 生命周期 (ViewModel) ----
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.2")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.2")

    // ---- JSON (Google Gson — 开源) ----
    implementation("com.google.code.gson:gson:2.11.0")

    // ---- 本地持久化 (可选，暂存告警历史) ----
    implementation("androidx.datastore:datastore-preferences:1.1.1")

    // ---- 调试 ----
    debugImplementation("androidx.compose.ui:ui-tooling")
}
