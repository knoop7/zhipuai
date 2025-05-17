"""

所有提示词必须遵循以下规则:
1. 不可以使用例如举例，只说明参数格式和用途
2. 参数说明要简洁明了，只描述参数类型和用途
3. 每个工具的使用说明要清晰，避免冗余
4. 提示词要突出工具的核心功能和关键参数
5. 保持提示词的一致性和可维护性
6. 强调必须使用工具调用，禁止直接文本回复控制相关问题

理解:
- 提示词是工具使用的指导，不是示例集合
- 参数说明要突出必要性和可选性
- 工具说明要突出核心功能和使用场景
- 保持提示词的简洁性和可维护性
- 所有设备控制和状态查询必须通过工具实现
"""

from typing import List, Dict, Any, Set

LIGHT_CONTROL = {
    "prompt": """

对于灯光控制请求，必须正确使用工具：


使用HassLightSetAllIntent工具，参数说明：
- name: 具体灯具名称
- domain: 设备域名，默认为'light'，可选'switch'
- action: 操作类型，表示开灯或关灯
- color: 颜色名称
- brightness: 亮度值(0-100)
- color_temp: 色温，可用描述词或数值(2600-6500)


控制所有灯须知：
1. 禁止将'all_lights'作为name参数值
2. 使用HassTurnOn/HassTurnOff工具：
   - domain参数指定为'light'控制所有灯
   - area参数指定区域控制该区域内所有灯


当light域设备无法控制时：
1. 将domain参数更改为'switch'
2. 使用HassTurnOn/HassTurnOff工具替代HassLightSetAllIntent
3. 多设备控制始终使用HassTurnOn/HassTurnOff工具

警告：name参数值禁止使用'all_lights'，将导致工具执行错误
""",
    "keywords": ["灯", "亮", "灯光", "灯泡", "light", "lamp", "色", "颜色", "亮度", "开灯", "关灯"],
    "tools": ["HassLightSetAllIntent", "HassLightSet", "HassTurnOn", "HassTurnOff"]
}

WEB_SEARCH = {
    "prompt": """

使用ZhipuAIWebSearch进行网络搜索
基本搜索: ZhipuAIWebSearch(query='上海天气')
指定时间搜索: ZhipuAIWebSearch(query='新闻热点', time_query='今天')
指定搜索引擎: ZhipuAIWebSearch(query='人工智能发展', search_engine='gj')
完整搜索: ZhipuAIWebSearch(query='天气预报', time_query='明天', search_engine='kq')

参数说明:
- query: 搜索内容(必填)
- time_query: 时间约束，如'今天'/'昨天'/'明天'，自动转换为YYYY-MM-DD格式
- search_engine: 搜索引擎，'jc'(基础版)/'gj'(高阶版)/'kq'(夸克)/'sg'(搜狗)
""",
    "keywords": ["搜索", "查询", "search", "联网", "互联网", "上网", "百度", "谷歌", "必应", "夸克", "搜狗"],
    "tools": ["ZhipuAIWebSearch"],
    "tool_definition": {
        "type": "function",
        "function": {
            "name": "ZhipuAIWebSearch",
            "description": "Search web information with time constraints and engine selection",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索内容，例如：'上海天气'"},
                    "time_query": {"type": "string", "description": "时间约束，使用'今天','昨天','明天'等值，系统会自动转换为YYYY-MM-DD格式"},
                    "search_engine": {"type": "string", "description": "搜索引擎选择: 'jc'(基础版,默认),'gj'(高阶版),'kq'(夸克),'sg'(搜狗)"}
                },
                "required": ["query"]
            }
        }
    }
}

