import request
from machine import UART


class Point:
    """路径点，包含经纬度信息"""
    def __init__(self, longitude, latitude, index=None):
        self.longitude = longitude   # 经度
        self.latitude = latitude     # 纬度
        self.index = index           # 可选：该点在整条路线中的序号

    def __repr__(self):
        return "Point(lng={}, lat={})".format(self.longitude, self.latitude)


class Step:
    """骑行导航的一个步骤（路段）"""
    def __init__(self, instruction, action, distance, duration, road, points):
        self.instruction = instruction   # 文字指示
        self.action = action             # 动作类型
        self.distance = distance         # 该步骤距离（米）
        self.duration = duration         # 该步骤耗时（秒）
        self.road = road                 # 道路名称
        self.points = points             # 该步骤包含的路径点列表（Point 对象列表）

    def __repr__(self):
        instr_short = self.instruction[:20] if self.instruction else ''
        return "Step(instruction={}..., points_count={})".format(instr_short, len(self.points))


class Route:
    """完整的骑行路线"""
    def __init__(self, origin, destination, total_distance_m, total_duration_s, steps):
        self.origin = origin                 # 起点坐标字符串
        self.destination = destination       # 终点坐标字符串
        self.total_distance_m = total_distance_m   # 总距离（米）
        self.total_duration_s = total_duration_s   # 总耗时（秒）
        self.steps = steps                   # Step 对象列表

    def __repr__(self):
        return "Route(total_distance={}m, steps={})".format(self.total_distance_m, len(self.steps))


class AmapAPI:
    def __init__(self, weather_key, direction_key, coding_key):
        self.weather_key = weather_key
        self.direction_key = direction_key
        self.coding_key = coding_key
        self.weather_url = 'https://restapi.amap.com/v3/weather/weatherInfo'
        self.direction_url = 'https://restapi.amap.com/v4/direction/bicycling'
        self.codeing_url = 'https://restapi.amap.com/v3/geocode/geo'

    def get_weather(self, city_code):
        url = '{}?key={}&city={}'.format(self.weather_url, self.weather_key, city_code)
        try:
            response = request.get(url)
            data = response.json()
            if data.get('lives') and len(data['lives']) > 0:
                live_info = data['lives'][0]
                city = live_info['city']
                weather = live_info['weather']
                temperature = live_info['temperature']
                humidity = live_info['humidity']
                print("城市：{}，天气：{}，温度：{}，湿度：{}".format(city, weather, temperature, humidity))
                return live_info
            else:
                print("获取天气失败：", data)
                return None
        except Exception as e:
            print("请求天气接口异常：", e)
            return None

    def get_bicycle_route(self, origin, destination):
        """获取骑行路径数据"""
        url = '{}?origin={}&destination={}&key={}'.format(self.direction_url, origin, destination, self.direction_key)
        try:
            response = request.get(url)
            data = response.json()
            return data
        except Exception as e:
            print("请求骑行路径接口异常：", e)
            return {"errcode": -1, "errmsg": str(e)}

    def get_addr_coding(self, addr):
        """地址转经纬度"""
        url = '{}?key={}&address={}'.format(self.codeing_url, self.coding_key, addr)
        try:
            response = request.get(url)
            data = response.json()
            if data.get('status') != '1':
                return {'error': '高德API返回状态错误: {}'.format(data.get('info', ''))}
            if int(data.get('count', 0)) == 0:
                return {'error': '未找到该地址'}
            geocode = data['geocodes'][0]
            location = geocode.get('location', '')
            if not location:
                return {'error': '未获取到经纬度'}
            longitude, latitude = location.split(',')
            return {
                'longitude': float(longitude),
                'latitude': float(latitude),
                'address': geocode.get('formatted_address', ''),
                'province': geocode.get('province', ''),
                'city': geocode.get('city', ''),
                'district': geocode.get('district', ''),
                'adcode': geocode.get('adcode', ''),
                'level': geocode.get('level', '')
            }
        except Exception as e:
            return {'error': '请求地理编码接口异常：{}'.format(e)}

    @staticmethod
    def parse_bicycle_route(response_data):
        """
        解析高德骑行路径规划返回的JSON数据，封装成 Route 对象。
        其中每一个路径点（polyline上的每个点）都保存为 Point 类实例，包含经纬度信息。
        """
        if not response_data or response_data.get('errcode') != 0:
            return None

        route_data = response_data.get('data', {})
        if not route_data or 'paths' not in route_data or not route_data['paths']:
            return None

        path = route_data['paths'][0]
        total_distance = path.get('distance', 0)
        total_duration = path.get('duration', 0)
        steps_data = path.get('steps', [])

        origin = route_data.get('origin', '未知')
        destination = route_data.get('destination', '未知')

        steps = []
        for step_data in steps_data:
            instruction = step_data.get('instruction', '')
            action = step_data.get('action', '')
            distance = step_data.get('distance', 0)
            duration = step_data.get('duration', 0)
            road = step_data.get('road', '')
            polyline_str = step_data.get('polyline', '')

            points = []
            if polyline_str:
                point_strs = polyline_str.split(';')
                for idx, pt_str in enumerate(point_strs):
                    if ',' in pt_str:
                        lng_str, lat_str = pt_str.split(',')
                        try:
                            lng = float(lng_str)
                            lat = float(lat_str)
                            points.append(Point(lng, lat, index=idx))
                        except ValueError:
                            continue

            step = Step(instruction, action, distance, duration, road, points)
            steps.append(step)

        route = Route(origin, destination, total_distance, total_duration, steps)
        return route


