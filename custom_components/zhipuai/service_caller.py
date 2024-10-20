# 依旧优化中，精简大量错误

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
            await self.hass.services.async_call(domain, service, data, blocking=True)
            LOGGER.info(f"成功调用服务 {domain}.{service}")
            return {"success": True, "message": f"成功调用服务 {domain}.{service}", "data": data}
        except Exception as e:
            LOGGER.error(f"调用服务 {domain}.{service} 时出错：{str(e)}")
            return {"success": False, "message": str(e), "data": data}

    async def handle_service_call(self, service_info: Dict[str, Any]) -> Dict[str, Any]:
        domain = service_info.get('domain')
        action = service_info.get('action')
        name = service_info.get('name')
        area = service_info.get('area')
        data = service_info.get('data', {})

        LOGGER.debug(f"处理服务调用: domain={domain}, action={action}, name={name}, area={area}, data={data}")

        handlers = {
            "light": self.handle_light_intent,
            "water_heater": self.handle_water_heater_intent,
            "fan": self.handle_fan_intent,
            "cover": self.handle_cover_intent,
            "lock": self.handle_lock_intent,
            "climate": self.handle_climate_intent,
            "media_player": self.handle_media_player_intent,
            "switch": self.handle_switch_intent,
            "input_select": self.handle_input_select_intent,
            "scene": self.handle_scene_intent,
            "script": self.handle_script_intent,
            "camera": self.handle_camera_intent,
            "notify": self.handle_notify_intent,
            "automation": self.handle_automation_intent
        }

        handler = handlers.get(domain, self.handle_generic_intent)
        return await handler(action, name, area, data)

    async def handle_fan_intent(self, action: str, name: str, area: str, data: Dict[str, Any]) -> Dict[str, Any]:
        fan_entities = await self._get_entities("fan", name, area)
        if not fan_entities:
            return {"success": False, "message": f"未找到匹配的风扇"}

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
            return {"success": False, "message": f"没有成功执行的风扇操作"}
        return {"success": True, "message": f"执行了 {len(results)} 个风扇操作", "details": results}

    async def handle_light_intent(self, action: str, name: str, area: str, data: Dict[str, Any]) -> Dict[str, Any]:
        light_entities = await self._get_entities("light", name, area)
        if not light_entities:
            return {"success": False, "message": f"未找到匹配的灯光"}

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
            return {"success": False, "message": f"没有成功执行的灯光操作"}
        return {"success": True, "message": f"执行了 {len(results)} 个灯光操作", "details": results}

    async def handle_water_heater_intent(self, action: str, name: str, area: str, data: Dict[str, Any]) -> Dict[str, Any]:
        LOGGER.debug(f"Handling water heater intent: action={action}, name={name}, area={area}, data={data}")
        
        water_heater_entity = "number.temperature_setting"
        
        if not self.hass.states.get(water_heater_entity):
            LOGGER.error(f"未找到热水器温度设置实体: {water_heater_entity}")
            return {"success": False, "message": f"未找到热水器温度设置实体: {water_heater_entity}"}

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
                    return {"success": False, "message": "设置温度时需要提供温度值"}
            
            LOGGER.info(f"正在设置热水器温度为 {service_data['value']}°C")
            result = await self.call_service("number", service, service_data)
            
            if result["success"]:
                return {"success": True, "message": f"成功将热水器温度设置为 {service_data['value']}°C", "details": result}
            else:
                return {"success": False, "message": f"设置热水器温度失败: {result['message']}", "details": result}
        else:
            LOGGER.warning(f"不支持的热水器操作: {action}")
            return {"success": False, "message": f"不支持的热水器操作: {action}"}

    async def handle_cover_intent(self, action: str, name: str, area: str, data: Dict[str, Any]) -> Dict[str, Any]:
        VALID_DEVICE_CLASSES = {
            "awning", "blind", "curtain", "damper", "door", "garage", "gate", 
            "shade", "shutter", "window"
        }
        
        cover_entities = await self._get_entities("cover", name, area)
        if not cover_entities:
            return {"success": False, "message": f"未找到匹配的窗帘或门"}

        results = []
        for entity_id in cover_entities:
            service_data = {"entity_id": entity_id}
            
            state = self.hass.states.get(entity_id)
            device_class = state.attributes.get("device_class") if state else None

            if action in ["open", "close", "stop"]:
                service = action
            elif action == "set_position":
                service = "set_cover_position"
                if "position" in data:
                    service_data["position"] = data["position"]
                else:
                    LOGGER.warning(f"设置位置时需要提供 'position' 参数")
                    continue
            else:
                LOGGER.warning(f"不支持的操作: {action}")
                continue
            
            if "device_class" in data:
                if data["device_class"] in VALID_DEVICE_CLASSES:
                    service_data["device_class"] = data["device_class"]
                else:
                    LOGGER.warning(f"无效的 device_class: {data['device_class']}. 使用默认值。")

            elif device_class:
                service_data["device_class"] = device_class
            
            result = await self.call_service("cover", service, service_data)
            results.append(result)

        if not results:
            return {"success": False, "message": f"没有成功执行的操作"}
        return {"success": True, "message": f"执行了 {len(results)} 个操作", "details": results}

    async def handle_lock_intent(self, action: str, name: str, area: str, data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            if name is not None and not isinstance(name, str):
                name = str(name)

            lock_entities = await self._get_entities("lock", name, area)
            if not lock_entities:
                return {"success": False, "message": f"未找到匹配的门锁"}

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
                return {"success": False, "message": f"没有成功执行的门锁操作"}
            return {"success": True, "message": f"执行了 {len(results)} 个门锁操作", "details": results}

        except Exception as e:
            LOGGER.error(f"处理锁设备时发生错误: {str(e)}")
            return {"success": False, "message": f"处理锁设备时发生错误: {str(e)}"}
        return {"success": True, "message": f"执行了 {len(results)} 个门锁操作", "details": results}

    async def handle_climate_intent(self, action: str, name: str, area: str, data: Dict[str, Any]) -> Dict[str, Any]:
        climate_entities = await self._get_entities("climate", name, area)
        if not climate_entities:
            return {"success": False, "message": f"未找到匹配的空调或温控设备"}

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
            return {"success": False, "message": f"没有成功执行的空调操作"}
        return {"success": True, "message": f"执行了 {len(results)} 个空调操作", "details": results}

    async def handle_media_player_intent(self, action: str, name: str, area: str, data: Dict[str, Any]) -> Dict[str, Any]:
        media_player_entities = await self._get_entities("media_player", name, area)
        if not media_player_entities:
            return {"success": False, "message": f"未找到匹配的媒体播放器"}

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
            return {"success": False, "message": f"没有成功执行的媒体播放器操作"}
        return {"success": True, "message": f"执行了 {len(results)} 个媒体播放器操作", "details": results}

    async def restart_hass(self, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            await self.hass.services.async_call("homeassistant", "restart", data or {})
            return {"success": True, "message": "Home Assistant 正在重启"}
        except Exception as e:
            LOGGER.error(f"重启 Home Assistant 时出错：{str(e)}")
            return {"success": False, "message": f"重启 Home Assistant 失败：{str(e)}"}

    async def handle_generic_intent(self, domain: str, action: str, name: str, area: str, data: Dict[str, Any]) -> Dict[str, Any]:
        entities = await self._get_entities(domain, name, area)
        if not entities:
            return {"success": False, "message": f"未找到匹配的 {domain} 实体"}

        results = []
        for entity_id in entities:
            service_data = {**data, "entity_id": entity_id}
            result = await self.call_service(domain, action, service_data)
            results.append(result)

        if not results:
            return {"success": False, "message": f"没有成功执行的 {domain} 操作"}
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
                entity_area = self._get_entity_area(entity_id)
                if not entity_area or area.lower() not in entity_area.lower():
                    continue

            matched_entities.append(entity_id)

        LOGGER.debug(f"Found entities for domain {domain}: {matched_entities}")
        return matched_entities

    def _get_entity_area(self, entity_id: str) -> Optional[str]:
        entity_reg = self.entity_reg.async_get(entity_id)
        if entity_reg and entity_reg.area_id:
            area = self.area_reg.async_get_area(entity_reg.area_id)
            return area.name if area else None
        return None


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

    async def handle_switch_intent(self, action: str, name: str, area: str, data: Dict[str, Any]) -> Dict[str, Any]:
        switch_entities = await self._get_entities("switch", name, area)
        if not switch_entities:
            return {"success": False, "message": f"未找到匹配的开关"}

        results = []
        for entity_id in switch_entities:
            if action in ["turn_on", "turn_off"]:
                service_data = {"entity_id": entity_id}
                result = await self.call_service("switch", action, service_data)
                results.append(result)
            else:
                LOGGER.warning(f"不支持的开关操作: {action}")

        if not results:
            return {"success": False, "message": f"没有成功执行的开关操作"}
        return {"success": True, "message": f"执行了 {len(results)} 个开关操作", "details": results}

    async def handle_input_select_intent(self, action: str, name: str, area: str, data: Dict[str, Any]) -> Dict[str, Any]:
        input_select_entities = await self._get_entities("input_select", name, area)
        if not input_select_entities:
            return {"success": False, "message": f"未找到匹配的输入选择器"}

        results = []
        for entity_id in input_select_entities:
            if action == "select_option":
                service_data = {"entity_id": entity_id, "option": data.get("option")}
                result = await self.call_service("input_select", "select_option", service_data)
                results.append(result)
            else:
                LOGGER.warning(f"不支持的输入选择器操作: {action}")

        if not results:
            return {"success": False, "message": f"没有成功执行的输入选择器操作"}
        return {"success": True, "message": f"执行了 {len(results)} 个输入选择器操作", "details": results}

    async def handle_scene_intent(self, action: str, name: str, area: str, data: Dict[str, Any]) -> Dict[str, Any]:
        scene_entities = await self._get_entities("scene", name, area)
        if not scene_entities:
            return {"success": False, "message": f"未找到匹配的场景"}

        results = []
        for entity_id in scene_entities:
            if action == "activate":
                service_data = {"entity_id": entity_id}
                result = await self.call_service("scene", "turn_on", service_data)
                results.append(result)
            else:
                LOGGER.warning(f"不支持的场景操作: {action}")

        if not results:
            return {"success": False, "message": f"没有成功执行的场景操作"}
        return {"success": True, "message": f"执行了 {len(results)} 个场景操作", "details": results}

    async def handle_script_intent(self, action: str, name: str, area: str, data: Dict[str, Any]) -> Dict[str, Any]:
        script_entities = await self._get_entities("script", name, area)
        if not script_entities:
            return {"success": False, "message": f"未找到匹配的脚本"}

        results = []
        for entity_id in script_entities:
            if action == "run":
                service_data = {"entity_id": entity_id}
                result = await self.call_service("script", "turn_on", service_data)
                results.append(result)
            else:
                LOGGER.warning(f"不支持的脚本操作: {action}")

        if not results:
            return {"success": False, "message": f"没有成功执行的脚本操作"}
        return {"success": True, "message": f"执行了 {len(results)} 个脚本操作", "details": results}

    async def handle_camera_intent(self, action: str, name: str, area: str, data: Dict[str, Any]) -> Dict[str, Any]:
        camera_entities = await self._get_entities("camera", name, area)
        if not camera_entities:
            return {"success": False, "message": f"未找到匹配的相机"}

        results = []
        for entity_id in camera_entities:
            if action == "snapshot":
                filename = data.get('filename', f"snapshot_{int(time.time())}.jpg")
                service_data = {"entity_id": entity_id, "filename": filename}
                result = await self.call_service("camera", "snapshot", service_data)
                results.append(result)
            else:
                LOGGER.warning(f"不支持的相机操作: {action}")

        if not results:
            return {"success": False, "message": f"没有成功执行的相机操作"}
        return {"success": True, "message": f"执行了 {len(results)} 个相机操作", "details": results}

    async def handle_notify_intent(self, action: str, name: str, area: str, data: Dict[str, Any]) -> Dict[str, Any]:
        message = data.get('message', '')
        title = data.get('title', 'Home Assistant 通知')
        if not message:
            return {"success": False, "message": "未提供通知消息"}

        try:
            await self.call_service("notify", "notify", {"message": message, "title": title})
            return {"success": True, "message": f"成功发送通知: {title} - {message}"}
        except Exception as e:
            LOGGER.error(f"发送通知时出错: {str(e)}")
            return {"success": False, "message": str(e)}

    async def handle_automation_intent(self, action: str, name: str, area: str, data: Dict[str, Any]) -> Dict[str, Any]:
        automation_entities = await self._get_entities("automation", name, area)
        if not automation_entities:
            return {"success": False, "message": f"未找到匹配的自动化"}

        results = []
        for entity_id in automation_entities:
            if action in ["turn_on", "turn_off", "trigger"]:
                service_data = {"entity_id": entity_id}
                result = await self.call_service("automation", action, service_data)
                results.append(result)
            else:
                LOGGER.warning(f"不支持的自动化操作: {action}")

        if not results:
            return {"success": False, "message": f"没有成功执行的自动化操作"}
        return {"success": True, "message": f"执行了 {len(results)} 个自动化操作", "details": results}

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