CLIMATE_CONTROL = {
    "prompt": """

必须使用ClimateSetTemperature/ClimateSetMode/ClimateSetFanMode进行温控器控制，禁止直接通过文本回答
参数说明:
- name: 空调名称
- temperature: 温度值
- mode: 模式(cool/heat/auto/fan_only/dry/off)
- fan_mode: 风速模式(auto/low/medium/high)
""",
    "keywords": ["空调", "温度", "制冷", "制热", "冷气", "暖气", "风速", "AC", "climate"],
    "tools": ["ClimateSetTemperature", "ClimateSetMode", "ClimateSetFanMode"]
}

MEDIA_PLAYER = {
    "prompt": """

必须使用MassPlayMediaAssist进行媒体播放控制：


- query: 要播放的内容(必填)
- name: 指定播放设备(必填)


1. name参数只能使用实际设备名称，禁止使用设备名称作为query值
2. 对于已存在的播放设备，必须指定正确的设备名称，不要将设备名重复用作query
3. 使用query参数指定要播放的歌曲、歌手或内容
4. 控制特定播放器播放时，使用name参数指定播放器名称


当播放器无法播放时：
1. 检查播放器名称是否正确，避免将名称作为query参数使用
2. 使用HassTurnOn/HassMediaPlay代替MassPlayMediaAssist
3. 确保query参数包含要播放的内容，而不是设备名称

警告：请勿将同一参数值同时用于name和query，这将导致工具执行错误
""",
    "keywords": ["播放", "音乐", "歌曲", "歌手", "视频", "电影", "play", "music", "song"],
    "tools": ["MassPlayMediaAssist", "HassMediaPlay", "HassTurnOn"]
}

MEDIA_PLAYER_STATUS = {
    "prompt": """

必须使用GetLiveContext获取媒体播放器当前状态：


- domain: 必须为'media_player'
- entity_id: 播放器实体ID(可选)


1. 查询播放器状态必须使用GetLiveContext工具
2. 查询后，必须基于查询结果提供当前播放信息
3. 不要尝试直接通过文本回答播放状态相关问题


若状态查询失败：
1. 检查播放器实体ID是否正确
2. 使用GetLiveContext查询所有media_player域设备
3. 确保正确指定了domain='media_player'参数

警告：查询播放器状态必须通过工具调用完成，禁止直接回答
""",
    "keywords": ["正在播放", "谁唱的", "什么歌", "什么状态", "播放状态", "歌曲信息", "歌名", "音乐信息", "artist", "song", "track", "playing", "spotify", "播放器", "歌手", "专辑"],
    "tools": ["GetLiveContext"]
}

TIMER = {
    "prompt": """

使用HassTimerIntent设置和管理定时器
参数说明:
- action: 操作类型，'set'/'stop'/'cancel'
- duration: 时长，如'5分钟'/'1小时30分钟'
- timer_name: 定时器名称(可选)
""",
    "keywords": ["计时", "定时", "提醒", "分钟后", "小时后", "timer"],
    "tools": ["HassTimerIntent"]
}

COVER_CONTROL = {
    "prompt": """

必须使用CoverControlAll控制窗帘，禁止直接通过文本回答
参数说明:
- action: 'open'/'close'，控制所有窗帘
- name: 指定窗帘名称，与domain='cover'一起使用
""",
    "keywords": ["窗帘", "curtain", "百叶窗", "卷帘", "遮阳"],
    "tools": ["CoverControlAll", "ZHIPUAI_CoverGetStateIntent"]
}

NOTIFY_INTENT = {
    "prompt": """

HassNotifyIntent 用于创建持久性通知
参数: message(通知内容)
""",
    "keywords": ["记住", "记录", "备忘", "通知", "提醒我", "记一下", "发送通知", "创建通知"],
    "tools": ["HassNotifyIntent"]
}

CAMERA_ANALYZE = {
    "prompt": """

ZhipuAICameraAnalyze 用于分析摄像头画面
参数: camera_name(摄像头名称), question(问题)
""",
    "keywords": ["摄像头", "监控", "画面", "相机", "camera", "看到", "画面", "监视"],
    "tools": ["ZhipuAICameraAnalyze"]
}

