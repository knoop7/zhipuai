from __future__ import annotations

import os
import aiohttp
import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError

from .const import (
    DOMAIN,
    LOGGER,
    ZHIPUAI_IMAGE_GEN_URL,
    IMAGE_SIZES,
    DEFAULT_IMAGE_SIZE,
)

IMAGE_GEN_SCHEMA = vol.Schema({
    vol.Required("prompt"): str,
    vol.Optional("model", default="cogview-3-flash"): vol.In(["cogview-3-plus", "cogview-3", "cogview-3-flash"]),
    vol.Optional("size", default=DEFAULT_IMAGE_SIZE): vol.In(IMAGE_SIZES),
})

async def async_setup_image_gen(hass: HomeAssistant) -> None:
    async def handle_image_gen(call: ServiceCall) -> None:
        try:
            config_entries = hass.config_entries.async_entries(DOMAIN)
            if not config_entries:
                raise ValueError("未找到 ZhipuAI 配置")
            api_key = config_entries[0].data.get("api_key")
            if not api_key:
                raise ValueError("在配置中找不到 API 密钥")

            prompt = call.data["prompt"]
            model = call.data.get("model", "cogview-3-flash")
            size = call.data.get("size", DEFAULT_IMAGE_SIZE)

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "model": model,
                "prompt": prompt,
                "size": size
            }

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        ZHIPUAI_IMAGE_GEN_URL,
                        headers=headers,
                        json=payload,
                        timeout=300
                    ) as response:
                        response.raise_for_status()
                        result = await response.json()

                if not result.get("data") or not result["data"][0].get("url"):
                    raise ValueError("API 未返回有效的图片 URL")

                image_url = result["data"][0]["url"]
                
                www_dir = hass.config.path("www")
                img_dir = os.path.join(www_dir, "zhipuai_img")
                if not os.path.exists(img_dir):
                    os.makedirs(img_dir, exist_ok=True)

                filename = os.path.basename(image_url.split('?')[0]) or 'zhipuai_sc.png'
                local_path = os.path.join(img_dir, filename)
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(image_url) as response:
                        if response.status == 200:
                            content = await response.content.read()
                            with open(local_path, "wb") as f:
                                f.write(content)
                            
                            local_url = f"/local/zhipuai_img/{filename}"
                
                hass.bus.async_fire(f"{DOMAIN}_response", {
                    "type": "image_gen",
                    "content": local_url,
                    "success": True
                })
                
                return {
                    "success": True,
                    "message": local_url,
                    "original_url": image_url
                }

            except aiohttp.ClientError as e:
                LOGGER.error(f"API请求失败: {str(e)}")
                raise ServiceValidationError(f"API请求失败: {str(e)}")

        except Exception as e:
            error_msg = f"图像生成失败: {str(e)}"
            LOGGER.error(error_msg)
            return {"success": False, "message": error_msg}

    hass.services.async_register(
        DOMAIN,
        "image_gen",
        handle_image_gen,
        schema=IMAGE_GEN_SCHEMA,
        supports_response=True
    )
