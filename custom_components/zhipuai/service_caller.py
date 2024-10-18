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


    async def call_service(self, domain: str, service: str, data: dict):
        try:
            await self.hass.services.async_call(domain, service, data)
            return {"success": True, "message": f"成功调用服务 {domain}.{service}", "data": data}
        except Exception as e:
            LOGGER.error(f"调用服务 {domain}.{service} 时出错：{str(e)}")
            return {"success": False, "error": str(e), "data": data}


    async def handle_service_call(self, tool_input):
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

        if domain == "light":
            return await self.handle_light_intent(action, name, area, data)
        if domain == "fan":
            return await self.handle_fan_intent(action, name, area, data)
        if domain == "homeassistant" and action == "restart":
            return await self.restart_hass()
        elif domain == "light":
            return await self.handle_light_intent(action, name, area, data)
        elif domain == "cover":
            return await self.handle_cover_intent(action, name, area, data)
        elif domain == "lock":
            return await self.handle_lock_intent(action, name, area, data)
        else:
            return await self.handle_generic_intent(domain, action, name, area, data)


    async def handle_fan_intent(self, action: str, name: str, area: str, data: dict):
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
                return {"success": False, "error": f"不支持的风扇操作: {action}"}
            
            service_data.update(data)
            result = await self.call_service("fan", service, service_data)
            results.append(result)

        return {"success": True, "message": f"执行了 {len(results)} 个风扇操作", "details": results}


    def _process_light_attributes(self, data: dict):
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

    def _convert_color_to_rgb(self, color):
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


    def _convert_color_temp(self, color_temp):
        try:
            return str(int(color_temp))
        except ValueError:
            LOGGER.error(f"无效的色温值: {color_temp}")
            return None

    async def handle_light_intent(self, action: str, name: str, area: str, data: dict):
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
                return {"success": False, "error": f"不支持的灯光操作: {action}"}
            
            result = await self.call_service("light", service, service_data)
            results.append(result)

        return {"success": True, "message": f"执行了 {len(results)} 个灯光操作", "details": results}

    async def restart_hass(self, data: dict = None):
        try:
            await self.hass.services.async_call("homeassistant", "restart", data or {})
            return {"success": True, "message": "Home Assistant 正在重启"}
        except Exception as e:
            LOGGER.error(f"重启 Home Assistant 时出错：{str(e)}")
            return {"success": False, "error": f"重启 Home Assistant 失败：{str(e)}"}


    async def handle_cover_intent(self, action: str, name: str, area: str, data: dict):
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
                return {"success": False, "error": f"不支持的窗帘操作: {action}"}
            
            service_data.update(data)
            result = await self.call_service("cover", service, service_data)
            results.append(result)

        return {"success": True, "message": f"执行了 {len(results)} 个窗帘操作", "details": results}


    async def handle_lock_intent(self, action: str, name: str, area: str, data: dict):
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
                return {"success": False, "error": f"不支持的门锁操作: {action}"}

        return {"success": True, "message": f"执行了 {len(results)} 个门锁操作", "details": results}


    async def handle_generic_intent(self, domain: str, service: str, name: str, area: str, data: dict):
        entities = await self._get_entities(domain, name, area)
        if not entities:
            return {"success": False, "error": f"未找到匹配的 {domain} 实体"}

        results = []
        for entity_id in entities:
            service_data = {**data, "entity_id": entity_id}
            result = await self.call_service(domain, service, service_data)
            results.append(result)

        return {"success": True, "message": f"执行了 {len(results)} 个 {domain} 操作", "details": results}


    async def _get_entities(self, domain: str, name: str = None, area: str = None, device_classes: set = None):
        entities = self.hass.states.async_entity_ids(domain)
        matched_entities = []

        for entity_id in entities:
            entity = self.hass.states.get(entity_id)
            if entity is None:
                continue

            # 检查设备类型
            if device_classes:
                entity_device_class = entity.attributes.get(ATTR_DEVICE_CLASS)
                if entity_device_class not in device_classes:
                    continue

            # 检查名称
            if name and name.lower() not in entity.name.lower():
                continue

            # 检查区域
            if area:
                entity_entry = self.entity_reg.async_get(entity_id)
                if entity_entry and entity_entry.area_id:
                    area_entry = self.area_reg.async_get_area(entity_entry.area_id)
                    if area_entry and area.lower() not in area_entry.name.lower():
                        continue
                else:
                    continue

            matched_entities.append(entity_id)

        return matched_entities


    def _process_light_attributes(self, data: dict):
        processed_data = {}
        if "color" in data:
            rgb_color = self._convert_color_to_rgb(data["color"])
            if rgb_color:
                processed_data["rgb_color"] = rgb_color
        if "brightness" in data:
            processed_data["brightness"] = int(data["brightness"])
        if "color_temp" in data:
            processed_data["color_temp"] = int(data["color_temp"])
        return processed_data


    def _convert_color_to_rgb(self, color):
        if isinstance(color, (list, tuple)) and len(color) == 3:
            return color
        elif isinstance(color, str):
            return color_util.color_name_to_rgb(color.lower().replace(" ", ""))
        return None



    async def get_available_services(self):
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


def get_service_caller(hass: HomeAssistant):
    return ServiceCaller(hass)