CLIMATE_ADVANCED = {
    "prompt": """

ClimateSetHumidity: 设置湿度(10-100)
ClimateSetSwingMode: 设置摆风模式(vertical/horizontal/both/off)
""",
    "keywords": ["湿度", "摆风", "上下摆动", "左右摆动", "humidity", "swing", "oscillate"],
    "tools": ["ClimateSetHumidity", "ClimateSetSwingMode"]
}

COVER_POSITION = {
    "prompt": """

ZHIPUAI_CoverSetPositionIntent 用于设置窗帘位置
参数: name(窗帘名称), position(位置0-100)
""",
    "keywords": ["窗帘位置", "窗帘百分比", "半开", "拉开一点", "position", "拉到"],
    "tools": ["ZHIPUAI_CoverSetPositionIntent"]
}

IMAGE_GEN = {
    "prompt": """

ZhipuAIImageGen 用于生成图像
参数: prompt(图像描述)
""",
    "keywords": ["生成图片", "画一张", "创建图像", "图像生成", "AI绘图", "绘制", "image", "picture", "draw"],
    "tools": ["ZhipuAIImageGen"]
}

DEVICE_STATUS = {
    "prompt": """

必须使用GetLiveContext获取设备当前状态，禁止直接通过文本回答
参数说明:
- domain: 设备类型('light'/'switch'/'sensor'等)
- entity_id: 实体ID(可选)
""",
    "keywords": ["状态", "开着吗", "关着吗", "温度", "湿度", "电量", "多少度", "亮着吗", "什么颜色", "什么亮度", "状况", "情况", "现在", "当前"],
    "tools": ["GetLiveContext"]
}

TOOL_USAGE_MANDATORY = {
    "prompt": """

必须通过工具调用实现所有设备控制和状态查询:


1. 所有家居设备控制请求必须使用工具调用，禁止文本回复
2. 设备名称+动作指令组合必须识别为控制指令并使用工具
3. 播放器控制必须使用HassMediaPlay工具，含以下参数:
   - name: 播放器名称
   - domain: 'media_player'
4. 对于不确定的控制指令，必须优先尝试使用工具
5. 即使预计操作可能无法完成，也必须通过工具尝试执行


- 媒体播放器: HassMediaPlay > MassPlayMediaAssist 


- 一个工具失败后，尝试使用替代工具
- 仅当所有可能工具都尝试失败后，才可告知用户操作无法完成
- 工具调用失败后，调整参数格式并使用替代工具


- 禁止直接回复"我无法控制"或"请使用其他方式控制"
- 禁止跳过工具调用直接回复文本
- 禁止以任何理由拒绝尝试使用工具执行用户请求
""",
    "keywords": ["控制", "查询", "状态", "打开", "关闭", "设置", "调整", "家居", "开", "关", "实体", "播放", "暂停", "spotify"],
    "tools": ["GetLiveContext","HassMediaPlay", "HassMediaPause"]
}

MEDIA_CONTROL = {
    "prompt": """

必须使用工具控制媒体播放器，严禁直接文本回答


1. 设备名称+动作指令组合必须识别为控制指令并使用工具
2. 播放器控制必须使用工具，禁止以任何理由拒绝尝试
3. 即使预计操作可能不成功，也必须通过工具尝试执行


- HassMediaPlay/HassMediaPause工具参数:
  - name: 播放器名称
  - domain: 必须为'media_player'

""",
    "keywords": ["暂停", "继续", "停止", "播放", "下一首", "上一首", "下一曲", "上一曲", "音量", "静音", "spotify"],
    "tools": ["HassTurnOn", "HassTurnOff", "HassMediaPlay", "HassMediaPause", "HassMediaStop", "HassVolumeSet", "HassVolumeMute"]
}

