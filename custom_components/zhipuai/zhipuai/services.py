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
from homeassistant.components.camera.const import DOMAIN as CAMERA_DOMAIN
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
        self.www_dir = os.path.join(self.hass.config.config_dir, 'www')
        self.frame_dir = os.path.join(self.www_dir, 'zhipuai_cam')
        if not os.path.exists(self.frame_dir):
            os.makedirs(self.frame_dir, exist_ok=True)

    async def save_frame(self, image_data: bytes, entity_id: str, enhanced_img: Image.Image = None) -> str:
        try:
            camera_name = entity_id.split('.')[1]
            filename = f"{camera_name}.jpg"
            filepath = os.path.join(self.frame_dir, filename)
            
            def _save_image():
                if enhanced_img:
                    enhanced_img.save(filepath, 'JPEG', quality=95)
                else:
                    with open(filepath, 'wb') as f:
                        f.write(image_data)
            
            await self.hass.async_add_executor_job(_save_image)
            return f"/local/zhipuai_cam/{filename}"
        except Exception as e:
            LOGGER.info(f"保存分析帧失败: {str(e)}")
            return None

    def enhance_center(self, img, crop_ratio=0.5):
        orig_width, orig_height = img.size
        
        crop_width = int(orig_width * crop_ratio)
        crop_height = int(orig_height * crop_ratio)
        
        crop_width = max(100, crop_width)
        crop_height = max(100, crop_height)
        
        center_x = orig_width // 2
        center_y = orig_height // 2
        
        left = center_x - (crop_width // 2)
        top = center_y - (crop_height // 2)
        right = left + crop_width
        bottom = top + crop_height
        
        if left < 0:
            right -= left
            left = 0
        if top < 0:
            bottom -= top
            top = 0
        if right > orig_width:
            left -= (right - orig_width)
            right = orig_width
        if bottom > orig_height:
            top -= (bottom - orig_height)
            bottom = orig_height
            
        img = img.crop((left, top, right, bottom))
        img = img.resize((1920, 1080), Image.Resampling.LANCZOS)
        
        return img

    async def resize_image(self, image_data: bytes, is_gif: bool = False, save_frame: bool = False, entity_id: str = None, crop_ratio: float = 0.5) -> str:
        try:
            img_byte_arr = io.BytesIO(image_data)
            img = await self.hass.async_add_executor_job(Image.open, img_byte_arr)
            
            if is_gif and img.format == 'GIF' and getattr(img, "is_animated", False):
                frames = []
                try:
                    for frame in range(img.n_frames):
                        img.seek(frame)
                        new_frame = await self.hass.async_add_executor_job(lambda x: x.convert('RGB'), img.copy())
                        new_frame = await self.hass.async_add_executor_job(
                            self.enhance_center, new_frame, crop_ratio
                        )
                        frames.append(new_frame)
                    
                    if save_frame and entity_id:
                        await self.save_frame(image_data, entity_id, frames[0])
                    
                    output = io.BytesIO()
                    frames[0].save(
                        output, 
                        save_all=True, 
                        append_images=frames[1:], 
                        format='GIF',
                        duration=img.info.get('duration', 100),
                        loop=0,
                        quality=95
                    )
                    base64_image = base64.b64encode(output.getvalue()).decode('utf-8')
                    return base64_image
                except Exception as e:
                    LOGGER.info(f"GIF处理错误: {str(e)}")
                    img.seek(0)
            
            if img.mode == 'RGBA' or img.format == 'GIF':
                img = await self.hass.async_add_executor_job(lambda x: x.convert('RGB'), img)
            
            enhanced_img = await self.hass.async_add_executor_job(
                self.enhance_center, img, crop_ratio
            )
            
            if save_frame and entity_id:
                await self.save_frame(image_data, entity_id, enhanced_img)

            img_byte_arr = io.BytesIO()
            await self.hass.async_add_executor_job(
                lambda i, b: i.save(b, format='JPEG', quality=95, optimize=True), 
                enhanced_img, 
                img_byte_arr
            )
            base64_image = base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')
            
            return base64_image
        except Exception as e:
            LOGGER.info(f"图像处理错误: {str(e)}")
            raise ValueError(f"图像处理失败: {str(e)}")

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
    vol.Optional("save_frame", default=False): cv.boolean,
    vol.Optional("crop_ratio", default=0.5): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=1.0)),
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
    }
)

