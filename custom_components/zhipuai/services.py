from __future__ import annotations

import base64
import io
import os
import os.path
import numpy as np
from PIL import Image
import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.components import camera
from homeassistant.components.camera import Image as CameraImage
from homeassistant.exceptions import ServiceValidationError
import requests
import json
import time
import asyncio

from .const import (
    DOMAIN,
    LOGGER,
    ZHIPUAI_URL,
    CONF_TEMPERATURE,
    RECOMMENDED_TEMPERATURE,
    CONF_MAX_TOKENS,
    RECOMMENDED_MAX_TOKENS,
)

class ImageProcessor:
    def __init__(self, hass: HomeAssistant):
        self.hass = hass

    async def resize_image(self, image_data: bytes, target_width: int = 1280, is_gif: bool = False) -> str:
        try:
            img_byte_arr = io.BytesIO(image_data)
            img = await self.hass.async_add_executor_job(Image.open, img_byte_arr)
            
            if is_gif and img.format == 'GIF' and getattr(img, "is_animated", False):
                frames = []
                try:
                    for frame in range(img.n_frames):
                        img.seek(frame)
                        new_frame = await self.hass.async_add_executor_job(lambda x: x.convert('RGB'), img.copy())
                        
                        width, height = new_frame.size
                        aspect_ratio = width / height
                        target_height = int(target_width / aspect_ratio)
                        if width > target_width or height > target_height:
                            new_frame = await self.hass.async_add_executor_job(lambda x: x.resize((target_width, target_height)), new_frame)
                        frames.append(new_frame)
                    
                    output = io.BytesIO()
                    frames[0].save(output, save_all=True, append_images=frames[1:], format='GIF', duration=img.info.get('duration', 100), loop=0)
                    base64_image = base64.b64encode(output.getvalue()).decode('utf-8')
                    return base64_image
                except Exception as e:
                    LOGGER.error(f"GIF处理错误: {str(e)}")
                    img.seek(0)
            
            if img.mode == 'RGBA' or img.format == 'GIF':
                img = await self.hass.async_add_executor_job(lambda x: x.convert('RGB'), img)
            
            width, height = img.size
            aspect_ratio = width / height
            target_height = int(target_width / aspect_ratio)

            if width > target_width or height > target_height:
                img = await self.hass.async_add_executor_job(lambda x: x.resize((target_width, target_height)), img)

            img_byte_arr = io.BytesIO()
            await self.hass.async_add_executor_job(lambda i, b: i.save(b, format='JPEG'), img, img_byte_arr)
            base64_image = base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')
            
            return base64_image
        except Exception as e:
            LOGGER.error(f"图像处理错误: {str(e)}")
            raise ServiceValidationError(f"图像处理失败: {str(e)}")

    def _similarity_score(self, previous_frame, current_frame_gray):
        K1 = 0.005
        K2 = 0.015
        L = 255

        C1 = (K1 * L) ** 2
        C2 = (K2 * L) ** 2

        previous_frame_np = np.array(previous_frame, dtype=np.float64)
        current_frame_np = np.array(current_frame_gray, dtype=np.float64)

        mu1 = np.mean(previous_frame_np)
        mu2 = np.mean(current_frame_np)

        sigma1_sq = np.var(previous_frame_np)
        sigma2_sq = np.var(current_frame_np)
        sigma12 = np.cov(previous_frame_np.flatten(), current_frame_np.flatten())[0, 1]

        ssim = ((2 * mu1 * mu2 + C1) * (2 * sigma12 + C2)) / ((mu1**2 + mu2**2 + C1) * (sigma1_sq + sigma2_sq + C2))

        return ssim

IMAGE_ANALYZER_SCHEMA = vol.Schema({
    vol.Required("model", default="glm-4v-flash"): vol.In(["glm-4v-plus", "glm-4v", "glm-4v-flash"]),
    vol.Required("message"): cv.string,
    vol.Optional("image_file"): cv.string,
    vol.Optional("image_entity"): cv.entity_id,
    vol.Optional(CONF_TEMPERATURE, default=RECOMMENDED_TEMPERATURE): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=1.0)),
    vol.Optional(CONF_MAX_TOKENS, default=RECOMMENDED_MAX_TOKENS): vol.All(vol.Coerce(int), vol.Range(min=1, max=1024)),
    vol.Optional("stream", default=False): cv.boolean,
    vol.Optional("target_width", default=1280): vol.All(vol.Coerce(int), vol.Range(min=512, max=1920)),
})