SWITCH_CONTROL = {
    "prompt": """

必须使用HassTurnOn/HassTurnOff控制开关设备，禁止直接通过文本回答
参数说明:
- name: 设备名称
- domain: 必须为'switch'
""",
    "keywords": ["开关", "插座", "电源", "打开", "关闭", "switch"],
    "tools": ["HassTurnOn", "HassTurnOff"]
}

SCENE_CONTROL = {
    "prompt": """

必须使用HassTurnOn激活场景，禁止直接通过文本回答
参数说明:
- name: 场景名称
- domain: 必须为'scene'
""",
    "keywords": ["场景", "模式", "情景", "氛围", "启动场景", "激活场景", "scene"],
    "tools": ["HassTurnOn"]
}

GROUP_CONTROL = {
    "prompt": """

必须使用HassTurnOn/HassTurnOff控制群组设备，禁止直接通过文本回答
参数说明:
- name: 群组名称
- domain: 必须为'group'
""",
    "keywords": ["群组", "所有", "全部", "一起", "group"],
    "tools": ["HassTurnOn", "HassTurnOff"]
}

ALL_FEATURES = [
    LIGHT_CONTROL, 
    WEB_SEARCH, 
    CLIMATE_CONTROL, 
    MEDIA_PLAYER,
    MEDIA_PLAYER_STATUS,
    TIMER, 
    COVER_CONTROL,
    NOTIFY_INTENT,
    CAMERA_ANALYZE,
    CLIMATE_ADVANCED,
    COVER_POSITION,
    IMAGE_GEN,
    DEVICE_STATUS,
    MEDIA_CONTROL,
    SWITCH_CONTROL,
    SCENE_CONTROL,
    GROUP_CONTROL,
    TOOL_USAGE_MANDATORY 
]

def detect_features_in_text(text: str) -> List[Dict]:
    if not text:
        return []
    
    text_lower = text.lower()
    
    device_patterns = {
        "media": {
            "devices": ["留声机", "音箱", "播放器", "音响", "天猫精灵", "小爱", "Echo", "Alexa"],
            "actions": ["播放", "放", "搜索", "听"],
            "features": [MEDIA_PLAYER, MEDIA_CONTROL]
        },
        "light": {
            "devices": ["灯", "灯具", "照明"],
            "actions": ["开", "关", "亮", "暗", "变色"],
            "features": [LIGHT_CONTROL]
        },
        "climate": {
            "devices": ["空调", "温控", "暖气"],
            "actions": ["开", "关", "调", "温度"],
            "features": [CLIMATE_CONTROL]
        },
        "cover": {
            "devices": ["窗帘", "百叶窗", "卷帘"],
            "actions": ["开", "关", "拉"],
            "features": [COVER_CONTROL]
        }
    }
    
    for category, pattern in device_patterns.items():
        if any(d in text_lower for d in pattern["devices"]):
            if category == "media" and ("搜索" in text_lower or "播放" in text_lower or "放" in text_lower):
                return pattern["features"]
            elif any(a in text_lower for a in pattern["actions"]):
                return pattern["features"]
    
    if "搜索" in text_lower or "查询" in text_lower or "查找" in text_lower:
        media_terms = ["歌", "歌曲", "音乐", "专辑", "播放"]
        web_terms = ["网上", "网络", "百度", "资料", "新闻"]
        
        if any(term in text_lower for term in media_terms):
            return [MEDIA_PLAYER, MEDIA_CONTROL]
        elif any(term in text_lower for term in web_terms):
            return [WEB_SEARCH]
    
    color_terms = ["红色", "蓝色", "绿色", "黄色", "白色", "黑色"]
    if any(color in text_lower for color in color_terms) and any(term in text_lower for term in ["灯", "灯光"]):
        return [LIGHT_CONTROL]
    
    if "播放" in text_lower or "音乐" in text_lower or "歌曲" in text_lower:
        return [MEDIA_PLAYER, MEDIA_CONTROL]
    elif "灯" in text_lower and ("开" in text_lower or "关" in text_lower):
        return [LIGHT_CONTROL]
    
    matched = []
    for feature in ALL_FEATURES:
        if feature not in [LIGHT_CONTROL, MEDIA_PLAYER, MEDIA_CONTROL, WEB_SEARCH, 
                          CLIMATE_CONTROL, COVER_CONTROL, DEVICE_STATUS]:
            continue
            
        
        count = sum(1 for k in feature["keywords"] if k.lower() in text_lower)
        if count >= 2 or (count == 1 and 
                         any(len(k) > 3 and k.lower() in text_lower 
                             for k in feature["keywords"])):
            matched.append(feature)
    
    
    if len(matched) > 2:
        scores = []
        for feature in matched:
            
            keyword_score = sum(2 if len(k) > 3 else 1 
                              for k in feature["keywords"] 
                              if k.lower() in text_lower)
            scores.append((feature, keyword_score))
        
        matched = [f for f, _ in sorted(scores, key=lambda x: x[1], reverse=True)[:2]]
    
    return matched

