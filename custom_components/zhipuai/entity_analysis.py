
from __future__ import annotations

import json
import voluptuous as vol
from datetime import datetime, timedelta
from typing import List

from homeassistant.core import HomeAssistant, ServiceCall, State
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er, config_validation as cv
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.history import get_significant_states

from .const import DOMAIN, LOGGER

ENTITY_ANALYSIS_SCHEMA = vol.Schema({
    vol.Required("entity_id"): vol.Any(cv.entity_id, [cv.entity_id]),
    vol.Optional("days", default=3): vol.All(
        vol.Coerce(int), 
        vol.Range(min=1, max=15)
    )
})

async def async_setup_entity_analysis(hass: HomeAssistant) -> None:
    
    
    async def handle_entity_analysis(call: ServiceCall) -> dict:
        
        try:
            entity_ids = call.data["entity_id"]
            if isinstance(entity_ids, str):
                entity_ids = [entity_ids]
            
            days = call.data.get("days", 3)

            entity_registry = er.async_get(hass)
            valid_entity_ids = []
            current_states = {}

            for entity_id in entity_ids:
                state = hass.states.get(entity_id)
                if state is None:
                    LOGGER.warning("实体 %s 不存在", entity_id)
                    continue
                
                if not entity_registry.async_get(entity_id):
                    LOGGER.info("实体 %s 未注册但存在，将只获取当前状态", entity_id)
                    current_states[entity_id] = state
                else:
                    valid_entity_ids.append(entity_id)

            if not valid_entity_ids and not current_states:
                error_msg = "没有找到任何有效的实体"
                LOGGER.error(error_msg)
                return {"success": False, "message": error_msg}

            end_time = datetime.now()
            start_time = end_time - timedelta(days=days)
            history_text = []
            
            if valid_entity_ids:
                instance = get_instance(hass)
                history_data = await instance.async_add_executor_job(
                    get_significant_states,
                    hass,
                    start_time,
                    end_time,
                    valid_entity_ids,
                    None,
                    True,
                    True
                )

                if history_data:
                    for entity_id in valid_entity_ids:
                        if entity_id not in history_data:
                            continue
                        
                        for state in history_data[entity_id]:
                            if state is None:
                                continue
                            history_text.append(
                                f"{entity_id}, {state.state}, {state.last_updated.strftime('%Y-%m-%d %H:%M:%S')}"
                            )

            for entity_id, state in current_states.items():
                history_text.append(
                    f"{entity_id}, {state.state}, {state.last_updated.strftime('%Y-%m-%d %H:%M:%S')}"
                )

            message = (
                f"分析时间范围: {start_time.strftime('%Y-%m-%d %H:%M:%S')} 至 "
                f"{end_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"总计 {len(history_text)} 条记录\n\n"
                "实体ID, 状态值, 更新时间\n"
                f"{chr(10).join(history_text)}"
            )

            LOGGER.info("生成的历史记录文本:\n%s", message)
            
            return {
                "success": True,
                "message": message
            }

        except Exception as e:
            error_msg = f"获取历史记录失败: {str(e)}"
            LOGGER.error(error_msg)
            return {"success": False, "message": error_msg}

    hass.services.async_register(
        DOMAIN,
        "entity_analysis",
        handle_entity_analysis,
        schema=ENTITY_ANALYSIS_SCHEMA,
        supports_response=True
    )