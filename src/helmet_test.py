import math
import request
from machine import UART

class Point:
    def __init__(self, longitude, latitude, index=None):
        self.longitude = longitude
        self.latitude = latitude
        self.index = index

    def __repr__(self):
        return "Point(lng={}, lat={})".format(self.longitude, self.latitude)

class Step:
    def __init__(self, instruction, action, distance, duration, road, points):
        self.instruction = instruction
        self.action = action
        self.distance = distance
        self.duration = duration
        self.road = road
        self.points = points

    def __repr__(self):
        instr_short = self.instruction[:20] if self.instruction else ''
        return "Step(instruction={}..., points_count={})".format(instr_short, len(self.points))

class Route:
    def __init__(self, origin, destination, total_distance_m, total_duration_s, steps):
        self.origin = origin
        self.destination = destination
        self.total_distance_m = total_distance_m
        self.total_duration_s = total_duration_s
        self.steps = steps

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
                print("城市：{}，天气：{}，温度：{}，湿度：{}".format(
                    live_info['city'], live_info['weather'],
                    live_info['temperature'], live_info['humidity']))
                return live_info
            else:
                print("获取天气失败：", data)
                return None
        except Exception as e:
            print("请求天气接口异常：", e)
            return None

    def get_bicycle_route(self, origin, destination):
        url = '{}?origin={}&destination={}&key={}'.format(self.direction_url, origin, destination, self.direction_key)
        try:
            response = request.get(url)
            return response.json()
        except Exception as e:
            print("请求骑行路径接口异常：", e)
            return {"errcode": -1, "errmsg": str(e)}

    def get_addr_coding(self, addr):
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
    def haversine(lng1, lat1, lng2, lat2):
        # 球面距离公式
        R = 6371000
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lng2 - lng1)
        a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c

    @staticmethod
    def _ang_dist(la1, lo1, la2, lo2):
        """两点间角距离（弧度），输入已是弧度"""
        dlat = la2 - la1
        dlng = lo2 - lo1
        a = math.sin(dlat / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin(dlng / 2) ** 2
        return 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    @staticmethod
    def _bearing(la1, lo1, la2, lo2):
        """从点1到点2的初始方位角（弧度），输入已是弧度"""
        dlng = lo2 - lo1
        y = math.sin(dlng) * math.cos(la2)
        x = math.cos(la1) * math.sin(la2) - math.sin(la1) * math.cos(la2) * math.cos(dlng)
        return math.atan2(y, x)

    @staticmethod
    def point_to_segment_distance(p_lng, p_lat, a_lng, a_lat, b_lng, b_lat):
        """点到线段的最短球面距离（米）—— 纯球面几何，无平面近似"""
        if a_lng == b_lng and a_lat == b_lat:
            return AmapAPI.haversine(p_lng, p_lat, a_lng, a_lat)

        R = 6371000.0

        lat1, lng1 = math.radians(a_lat), math.radians(a_lng)
        lat2, lng2 = math.radians(b_lat), math.radians(b_lng)
        lat_p, lng_p = math.radians(p_lat), math.radians(p_lng)

        d_ap = AmapAPI._ang_dist(lat1, lng1, lat_p, lng_p)
        d_ab = AmapAPI._ang_dist(lat1, lng1, lat2, lng2)

        if d_ab < 1e-12:
            return d_ap * R

        brng_ab = AmapAPI._bearing(lat1, lng1, lat2, lng2)
        brng_ap = AmapAPI._bearing(lat1, lng1, lat_p, lng_p)

        d_xt = math.asin(math.sin(d_ap) * math.sin(brng_ap - brng_ab))

        cos_d_at = math.cos(d_ap) / max(math.cos(d_xt), 1e-12)
        cos_d_at = max(-1.0, min(1.0, cos_d_at))
        d_at = math.acos(cos_d_at)

        if d_at <= d_ab and math.cos(brng_ap - brng_ab) >= 0:
            return abs(d_xt) * R

        dist_to_a = d_ap * R
        dist_to_b = AmapAPI._ang_dist(lat_p, lng_p, lat2, lng2) * R
        return min(dist_to_a, dist_to_b)

    @staticmethod
    def polyline_distance(lng, lat, points):
        """点到折线的最短距离（米）"""
        if not points:
            return float('inf')
        if len(points) == 1:
            return AmapAPI.haversine(lng, lat, points[0].longitude, points[0].latitude)
        min_dist = float('inf')
        for i in range(len(points) - 1):
            p1 = points[i]
            p2 = points[i + 1]
            dist = AmapAPI.point_to_segment_distance(
                lng, lat,
                p1.longitude, p1.latitude,
                p2.longitude, p2.latitude
            )
            if dist < min_dist:
                min_dist = dist
        return min_dist

    def is_off_course(self, current_lng, current_lat, point_a, point_b, threshold_m=50):
        if not isinstance(point_a, Point) or not isinstance(point_b, Point):
            raise TypeError("point_a 和 point_b 必须是 Point 类的实例")
        distance = self.point_to_segment_distance(
            current_lng, current_lat,
            point_a.longitude, point_a.latitude,
            point_b.longitude, point_b.latitude
        )
        return distance > threshold_m

    def get_current_step(self, route, current_lng, current_lat, threshold_m=50):
        if not route or not route.steps:
            return None
        best_step = None
        best_distance = float('inf')
        for step in route.steps:
            if not step.points:
                continue
            dist = AmapAPI.polyline_distance(current_lng, current_lat, step.points)
            if dist <= threshold_m and dist < best_distance:
                best_distance = dist
                best_step = step
        return best_step

    @staticmethod
    def parse_bicycle_route(response_data):
        # 解析高德骑行路径规划返回的JSON
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
                for idx, pt_str in enumerate(polyline_str.split(';')):
                    if ',' in pt_str:
                        lng_str, lat_str = pt_str.split(',')
                        try:
                            points.append(Point(float(lng_str), float(lat_str), index=idx))
                        except ValueError:
                            continue
            steps.append(Step(instruction, action, distance, duration, road, points))

        return Route(origin, destination, total_distance, total_duration, steps)

class Navigator:
    def __init__(self, route, threshold_m=50, arrive_threshold_m=20,
                 current_lng=None, current_lat=None):
        self.route = route
        self.threshold = threshold_m
        self.arrive_threshold = arrive_threshold_m
        self.finished = False

        if current_lng is not None and current_lat is not None and route and route.steps:
            self.current_step_idx = self._find_nearest_step(current_lng, current_lat)
        else:
            self.current_step_idx = 0

    def _find_nearest_step(self, lng, lat):
        best_idx = 0
        best_dist = float('inf')
        for i, step in enumerate(self.route.steps):
            if not step.points:
                continue
            dist = AmapAPI.polyline_distance(lng, lat, step.points)
            if dist < best_dist:
                best_dist = dist
                best_idx = i
        return best_idx

    def update(self, current_lng, current_lat):
        if self.finished:
            return False, False, True

        if current_lng is None or current_lat is None:
            return False, False, False
        if abs(current_lat) > 90 or abs(current_lng) > 180:
            return False, False, False

        step = self.route.steps[self.current_step_idx]
        if not step.points or len(step.points) < 2:
            return False, False, False

        dist = AmapAPI.polyline_distance(current_lng, current_lat, step.points)

        end_point = step.points[-1]
        dist_to_end = AmapAPI.haversine(
            current_lng, current_lat,
            end_point.longitude, end_point.latitude
        )
        arrived = dist_to_end <= self.arrive_threshold

        step_changed = False
        if arrived:
            off_course = False
            if self.current_step_idx < len(self.route.steps) - 1:
                self.current_step_idx += 1
                step_changed = True
                next_inst = self.route.steps[self.current_step_idx].instruction
                print("进入下一个路段: {}...".format(next_inst[:50] if next_inst else ''))
            else:
                self.finished = True
                print("导航完成！")
        else:
            off_course = dist > self.threshold
            if off_course:
                new_idx = self._find_nearest_step(current_lng, current_lat)
                new_step = self.route.steps[new_idx]
                new_dist = (AmapAPI.polyline_distance(current_lng, current_lat, new_step.points)
                            if new_step.points else float('inf'))
                if new_dist <= self.threshold and new_idx != self.current_step_idx:
                    self.current_step_idx = new_idx
                    off_course = False
                    step_changed = True
                    new_inst = new_step.instruction
                    print("检测到跳转到路段 {}: {}...".format(
                        new_idx, new_inst[:50] if new_inst else ''))

        return off_course, step_changed, self.finished

    def get_current_step(self):
        if self.finished or self.current_step_idx >= len(self.route.steps):
            return None
        return self.route.steps[self.current_step_idx]

    def get_current_step_index(self):
        return self.current_step_idx if not self.finished else -1


class NavigationManager:
    def __init__(self, threshold_m=50, arrive_threshold_m=20):
        self.navigator = None
        self.route = None
        self.is_navigating = False
        self.last_lng = None
        self.last_lat = None

        self.on_step_changed = None
        self.on_off_course = None
        self.on_arrived = None

        self.threshold = threshold_m
        self.arrive_threshold = arrive_threshold_m
        self._off_course_notified = False

    def start(self, route, current_lng=None, current_lat=None):
        self.route = route
        self.navigator = Navigator(
            route,
            threshold_m=self.threshold,
            arrive_threshold_m=self.arrive_threshold,
            current_lng=current_lng,
            current_lat=current_lat
        )
        self.is_navigating = True
        self.last_lng = current_lng
        self.last_lat = current_lat
        self._off_course_notified = False

    def stop(self):
        self.is_navigating = False
        self.navigator = None
        self.route = None
        self.last_lng = None
        self.last_lat = None

    def update_position(self, lng, lat):
        if not self.is_navigating or not self.navigator:
            return False, False, False

        # 坐标校验在前，防止无效坐标污染 last_lng/last_lat
        if lng is None or lat is None or abs(lat) > 90 or abs(lng) > 180:
            return False, False, False

        self.last_lng = lng
        self.last_lat = lat

        off_course, step_changed, finished = self.navigator.update(lng, lat)

        if finished:
            self.is_navigating = False
            if self.on_arrived:
                self.on_arrived()
        elif step_changed and self.on_step_changed:
            step = self.navigator.get_current_step()
            if step and self.on_step_changed:
                idx = self.navigator.get_current_step_index()
                total = len(self.route.steps)
                self.on_step_changed(step, idx, total)
            self._off_course_notified = False   # 进入新路段，重置偏航通知
        elif off_course and self.on_off_course:
            if not self._off_course_notified:
                self.on_off_course()
                self._off_course_notified = True
        elif not off_course:
            self._off_course_notified = False   # 回到路线上，允许下次偏航通知

        return off_course, step_changed, finished

    def get_current_instruction(self):
        if not self.is_navigating or not self.navigator:
            return None
        step = self.navigator.get_current_step()
        return step.instruction if step else None

    def get_status(self):
        if not self.is_navigating or not self.navigator:
            return {"state": "idle"}

        step = self.navigator.get_current_step()
        idx = self.navigator.get_current_step_index()

        if step is None:
            return {"state": "finished"}

        remain_m = 0
        for i in range(idx, len(self.route.steps)):
            remain_m += self.route.steps[i].distance

        if step.points and len(step.points) > 0 and self.last_lng is not None:
            end_pt = step.points[-1]
            dist_to_end = AmapAPI.haversine(
                self.last_lng, self.last_lat,
                end_pt.longitude, end_pt.latitude
            )
        else:
            dist_to_end = 0

        return {
            "state": "navigating",
            "step_index": idx,
            "total_steps": len(self.route.steps),
            "instruction": step.instruction if step else "",
            "action": step.action if step else "",
            "road": step.road if step else "",
            "step_distance_m": step.distance if step else 0,
            "dist_to_step_end_m": int(dist_to_end),
            "total_remaining_m": int(remain_m),
            "total_remaining_min": int(self.route.total_duration_s / 60) if self.route else 0,
            "finished": self.navigator.finished
        }