async def async_setup_services(hass: HomeAssistant) -> None:
    image_processor = ImageProcessor(hass)
    
    async def handle_image_analyzer(call: ServiceCall) -> None:
        try:
            config_entries = hass.config_entries.async_entries(DOMAIN)
            if not config_entries:
                error_msg = "未找到 ZhipuAI"
                LOGGER.info(error_msg)
                raise ValueError(error_msg)
                
            api_key = config_entries[0].data.get("api_key")
            if not api_key:
                error_msg = "在配置中找不到 API 密钥"
                LOGGER.info(error_msg)
                raise ValueError(error_msg)

            image_data = None
            if image_file := call.data.get("image_file"):
                try:
                    if not os.path.isabs(image_file):
                        image_file = os.path.join(hass.config.config_dir, image_file)
                    
                    if os.path.isdir(image_file):
                        error_msg = f"提供的路径是一个目录: {image_file}"
                        LOGGER.info(error_msg)
                        raise ValueError(error_msg)
                    
                    if not os.path.exists(image_file):
                        error_msg = f"图片文件不存在: {image_file}"
                        LOGGER.info(error_msg)
                        raise ValueError(error_msg)
                    
                    with open(image_file, "rb") as f:
                        image_data = f.read()
                except IOError as e:
                    error_msg = f"读取图片文件失败: {str(e)}"
                    LOGGER.info(error_msg)
                    raise ValueError(error_msg)
                
            elif image_entity := call.data.get("image_entity"):
                try:
                    if not image_entity.startswith("camera."):
                        error_msg = f"无效的摄像头实体ID: {image_entity}"
                        LOGGER.info(error_msg)
                        raise ValueError(error_msg)

                    if not hass.states.get(image_entity):
                        error_msg = f"摄像头实体不存在: {image_entity}"
                        LOGGER.info(error_msg)
                        raise ValueError(error_msg)

                    try:
                        image = await camera.async_get_image(hass, image_entity, timeout=10)
                        
                        if not image or not image.content:
                            error_msg = f"无法从摄像头获取图片: {image_entity}"
                            LOGGER.info(error_msg)
                            raise ValueError(error_msg)
                        
                        image_data = image.content
                        
                        if call.data.get("save_frame", False):
                            frame_url = await image_processor.save_frame(image_data, image_entity)
                            if frame_url:
                                LOGGER.info(f"分析帧已保存: {frame_url}")
                        
                        base64_image = await image_processor.resize_image(image_data, is_gif=True, save_frame=call.data.get("save_frame", False), entity_id=image_entity, crop_ratio=call.data.get("crop_ratio", 0.5))
                        
                    except (camera.CameraEntityImageError, TimeoutError) as e:
                        error_msg = f"获取摄像头图片失败: {str(e)}"
                        LOGGER.info(error_msg)
                        raise ValueError(error_msg)

                except Exception as e:
                    error_msg = f"从实体获取图片失败: {str(e)}"
                    LOGGER.info(error_msg)
                    raise ValueError(error_msg)
            
            if not image_data:
                error_msg = "未提供图片数据"
                LOGGER.info(error_msg)
                raise ValueError(error_msg)

            try:
                base64_image = await image_processor.resize_image(image_data, save_frame=call.data.get("save_frame", False), entity_id=call.data.get("image_entity"), crop_ratio=call.data.get("crop_ratio", 0.5))
            except Exception as e:
                error_msg = f"图像处理失败: {str(e)}"
                LOGGER.info(error_msg)
                raise ValueError(error_msg)

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
                return {"success": False, "message": f"API请求失败: {str(e)}"}

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
                    LOGGER.info(error_msg)
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
            LOGGER.info(f"图像分析错误: {str(e)}")
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
                error_msg = f"视频文件未找到或是目录: {video_file}"
                LOGGER.info(error_msg)
                raise ValueError(error_msg)

            try:
                def read_video_file():
                    try:
                        with open(video_file, "rb") as f:
                            return f.read()
                    except IOError as e:
                        error_msg = f"读取视频文件失败: {str(e)}"
                        LOGGER.info(error_msg)
                        raise ValueError(error_msg)
                        
                video_data = await hass.async_add_executor_job(read_video_file)
            except Exception as e:
                error_msg = f"读取视频文件失败: {str(e)}"
                LOGGER.info(error_msg)
                raise ValueError(error_msg)

            if call.data.get("model") != "glm-4v-plus":
                LOGGER.info("视频分析仅支持glm-4v-plus模型，强制使用glm-4v-plus")
            
            video_size = len(video_data) / (1024 * 1024)
            if video_size > 20:
                error_msg = f"视频文件大小 ({video_size:.1f}MB) 超过20MB限制"
                LOGGER.info(error_msg)
                raise ValueError(error_msg)

            if not video_file.lower().endswith('.mp4'):
                error_msg = "视频文件必须是MP4格式"
                LOGGER.info(error_msg)
                raise ValueError(error_msg)

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
                    error_msg = "API 无响应"
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