VIDEO_ANALYZER_SCHEMA = vol.Schema(
    {
        vol.Required("model", default="glm-4v-plus"): cv.string,
        vol.Required("message"): cv.string,
        vol.Required("video_file"): cv.string,
        vol.Optional(CONF_TEMPERATURE, default=RECOMMENDED_TEMPERATURE): vol.All(
            vol.Coerce(float), vol.Range(min=0.1, max=1.0)
        ),
        vol.Optional(CONF_MAX_TOKENS, default=RECOMMENDED_MAX_TOKENS): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=1024)
        ),
        vol.Optional("stream", default=False): cv.boolean,
        vol.Optional("target_width", default=1280): vol.All(
            vol.Coerce(int), vol.Range(min=512, max=1920)
        ),
    }
)

async def async_setup_services(hass: HomeAssistant) -> None:
    image_processor = ImageProcessor(hass)
    
    async def handle_image_analyzer(call: ServiceCall) -> None:
        try:
            config_entries = hass.config_entries.async_entries(DOMAIN)
            if not config_entries:
                raise ValueError("未找到 ZhipuAI")
            api_key = config_entries[0].data.get("api_key")
            if not api_key:
                raise ValueError("在配置中找不到 API 密钥")

            image_data = None
            if image_file := call.data.get("image_file"):
                try:
                    if not os.path.isabs(image_file):
                        image_file = os.path.join(hass.config.config_dir, image_file)
                    
                    if os.path.isdir(image_file):
                        raise ServiceValidationError(f"提供的路径是一个目录: {image_file}")
                    
                    if not os.path.exists(image_file):
                        raise ServiceValidationError(f"图片文件不存在: {image_file}")
                    
                    with open(image_file, "rb") as f:
                        image_data = f.read()
                except IOError as e:
                    LOGGER.error(f"读取图片文件失败 {image_file}: {str(e)}")
                    raise ServiceValidationError(f"读取图片文件失败: {str(e)}")
                
            elif image_entity := call.data.get("image_entity"):
                try:
                    if not image_entity.startswith("camera."):
                        raise ServiceValidationError(f"无效的摄像头实体ID: {image_entity}")

                    if not hass.states.get(image_entity):
                        raise ServiceValidationError(f"摄像头实体不存在: {image_entity}")

                    try:
                        image: CameraImage = await camera.async_get_image(hass, image_entity, timeout=10)
                        
                        if not image or not image.content:
                            raise ServiceValidationError(f"无法从摄像头获取图片: {image_entity}")
                        
                        image_data = image.content
                        base64_image = await image_processor.resize_image(image_data, target_width=call.data.get("target_width", 1280), is_gif=True)
                        
                    except (camera.CameraEntityImageError, TimeoutError) as e:
                        raise ServiceValidationError(f"获取摄像头图片失败: {str(e)}")

                except Exception as e:
                    LOGGER.error(f"从实体获取图片失败 {image_entity}: {str(e)}")
                    raise ServiceValidationError(f"从实体获取图片失败: {str(e)}")
            
            if not image_data:
                raise ServiceValidationError("未提供图片数据")

            try:
                base64_image = await image_processor.resize_image(image_data, target_width=call.data.get("target_width", 1280))
            except Exception as e:
                LOGGER.error(f"图像处理失败: {str(e)}")
                raise ServiceValidationError(f"图像处理失败: {str(e)}")

            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {api_key}'
            }
            payload = {
                "model": call.data["model"],
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                }
                            },
                            {
                                "type": "text",
                                "text": call.data["message"]
                            }
                        ]
                    }
                ],
                "stream": call.data.get("stream", False),
                "temperature": call.data.get(CONF_TEMPERATURE, RECOMMENDED_TEMPERATURE),
                "max_tokens": call.data.get(CONF_MAX_TOKENS, RECOMMENDED_MAX_TOKENS),
            }

            try:
                response = await hass.async_add_executor_job(lambda: requests.post(ZHIPUAI_URL, headers=headers, json=payload, stream=call.data.get("stream", False), timeout=30))
                response.raise_for_status()
            except requests.exceptions.RequestException as e:
                LOGGER.error(f"API请求失败: {str(e)}")
                raise ServiceValidationError(f"API请求失败: {str(e)}")

            if call.data.get("stream", False):
                event_id = f"zhipuai_response_{int(time.time())}"
                
                try:
                    hass.bus.async_fire(f"{DOMAIN}_stream_start", {"event_id": event_id, "type": "image_analysis"})
                    
                    accumulated_text = ""
                    for line in response.iter_lines():
                        if line:
                            try:
                                data = line.decode('utf-8').replace('data: ', '')
                                if data == '[DONE]':
                                    break
                                
                                json_data = json.loads(data)
                                if 'choices' in json_data and len(json_data['choices']) > 0:
                                    content = json_data['choices'][0].get('delta', {}).get('content', '')
                                    if content:
                                        accumulated_text += content
                                        hass.bus.async_fire(f"{DOMAIN}_stream_token", {"event_id": event_id, "content": content, "full_content": accumulated_text})
                                        
                            except json.JSONDecodeError as e:
                                LOGGER.error(f"解析流式响应失败: {str(e)}")
                                continue
                    
                    hass.bus.async_fire(f"{DOMAIN}_stream_end", {"event_id": event_id, "full_content": accumulated_text})
                    
                    hass.bus.async_fire(f"{DOMAIN}_response", {"type": "image_analysis", "content": accumulated_text, "success": True})
                    return {"success": True, "event_id": event_id, "message": accumulated_text}
                    
                except Exception as e:
                    error_msg = f"处理流式响应时出错: {str(e)}"
                    LOGGER.error(error_msg)
                    hass.bus.async_fire(f"{DOMAIN}_stream_error", {"event_id": event_id, "error": error_msg})
                    return {"success": False, "message": error_msg}
            else:
                result = response.json()
                if result.get("choices") and len(result["choices"]) > 0:
                    content = result["choices"][0].get("message", {}).get("content", "")
                    hass.bus.async_fire(f"{DOMAIN}_response", {"type": "image_analysis", "content": content, "success": True})
                    return {"success": True, "message": content}
                else:
                    error_msg = "No response from API"
                    return {"success": False, "message": error_msg}
        except Exception as e:
            error_msg = f"Image analysis failed: {str(e)}"
            LOGGER.error(f"图像分析错误: {str(e)}")
            return {"success": False, "message": error_msg}

    async def handle_video_analyzer(call: ServiceCall) -> None:
        try:
            config_entries = hass.config_entries.async_entries(DOMAIN)
            if not config_entries:
                raise ValueError("No ZhipuAI configuration found")
            api_key = config_entries[0].data.get("api_key")
            if not api_key:
                raise ValueError("API key not found in configuration")

            video_file = call.data["video_file"]
            if not os.path.isabs(video_file):
                video_file = os.path.join(hass.config.config_dir, video_file)
            
            if not os.path.isfile(video_file):
                LOGGER.error(f"视频文件未找到或是目录: {video_file}")
                return {"success": False, "message": f"视频文件未找到或是目录: {video_file}"}

            try:
                def read_video_file():
                    with open(video_file, "rb") as f:
                        return f.read()
                video_data = await hass.async_add_executor_job(read_video_file)
            except IOError as e:
                LOGGER.error(f"读取视频文件失败 {video_file}: {str(e)}")
                return {"success": False, "message": f"读取视频文件失败: {str(e)}"}

            if call.data.get("model") != "glm-4v-plus":
                LOGGER.warning("视频分析仅支持glm-4v-plus模型，强制使用glm-4v-plus")
            
            video_size = len(video_data) / (1024 * 1024)
            if video_size > 20:
                LOGGER.error(f"视频文件大小 ({video_size:.1f}MB) 超过20MB限制")
                return {"success": False, "message": f"视频文件大小 ({video_size:.1f}MB) 超过20MB限制"}

            if not video_file.lower().endswith('.mp4'):
                LOGGER.error("视频文件必须是MP4格式")
                return {"success": False, "message": "视频文件必须是MP4格式"}

            base64_video = base64.b64encode(video_data).decode('utf-8')

            payload = {
                "model": "glm-4v-plus",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "video_url",
                                "video_url": {
                                    "url": base64_video
                                }
                            },
                            {
                                "type": "text",
                                "text": call.data["message"]
                            }
                        ]
                    }
                ],
                "stream": call.data.get("stream", False)
            }

            if CONF_TEMPERATURE in call.data:
                payload["temperature"] = call.data[CONF_TEMPERATURE]
            if CONF_MAX_TOKENS in call.data:
                payload["max_tokens"] = call.data[CONF_MAX_TOKENS]

            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {api_key}'
            }

            try:
                for attempt in range(3):
                    try:
                        response = await hass.async_add_executor_job(
                            lambda: requests.post(
                                ZHIPUAI_URL,
                                headers=headers,
                                json=payload,
                                stream=call.data.get("stream", False),
                                timeout=30
                            )
                        )
                        response.raise_for_status()
                        break
                    except requests.exceptions.RequestException as e:
                        if attempt == 2:  
                            raise
                        if response.status_code == 429:  
                            await asyncio.sleep(2)  
                        else:
                            raise
            except requests.exceptions.RequestException as e:
                LOGGER.error(f"API请求失败: {str(e)}")
                return {"success": False, "message": f"API请求失败: {str(e)}"}

            if call.data.get("stream", False):
                event_id = f"zhipuai_response_{int(time.time())}"
                
                try:
                    hass.bus.async_fire(f"{DOMAIN}_stream_start", {"event_id": event_id, "type": "video_analysis"})
                    
                    accumulated_text = ""
                    for line in response.iter_lines():
                        if line:
                            try:
                                line_text = line.decode('utf-8').strip()
                                if line_text.startswith('data: '):
                                    line_text = line_text[6:]
                                if line_text == '[DONE]':
                                    break
                                
                                json_data = json.loads(line_text)
                                if 'choices' in json_data and json_data['choices']:
                                    choice = json_data['choices'][0]
                                    if 'delta' in choice and 'content' in choice['delta']:
                                        content = choice['delta']['content']
                                        accumulated_text += content
                                        hass.bus.async_fire(
                                            f"{DOMAIN}_stream_token",
                                            {
                                                "event_id": event_id,
                                                "token": content,
                                                "complete_text": accumulated_text
                                            }
                                        )
                            except json.JSONDecodeError as e:
                                LOGGER.error(f"解析流式响应失败: {str(e)}")
                                continue
                    
                    hass.bus.async_fire(f"{DOMAIN}_stream_end", {
                        "event_id": event_id,
                        "complete_text": accumulated_text
                    })
                    return {"success": True, "message": accumulated_text}
                except Exception as e:
                    LOGGER.error(f"处理流式响应时出错: {str(e)}")
                    return {"success": False, "message": f"处理流式响应时出错: {str(e)}"}
            else:
                result = response.json()
                if result.get("choices") and len(result["choices"]) > 0:
                    content = result["choices"][0].get("message", {}).get("content", "")
                    hass.bus.async_fire(f"{DOMAIN}_response", {"type": "video_analysis", "content": content, "success": True})
                    return {"success": True, "message": content}
                else:
                    error_msg = "No response from API"
                    return {"success": False, "message": error_msg}
        except Exception as e:
            error_msg = f"Video analysis failed: {str(e)}"
            LOGGER.error(f"视频分析错误: {str(e)}")
            return {"success": False, "message": error_msg}

    hass.services.async_register(DOMAIN, "image_analyzer", handle_image_analyzer, schema=IMAGE_ANALYZER_SCHEMA, supports_response=True)

    hass.services.async_register(DOMAIN, "video_analyzer", handle_video_analyzer, schema=VIDEO_ANALYZER_SCHEMA, supports_response=True)

    @callback
    def async_unload_services() -> None:
        hass.services.async_remove(DOMAIN, "image_analyzer")
        hass.services.async_remove(DOMAIN, "video_analyzer")

    return async_unload_services