def detect_keywords_in_text(text: str) -> List[str]:
    if not text:
        return []
    text_lower = text.lower()
    keywords = []
    for feature in ALL_FEATURES:
        for keyword in feature["keywords"]:
            if keyword.lower() in text_lower and keyword not in keywords:
                keywords.append(keyword)
    return keywords

def get_prompts_for_text(text: str) -> str:
    if not text:
        return ""
    matched_features = detect_features_in_text(text)
    if not matched_features:
        return ""
    prompts = [feature["prompt"] for feature in matched_features]
    return "\n\n".join(list(dict.fromkeys(prompts)))

def get_tools_for_text(text: str, existing_tools=None) -> List[Dict]:
    if not text:
        return []
    new_tools = []
    existing_tool_names = []
    if existing_tools:
        existing_tool_names = [t.get("function", {}).get("name", "") for t in existing_tools]
    matched_features = detect_features_in_text(text)
    for feature in matched_features:
        if "tool_definition" in feature:
            tool_name = feature["tool_definition"]["function"]["name"]
            if tool_name not in existing_tool_names:
                new_tools.append(feature["tool_definition"])
    return new_tools

def get_prompts_for_tools(tools) -> str:
    if not tools:
        return ""
    tool_names = [t.get("function", {}).get("name", "") for t in tools]
    matched_features = []
    for feature in ALL_FEATURES:
        if any(tool in feature.get("tools", []) for tool in tool_names):
            matched_features.append(feature)
    prompts = [feature["prompt"] for feature in matched_features]
    return "\n\n".join(list(dict.fromkeys(prompts)))

def get_basic_tools_guide(tool_choice_setting="auto") -> List[str]:
    tools_desc_parts = [
        "Use the following tools to execute operations. Each tool has a specific purpose.\n",
        "\nImportant Usage Guidelines:"
    ]
    if tool_choice_setting == "force":
        tools_desc_parts.append(
            "\n1. You MUST use tools for ALL operations - direct text responses for device control are not allowed"
            "\n2. For device control, you MUST call HassTurnOn, HassTurnOff or other appropriate tools"
            "\n3. For querying current device states, you MUST use GetLiveContext tool"
            "\n4. NEVER attempt to control devices through conversation - ALWAYS use tools"
        )
    else:
        tools_desc_parts.append(
            "\n1. Always use tools for device control instead of direct conversation"
            "\n2. For device control, prefer using just name and domain parameters"
            "\n3. For area control, prefer passing just area parameter"
            "\n4. For querying current device states, MUST use GetLiveContext tool"
        )
    return tools_desc_parts 

def is_web_search_request(text: str) -> bool:
    if not text:
        return False
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in WEB_SEARCH["keywords"])

def get_web_search_tool():
    return WEB_SEARCH["tool_definition"]