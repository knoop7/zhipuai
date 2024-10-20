##### 当前可能不可用状态居多，还在优化中


from typing import Dict, List, Union, Set, Any, Optional
from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent, area_registry, device_registry, entity_registry
from homeassistant.util import color as color_util
from homeassistant.const import ATTR_DEVICE_CLASS
from .const import LOGGER

class ServiceCaller:
    def __init__(self, hass: HomeAssistant):
        self.hass = hass
        self.area_reg = area_registry.async_get(hass)
        self.device_reg = device_registry.async_get(hass)
        self.entity_reg = entity_registry.async_get(hass)

    async def call_service(self, domain: str, service: str, data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            await self.hass.services.async_call(domain, service, data)
            LOGGER.info(f"成功调用服务 {domain}.{service}")
            return {"success": True, "message": f"成功调用服务 {domain}.{service}", "data": data}
        except Exception as e:
            LOGGER.error(f"调用服务 {domain}.{service} 时出错：{str(e)}")
            return {"success": False, "error": str(e), "data": data}

    async def handle_service_call(self, tool_input: Union[intent.IntentResponse, Any]) -> Dict[str, Any]:
        if isinstance(tool_input, intent.IntentResponse):
            domain = tool_input.intent.intent_type.split('.')[0]
            action = tool_input.intent.intent_type.split('.')[-1]
            name = tool_input.slots.get('name', {}).get('value')
            area = tool_input.slots.get('area', {}).get('value')
            data = {k: v['value'] for k, v in tool_input.slots.items() if k not in ['name', 'area']}
        else:  
            domain = tool_input.tool_args.get('domain', 'light')
            action = tool_input.tool_args.get('action', 'turn_on')
            name = tool_input.tool_args.get('name')
            area = tool_input.tool_args.get('area')
            data = {k: v for k, v in tool_input.tool_args.items() if k not in ['domain', 'action', 'name', 'area']}

        LOGGER.debug(f"Handling service call: domain={domain}, action={action}, name={name}, area={area}, data={data}")

        handlers = {
            "light": (self.handle_light_intent, ["灯", "照明", "光"]),
            "water_heater": (self.handle_water_heater_intent, ["热水器", "水温", "温度"]),
            "fan": (self.handle_fan_intent, ["风扇", "电扇", "空气循环"]),
            "cover": (self.handle_cover_intent, ["窗帘", "百叶窗", "卷帘"]),
            "lock": (self.handle_lock_intent, ["锁", "门锁", "智能锁"]),
            "climate": (self.handle_climate_intent, ["空调", "暖气", "温控"]),
            "media_player": (self.handle_media_player_intent, ["音响", "电视", "播放器"])
        }

        for handler_domain, (handler, keywords) in handlers.items():
            if domain == handler_domain or (name and any(keyword in name for keyword in keywords)):
                return await handler(action, name, area, data)

        if domain == "homeassistant" and action == "restart":
            return await self.restart_hass(data)

        return await self.handle_generic_intent(domain, action, name, area, data)

    async def handle_fan_intent(self, action: str, name: str, area: str, data: Dict[str, Any]) -> Dict[str, Any]:
        fan_entities = await self._get_entities("fan", name, area)
        if not fan_entities:
            return {"success": False, "error": f"未找到匹配的风扇"}

        results = []
        for entity_id in fan_entities:
            service_data = {"entity_id": entity_id}
            if action in ["turn_on", "turn_off"]:
                service = action
            elif action == "set_speed":
                service = "set_percentage"
                service_data["percentage"] = data.get("speed")
            else:
                LOGGER.warning(f"不支持的风扇操作: {action}")
                continue
            
            service_data.update(data)
            result = await self.call_service("fan", service, service_data)
            results.append(result)

        if not results:
            return {"success": False, "error": f"没有成功执行的风扇操作"}
        return {"success": True, "message": f"执行了 {len(results)} 个风扇操作", "details": results}

    async def handle_light_intent(self, action: str, name: str, area: str, data: Dict[str, Any]) -> Dict[str, Any]:
        light_entities = await self._get_entities("light", name, area)
        if not light_entities:
            return {"success": False, "error": f"未找到匹配的灯光"}

        results = []
        for entity_id in light_entities:
            service_data = {"entity_id": entity_id}
            if action in ["turn_on", "turn_off"]:
                service = action
                if action == "turn_on":
                    service_data.update(self._process_light_attributes(data))
            else:
                LOGGER.warning(f"不支持的灯光操作: {action}")
                continue
            
            result = await self.call_service("light", service, service_data)
            results.append(result)

        if not results:
            return {"success": False, "error": f"没有成功执行的灯光操作"}
        return {"success": True, "message": f"执行了 {len(results)} 个灯光操作", "details": results}

    async def handle_water_heater_intent(self, action: str, name: str, area: str, data: Dict[str, Any]) -> Dict[str, Any]:
        LOGGER.debug(f"Handling water heater intent: action={action}, name={name}, area={area}, data={data}")
        
        water_heater_entity = "number.temperature_setting"
        
        if not self.hass.states.get(water_heater_entity):
            LOGGER.error(f"未找到热水器温度设置实体: {water_heater_entity}")
            return {"success": False, "error": f"未找到热水器温度设置实体: {water_heater_entity}"}

        if action in ["set_temperature", "设置温度"]:
            service = "set_value"
            service_data = {"entity_id": water_heater_entity}
            
            if "temperature" in data:
                service_data["value"] = float(data["temperature"])
            else:
                try:
                    temperature = float(''.join(filter(str.isdigit, action)))
                    service_data["value"] = temperature
                except ValueError:
                    LOGGER.error("无法从动作中提取温度值")
                    return {"success": False, "error": "设置温度时需要提供温度值"}
            
            LOGGER.info(f"正在设置热水器温度为 {service_data['value']}°C")
            result = await self.call_service("number", service, service_data)
            
            if result["success"]:
                return {"success": True, "message": f"成功将热水器温度设置为 {service_data['value']}°C", "details": result}
            else:
                return {"success": False, "error": f"设置热水器温度失败: {result['error']}", "details": result}
        else:
            LOGGER.warning(f"不支持的热水器操作: {action}")
            return {"success": False, "error": f"不支持的热水器操作: {action}"}

    async def handle_cover_intent(self, action: str, name: str, area: str, data: Dict[str, Any]) -> Dict[str, Any]:
        cover_entities = await self._get_entities("cover", name, area, 
        device_classes={"shutter", "blind", "curtain", "awning", "window", "shade"})
        if not cover_entities:
            return {"success": False, "error": f"未找到匹配的窗帘"}

        results = []
        for entity_id in cover_entities:
            service_data = {"entity_id": entity_id}
            if action in ["open", "close", "stop"]:
                service = f"{action}_cover"
            elif action == "set_position":
                service = "set_cover_position"
                service_data["position"] = data.get("position")
            else:
                LOGGER.warning(f"不支持的窗帘操作: {action}")
                continue
            
            service_data.update(data)
            result = await self.call_service("cover", service, service_data)
            results.append(result)

        if not results:
            return {"success": False, "error": f"没有成功执行的窗帘操作"}
        return {"success": True, "message": f"执行了 {len(results)} 个窗帘操作", "details": results}

    async def handle_lock_intent(self, action: str, name: str, area: str, data: Dict[str, Any]) -> Dict[str, Any]:
        lock_entities = await self._get_entities("lock", name, area)
        if not lock_entities:
            return {"success": False, "error": f"未找到匹配的门锁"}

        results = []
        for entity_id in lock_entities:
            if action in ["lock", "unlock"]:
                service_data = {"entity_id": entity_id}
                service_data.update(data)
                result = await self.call_service("lock", action, service_data)
                results.append(result)
            else:
                LOGGER.warning(f"不支持的门锁操作: {action}")

        if not results:
            return {"success": False, "error": f"没有成功执行的门锁操作"}
        return {"success": True, "message": f"执行了 {len(results)} 个门锁操作", "details": results}

    async def handle_climate_intent(self, action: str, name: str, area: str, data: Dict[str, Any]) -> Dict[str, Any]:
        climate_entities = await self._get_entities("climate", name, area)
        if not climate_entities:
            return {"success": False, "error": f"未找到匹配的空调或温控设备"}

        results = []
        for entity_id in climate_entities:
            service_data = {"entity_id": entity_id}
            if action in ["turn_on", "turn_off"]:
                service = action
            elif action == "set_temperature":
                service = "set_temperature"
                if "temperature" in data:
                    service_data["temperature"] = float(data["temperature"])
                else:
                    LOGGER.warning("设置温度时需要提供 'temperature' 参数")
                    continue
            elif action == "set_hvac_mode":
                service = "set_hvac_mode"
                if "hvac_mode" in data:
                    service_data["hvac_mode"] = data["hvac_mode"]
                else:
                    LOGGER.warning("设置模式时需要提供 'hvac_mode' 参数")
                    continue
            else:
                LOGGER.warning(f"不支持的空调操作: {action}")
                continue
            
            service_data.update(data)
            result = await self.call_service("climate", service, service_data)
            results.append(result)

        if not results:
            return {"success": False, "error": f"没有成功执行的空调操作"}
        return {"success": True, "message": f"执行了 {len(results)} 个空调操作", "details": results}

    async def handle_media_player_intent(self, action: str, name: str, area: str, data: Dict[str, Any]) -> Dict[str, Any]:
        media_player_entities = await self._get_entities("media_player", name, area)
        if not media_player_entities:
            return {"success": False, "error": f"未找到匹配的媒体播放器"}

        results = []
        for entity_id in media_player_entities:
            service_data = {"entity_id": entity_id}
            if action in ["turn_on", "turn_off", "play", "pause", "stop", "volume_up", "volume_down", "volume_mute"]:
                service = action
            elif action == "set_volume_level":
                service = "volume_set"
                if "volume_level" in data:
                    service_data["volume_level"] = float(data["volume_level"])
                else:
                    LOGGER.warning("设置音量时需要提供 'volume_level' 参数")
                    continue
            else:
                LOGGER.warning(f"不支持的媒体播放器操作: {action}")
                continue
            
            service_data.update(data)
            result = await self.call_service("media_player", service, service_data)
            results.append(result)

        if not results:
            return {"success": False, "error": f"没有成功执行的媒体播放器操作"}
        return {"success": True, "message": f"执行了 {len(results)} 个媒体播放器操作", "details": results}

    async def restart_hass(self, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            await self.hass.services.async_call("homeassistant", "restart", data or {})
            return {"success": True, "message": "Home Assistant 正在重启"}
        except Exception as e:
            LOGGER.error(f"重启 Home Assistant 时出错：{str(e)}")
            return {"success": False, "error": f"重启 Home Assistant 失败：{str(e)}"}

    async def handle_generic_intent(self, domain: str, action: str, name: str, area: str, data: Dict[str, Any]) -> Dict[str, Any]:
        entities = await self._get_entities(domain, name, area)
        if not entities:
            return {"success": False, "error": f"未找到匹配的 {domain} 实体"}

        results = []
        for entity_id in entities:
            service_data = {**data, "entity_id": entity_id}
            result = await self.call_service(domain, action, service_data)
            results.append(result)

        if not results:
            return {"success": False, "error": f"没有成功执行的 {domain} 操作"}
        return {"success": True, "message": f"执行了 {len(results)} 个 {domain} 操作", "details": results}

    async def _get_entities(self, domain: str, name: Optional[str] = None, area: Optional[str] = None, device_classes: Optional[Set[str]] = None) -> List[str]:
        entities = self.hass.states.async_entity_ids(domain)
        matched_entities = []

        for entity_id in entities:
            entity = self.hass.states.get(entity_id)
            if entity is None:
                continue

            if device_classes:
                entity_device_class = entity.attributes.get(ATTR_DEVICE_CLASS)
                if entity_device_class not in device_classes:
                    continue

            if name and name.lower() not in entity.name.lower():
                continue

            if area:
                entity_entry = self.entity_reg.async_get(entity_id)
                if entity_entry and entity_entry.area_id:
                    area_entry = self.area_reg.async_get_area(entity_entry.area_id)
                    if area_entry and area.lower() not in area_entry.name.lower():
                        continue
                else:
                    continue

            matched_entities.append(entity_id)

        LOGGER.debug(f"Found entities for domain {domain}: {matched_entities}")
        return matched_entities

    def _process_light_attributes(self, data: Dict[str, Any]) -> Dict[str, Any]:
        processed_data = {}
        if "color" in data:
            rgb_color = self._convert_color_to_rgb(data["color"])
            if rgb_color:
                processed_data["rgb_color"] = rgb_color
        if "brightness" in data:
            processed_data["brightness"] = int(data["brightness"])
        if "color_temp" in data:
            processed_data["color_temp"] = self._convert_color_temp(data["color_temp"])
        return processed_data

    def _convert_color_to_rgb(self, color: Union[str, List[int], color_util.RGBColor]) -> Optional[str]:
        if isinstance(color, color_util.RGBColor):
            return f"{color.red},{color.green},{color.blue}"
        elif isinstance(color, (list, tuple)) and len(color) == 3:
            return f"{color[0]},{color[1]},{color[2]}"
        elif isinstance(color, str):
            color = color.lower().replace(" ", "")
            try:
                rgb = color_util.color_name_to_rgb(color)
                return f"{rgb[0]},{rgb[1]},{rgb[2]}"
            except ValueError:
                LOGGER.error(f"无法将颜色 '{color}' 转换为 RGB")
                return None
        else:
            LOGGER.error(f"不支持的颜色格式: {color}")
            return None

    def _convert_color_temp(self, color_temp: Union[int, str]) -> Optional[str]:
        try:
            return str(int(color_temp))
        except ValueError:
            LOGGER.error(f"无效的色温值: {color_temp}")
            return None

    async def get_available_services(self) -> Dict[str, Dict[str, Dict[str, Any]]]:
        services = {}
        for domain in self.hass.services.async_services():
            domain_services = {}
            for service in self.hass.services.async_services()[domain]:
                service_data = self.hass.services.async_services()[domain][service]
                domain_services[service] = {
                    "description": service_data.get("description", ""),
                    "fields": service_data.get("fields", {})
                }
            services[domain] = domain_services
        return services

def get_service_caller(hass: HomeAssistant) -> ServiceCaller:
    return ServiceCaller(hass)
