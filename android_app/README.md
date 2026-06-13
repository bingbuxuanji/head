# 头盔监控 Android App

基于开源方案搭建，未造轮子。

## 技术栈

| 组件 | 方案 | 来源 |
|------|------|------|
| MQTT 客户端 | Eclipse Paho Android | eclipse.org 官方 |
| UI 框架 | Jetpack Compose + Material 3 | Google 官方 |
| JSON 解析 | Gson | Google 开源 |
| 通知推送 | Android Notification API | 系统内置 |

## 启动

### 1. 安装 Android Studio

下载: https://developer.android.com/studio
安装时勾选 Android SDK (API 34)。

### 2. 打开项目

```
File → Open → 选择 android_app 文件夹
```

Gradle sync 自动下载依赖（Paho MQTT、Compose 等）。

### 3. 创建模拟器

```
Tools → Device Manager → Create Device
推荐: Pixel 6, API 34
```

### 4. 运行

```
点击绿色 ▶ Run 按钮，选择模拟器
```

## 模拟器网络

模拟器内访问宿主机 MQTT Broker 用特殊 IP：

| 场景 | MqttManager.BROKER_URL |
|------|----------------------|
| 本地调试 | `tcp://10.0.2.2:1883`（模拟器映射宿主机 localhost） |
| frp 穿透 | `tcp://frp-run.com:18830` |

当前默认: `tcp://10.0.2.2:1883`

## 功能

- ✅ 实时数据卡片（体温/心率/速度/GPS）
- ✅ 告警列表（红色高亮）
- ✅ 通知栏告警推送（Android 13+ 需授权）
- ✅ 连接状态指示灯
- ✅ Paho 自动重连
- ⬜ GPS 地图轨迹（下一阶段，接入 osmdroid）
- ⬜ 历史数据图表

## 文件结构

```
android_app/
├── build.gradle.kts              # 根构建脚本
├── settings.gradle.kts           # 项目设置
├── gradle.properties             # Gradle 配置
├── gradlew.bat                   # Windows 启动器
└── app/
    ├── build.gradle.kts          # App 模块（依赖声明）
    └── src/main/
        ├── AndroidManifest.xml   # 权限 + Service 声明
        ├── res/values/           # 字符串/主题资源
        └── java/com/helmet/monitor/
            ├── MainActivity.kt           # 入口
            ├── MqttManager.kt            # MQTT 连接管理
            ├── Notifier.kt               # 通知栏告警
            └── ui/
                └── DashboardScreen.kt    # Compose UI
```

## 调试流程

```
1. 双击 start_mqtt.bat 启动 MQTT Broker
2. python mqtt_server/debug_client.py 模拟设备上报
3. Android Studio → Run ▶ 在模拟器中查看实时数据
4. 在 MQTTX 中发送异常心率 190 → App 弹告警通知
```
