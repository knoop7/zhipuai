<div align="center">


# 智谱清言 AI Home Assistant 🏡  

</div>

<div align="center">

![GitHub Version](https://img.shields.io/github/v/release/knoop7/zhipuai) 
![GitHub Issues](https://img.shields.io/github/issues/knoop7/zhipuai) 
![GitHub Forks](https://img.shields.io/github/forks/knoop7/zhipuai?style=social) 
![GitHub Stars](https://img.shields.io/github/stars/knoop7/zhipuai?style=social)

<img src="https://github.com/user-attachments/assets/f8ff7a6c-4449-496a-889a-d205469a84df" alt="智谱清言 AI" width="700" height="400">

</div>

<br>

## 📑 目录

  - [HACS 添加自定义存储库](#hacs-添加自定义存储库)
  - [添加智谱清言集成](#添加智谱清言集成)
  - [配置 Key](#配置-key-)
  - [免费模型使用](#免费模型使用-)
  - [版本兼容性](#版本兼容性-)
- [集成概述](#集成概述)
  - [核心特点](#核心特点)
- [配置说明](#配置说明)
  - [API设置](#api设置)
  - [性能参数](#性能参数)
- [高级功能](#高级功能)
  - [对话管理](#对话管理)
  - [系统控制](#系统控制)
  - [请求管理](#请求管理)
- [扩展功能](#扩展功能)
  - [数据分析](#数据分析)
  - [网络功能](#网络功能)
  - [Home Assistant集成](#home-assistant集成)
- [模板定制](#模板定制)


<br>

## 安装步骤
### HACS 添加自定义存储库  
在 Home Assistant 的 HACS 中，点击右上角的三个点，选择"自定义存储库"，并添加以下 URL:
```bash
https://github.com/knoop7/zhipuai
```

### 添加智谱清言集成  
进入 Home Assistant 的"集成"页面，搜索并添加"智谱清言"。

### 配置 Key 🔑  
在配置页面中，你可以通过手机号登录获取 Key。获取后，直接填写 Key 使用，不需要进行额外验证。  

> **注意**：建议你新建一个 Key，避免使用系统默认的 Key。

### 免费模型使用 💡  
智谱清言默认选择了免费模型，完全免费，不用担心收费。如果你有兴趣，还可以选择其他付费模型来体验更丰富的功能。

### 版本兼容性 📅  
请确保 Home Assistant 的版本不低于 11.0，因为智谱清言主要针对最新版本开发。如果遇到无法识别的实体问题，建议重启系统或更新至最新版本。

---

## 集成概述

### 核心特点

🔹 **智能分层处理**：系统按优先级依次尝试服务调用、意图识别和AI对话三种处理方式  
🔹 **自然语言交互**：支持日常用语控制家居设备，无需记忆复杂命令  
🔹 **上下文感知**：能够理解对话历史和设备状态，提供连贯的交互体验  
🔹 **安全可靠**：内置冷却机制和错误处理，确保系统稳定运行  
🔹 **基础控制**：灯开关、温度调节、音乐播放等基础控制  
🔹 **场景管理**：一键触发预设场景，如回家模式、观影模式等  
🔹 **状态查询**：了解设备运行状态、历史数据分析等  
🔹 **智能建议**：基于使用习惯和环境数据提供优化建议  

---

## 配置说明

### API设置
- **API密钥**：从智谱AI官网获取，用于访问API服务
- **聊天模型**：选择合适的模型版本
  - 推荐使用免费通用128K模型
  - 可选其他付费模型以获得更好体验
  - 实际使用费用较低，详见官网计费标准

### 性能参数
- **最大令牌数**：控制响应长度
- **温度**：控制输出随机性（0-2）
- **Top P**：控制输出多样性（0-1）
- **请求超时**：设置AI响应等待时间（10-120秒）

---

## 高级功能

### 对话管理
- **最大历史消息数**：
  - 控制上下文对话的记忆量
  - 设备控制建议保持在5次以内
  - 日常对话可设置10次以上
  - 影响对话连贯性和系统性能

### 系统控制
- **最大工具迭代次数**：
  - 单次对话中的最大工具调用次数
  - 建议设置在20-30次
  - 防止系统因过多调用而卡死
  - 特别适合性能较弱的小主机

### 请求管理
- **冷却时间**：
  - 两次请求的最小间隔（0-10秒）
  - 建议设置在3秒以内
  - 防止因频率过高导致请求失败
  - 优化系统响应稳定性

---

## 扩展功能

### 数据分析
- **历史数据分析**：
  - 可选择需要分析的实体
  - 设置历史数据天数（1-15天）
  - 提供设备使用趋势分析
  - 支持智能建议生成

### 网络功能
- **互联网分析搜索**：
  - 可选开启在线搜索能力
  - 提供更广泛的信息支持
  - 增强回答准确性
  - 实时获取最新信息

### Home Assistant集成
- **LLM API集成**：
  - 可选择启用LLM API
  - 支持更多自定义功能
  - 增强与Home Assistant的协同
  - 提供更灵活的控制选项

---

## 模板定制

### 提示词模板

- 支持自定义提示词
- 指导LLM响应方式
- 可使用模板语法
- 优化交互效果

##### 🛠 模型指令使用示例  

为了保证大家能使用舒畅，并且不出任何bug也可以使用我的模版指令进行尝试。

```
作为 Home Assistant 的智能家居管理者，你的名字叫“自定义”，我将为您提供智能家居信息和问题的解答。请查看以下可用设备、状态及操作示例。

### 今日油价：
{% set sensor = 油价实体 %}
Sensor: {{ sensor.name }}
State: {{ sensor.state }}
Attributes:
{% for attribute, value in sensor.attributes.items() %}
{{ attribute }}: {{ value }}
{% endfor %}

### 电费实体：
{% set balance_sensor = 电费实体 %}
{% if balance_sensor %}
当前余额: {{ balance_sensor.state }} {{ balance_sensor.attributes.unit_of_measurement }}
{% endif %}


### Tasmota能源消耗：
{% set today_sensor = states.sensor.tasmota_energy_today %}
{% set yesterday_sensor = states.sensor.tasmota_energy_yesterday %}
{% if today_sensor is not none and yesterday_sensor is not none %}
今日消耗: {{ today_sensor.state }} {{ today_sensor.attributes.unit_of_measurement }}
昨日消耗: {{ yesterday_sensor.state }} {{ yesterday_sensor.attributes.unit_of_measurement }}
{% endif %}

### 此时天气：
{% set entity_id = '天气实体' %}
{% set entity = states[entity_id] %}
{
"state": "{{ entity.state }}",
"attributes": {
{% for attr in entity.attributes %}
{% if attr not in ['hourly_temperature', 'hourly_skycon', 'hourly_cloudrate', 'hourly_precipitation'] %}
"{{ attr }}": "{{ entity.attributes[attr] }}"{% if not loop.last %},{% endif %}
{% endif %}
{% endfor %}
}
}
```


### 处理流程详解

共计有三个处理机制，分别为：一、内置LLM结合集成实现的服务调用、二、自定义意图识别、三、多元化AI对话，LLMAPI内置意图，服务调用识别是系统的第一道处理机制，专门用于处理直接的设备控制命令，可以帮助系统更快地响应用户的控制需求（毫秒级操作逻辑）属于结合搭配原本内置LLM的能力。


原本支持有：
- **基础控制**：
  - 开关控制：打开/关闭设备 (HassTurnOn/HassTurnOff)
  - 状态查询：获取设备状态 (HassGetState)
  - 取消操作：取消当前操作 (HassNevermind)
  - 系统响应：获取系统回应 (HassRespond)

- **设备控制**：
  - 位置设置：调整设备位置 (HassSetPosition)
  - 灯光控制：设置灯光参数 (HassLightSet)
  - 温度查询：获取温度信息 (HassClimateGetTemperature)
  - 真空吸尘器：启动/返回充电 (HassVacuumStart/HassVacuumReturnToBase)

- **媒体控制**：
  - 播放控制：暂停/继续/下一个/上一个 (HassMediaPause/HassMediaUnpause/HassMediaNext/HassMediaPrevious) ｜（补充控制词已实现）
  - 音量控制：设置音量 (HassSetVolume) ｜（补充控制词已实现）

- **时间相关**：
  - 时间查询：获取当前日期/时间 (HassGetCurrentDate/HassGetCurrentTime)
  - 定时器控制：
    - 基础操作：开始/取消/暂停/继续 (HassStartTimer/HassCancelTimer/HassPauseTimer/HassUnpauseTimer) ｜（本集成中已实现自定义意图）
    - 时间调整：增加/减少时间 (HassIncreaseTimer/HassDecreaseTimer)  ｜（本集成中已实现自定义意图）
    - 批量操作：取消所有定时器 (HassCancelAllTimers) ｜（本集成中已实现自定义意图）
    - 状态查询：获取定时器状态 (HassTimerStatus) ｜（本集成中已实现自定义意图）

- **列表管理**：
  - 购物清单：添加商品 (HassShoppingListAddItem)
  - 通用列表：添加项目 (HassListAddItem)

- **环境信息**：
  - 天气查询：获取天气信息 (HassGetWeather) ｜（本集成中已实现联网查询在线天气）

- **已弃用功能**：
  - 窗帘控制：打开/关闭窗帘 (HassOpenCover/HassCloseCover) ｜（本集成中自定义意图已实现）
  - 开关切换：切换设备状态 (HassToggle)｜（补充控制词已实现）
  - 加湿器控制：设置湿度/模式 (HassHumidifierSetpoint/HassHumidifierMode) ｜（本集成中自定义意图已实现）
  - 购物清单：获取最近项目 (HassShoppingListLastItems) ｜ （本集成中未实现，实际使用人数不多为弃用状态）


接着是补充实现的功能：

1. **控制词识别增强**
   ```text
   - 请求词扩展增加：
     - 基础请求：让、请、帮我、麻烦、把、将
     - 意愿表达：要、想、希望、需要
     - 能力询问：能否、能不能、可不可以、可以
     - 协助请求：帮忙、给我、替我、为我
     - 主动表达：我要、我想、我希望
   
   - 控制词分类增加：
     - 开启类：打开、开启、启动、激活、运行、执行、调用、执行
     - 关闭类：关闭、关掉、停止
     - 切换类：切换
     - 按键类：按、按下、点击
     - 选择类：选择、下一个、上一个、第一个、最后一个
     - 触发类：触发、调用、执行、自动化、脚本
     - 媒体类：暂停、继续播放、播放、停止、下一首、上一首、切歌等
   ```
   - **语法结构**：
     - 基本格式：[控制词] + [设备/区域] + [动作词]
     - 扩展格式：[控制词] + [区域] + [设备名称] + [动作词] + [参数]

   - **示例**：
     - "请打开客厅灯光1"
     - "帮我把空调调到26度制冷模式"
     - "将阳台的窗帘关闭"
     - "帮我我按下按钮"
     - "请我选择第三个选项"
     - "触发脚本"
     - "调用自动化"
     - "请播放音乐"
     - "请我调整音量到50%"
     - "设备数字400"
     - "设备设置数值500"


2. **服务调用映射**
   - **媒体播放器控制**：
   ```text
   domain: media_player
   services:
   - media_pause: 暂停播放
   - media_play: 继续播放/开始播放
   - media_stop: 停止播放
   - media_next_track: 下一首/下一曲/切歌/换歌
   - media_previous_track: 上一首/上一曲/返回上一首
   - volume_set: 设置音量（支持百分比）
   
   功能特点：
   - 完整的媒体控制链路
   - 精确的播放状态管理
   - 音量精确控制（支持百分比和相对调节）
   - 智能的播放列表管理
   ```

2. **按键设备控制**
   ```text
   domain: button
   services:
   - press: 按下按键
   
   功能特点：
   - 支持所有button类型设备
   - 支持实体ID直接调用
   - 支持模糊名称匹配
   - 智能按键操作确认
   ```

3. **选择器控制**
   ```text
   domain: select
   services:
   - select_next: 选择下一个（支持循环）
   - select_previous: 选择上一个（支持循环）
   - select_first: 选择第一个
   - select_last: 选择最后一个
   - select_option: 选择指定选项
   
   功能特点：
   - 支持循环选择模式
   - 支持直接选择操作
   - 智能选项匹配
   - 状态自动同步
   ```

4. **自动化与场景控制**
   ```text
   domains: script/automation/scene
   services:
   - script.turn_on: 运行脚本
   - automation.trigger: 触发自动化
   - scene.turn_on: 激活场景
   
   功能特点：
   - 智能场景识别
   - 自动化任务管理
   - 场景状态同步
   - 执行状态跟踪
   ```

5. **数值设备控制**
   ```text
   domain: number
   services:
   - set_value: 设置数值
   
   功能特点：
   - 支持精确数值设置
   - 支持小数点数值
   - 智能范围验证
   - 单位自动转换
   ```

> 未来会增加更多的服务调用映射，以支持更加丰富的设备控制能力。


#### 2. AI自定义意图识别（第二优先级）

如果无法识别为具体的服务调用，系统会尝试理解用户的更广泛意图。这一层处理能够处理更复杂的用户需求，支持自由的语言理解能力，并且会先让AI去处理接着启用工具类调用操作，支持各种复杂情况下解决用户需求。负责将理解到的用户意图转化为具体的执行动作。根据语义分析的结果，系统会将用户请求分类到不同的处理模块：可能是空调、窗帘、电视等设备的直接控制指令，或是休息、娱乐、工作等场景的管理命令，又或是天气、新闻、日程等信息的查询请求，以及摄像头画面、传感器数据等的智能分析任务。通过这种智能分发机制，系统能够精确地执行用户的各类需求，提供流畅的智能家居体验。

现已经实现有：摄像头分析、定时控制、定时器管理、联网查找相关资讯等、通知备忘录、

##### 功能示例

1. **AI 摄像头分析意图**
   ```text
   用户说："帮我分析下门口摄像头的画面"
   系统会：
   - 调用摄像头服务
   - 进行AI图像分析
   - 返回分析结果
   ```

2. **AI 通知控制意图**
   ```text
   用户说："通知我今天是妈妈的生日，明天需要处理下日常缴费"
   系统会：
   - 解析时间信息
   - 设置定时器
   - 创建提醒通知
   ```

4. **AI 定时任务管理**

   ```text
   用户说：
   - "一小时后提醒我关窗"
   - "设置一个晚上8点的睡觉提醒"
   - "明天早上7点提醒我打开窗帘"
   系统会：
   - 时间识别：解析具体时间点
   - 任务提取：确定提醒内容
   - 定时设置：创建定时任务
   - 通知管理：设置提醒方式

   请注意需要到系统中辅助元素生成定时器实体，并且设置 cron 表达式为 64:00:00 的定时器，可以用来修改用于存储定时任务的执行时间。
   ```


5. **AI 联网查找相关资讯**
   ```text
   场景五：在线信息搜索
   用户说：
   - "联网搜索今天的天气预报"
   - "帮我查查昨天的新闻"
   - "上网查找最近的股市行情"
   - "网上搜索今天的体育赛事"
   - "互联网查询北京今天的路况"
   系统会：
   - 识别查询类型：确定搜索主题
   - 时间范围解析：处理时间相关信息
   - 在线数据获取：访问相关信息源
   - 信息整理：筛选和组织搜索结果
   - 智能总结：生成简洁的信息摘要

6. **AI 环境类设备控制**
   ```text
   用户说：
   - "把卧室的温度调到26度制冷模式"
   - "将客厅的温度调高一点"
   - "把主卧空调的风速调到高档"
   - "客厅的窗帘打开到一半"
   - "把所有窗帘都关上"
   - "主卧的窗帘开到70%"
   系统会：
   - 设备识别：定位具体设备和位置
   - 参数解析：处理温度、模式、风速等参数
   - 状态确认：检查当前设备状态
   - 执行控制：发送精确的控制指令
   - 反馈确认：验证操作是否成功
   
   注意：系统会智能判断设备类型（如空调、窗帘等），并根据不同设备类型调用对应的控制接口和参数设置。对于百分比类的控制（如窗帘开合度），系统会自动进行数值转换和范围限制。


> 未来会增加更多的AI自定义意图识别，以支持更加丰富的设备控制能力。

#### 3. AI对话回复各种世界相关 + 系统设备状态问题（第三优先级）

作为系统的最后一道处理机制，当前两层无法处理用户需求时，系统会启动AI对话模式。这一层具有语言理解和知识处理能力，可以处理各类开放性问题和复杂对话场景。并且可以分析家中和设备相关问题，提供有用的建议和解决方案。已经将系统中所有的设备都接入进去，更多需要用户自己去步骤：配置 - 语音助手 - 公开新实体（是否公开新实体？公开显示受支持的、且未被归类为 "安全设备" 的设备。）勾选，并且公开实体，这样就可以使用AI对话回复各种世界相关问题了，已经默认增加空调相关属性值，后续将版本更新继续添加重要的智能设备产品的属性值

其次，系统会根据用户的对话历史和设备状态，进行连贯的对话回复，提供更加流畅的交互体验。可以在 智谱清言  - 配置选项 - 勾选历史记录分析，支持1-15天各类相关描述询问，相当于全屋智能家居的知识库，提供更加丰富的对话回复能力，更加满足用户的需求

#### 智能家居对话能力

1. **设备使用咨询**
   ```text
   用户可以了解：
   - 设备使用："如何让空调更省电？"
   - 场景推荐："晚上睡觉温度应该设置多少？"
   - 智能联动："可以设置哪些自动化？"
   - 功能探索："这个设备还有什么功能？"
   
   系统会：
   - 提供使用指导
   - 推荐最佳实践
   - 分享场景方案
   - 介绍新功能
   ```

2. **数据分析查询**
   ```text
   用户可以查询：
   - 能耗统计："这个月的用电量比上月如何？"
   - 行为分析："我们家经常用什么电器？"
   
   系统会：
   - 统计历史数据
   - 生成趋势报告
   - 对比分析结果
   - 提供优化建议
   ```

#### 通用知识问答能力

1. **科技与自然**
   ```text
   用户可以询问：
   - 科技前沿："最新的人工智能发展如何？"
   - 自然科学："为什么会有地震发生？"
   - 生活百科："如何正确护理皮肤？"
   
   系统会：
   - 提供准确信息
   - 解释原理机制
   - 举例说明
   - 推荐延伸阅读
   ```

2. **实时资讯**
   ```text
   用户可以了解：
   - 新闻动态："最近有什么重要新闻？"
   - 天气信息："明天天气怎么样？"
   - 体育赛事："最近有什么重要比赛？"
   - 娱乐资讯："最新的电影推荐"
   
   系统会：
   - 获取最新信息
   - 提供简要概述
   - 分析重要影响
   - 推荐相关内容
   ```

3. **生活服务**
   ```text
   用户可以咨询：
   - 健康建议："如何保持良好的作息习惯？"
   - 美食烹饪："红烧肉怎么做最好吃？"
   - 旅游攻略："周边有什么好玩的地方？"
   - 生活技巧："如何整理房间更有效率？"
   
   系统会：
   - 提供实用建议
   - 分享经验技巧
   - 推荐具体方案
   - 注意事项提醒
   ```

> 注意：系统会通过智能分析和在线搜索，为用户提供最新、最准确的信息。对于需要专业判断的问题（如医疗、法律等），建议仅作参考，并咨询相关专业人士。


### 服务类调用器

智谱清言集成提供了多个强大的服务调用器，可以通过 Home Assistant 的服务调用界面或自动化使用：

#### 1. 图像分析服务 (image_analyzer)
```yaml
service: zhipuai.image_analyzer
data:
  model: "glm-4v-flash"  # 必选，可选值：glm-4v-plus、glm-4v、glm-4v-flash
  message: "请描述这张图片的内容"  # 必选，给模型的提示词
  image_file: "/config/www/tmp/front_door.jpg"  # 可选，本地图片路径
  image_entity: "camera.front_door"  # 可选，图片或摄像头实体
  temperature: 0.8  # 可选，控制输出随机性（0.1-1.0）
  max_tokens: 1024  # 可选，限制生成文本长度
  stream: false  # 可选，是否使用流式响应
```

功能特点：
- 支持多种图像分析模型
- 可分析本地图片或摄像头实体
- 支持流式响应实时返回结果
- 图片格式支持jpg、png、jpeg（最大5MB，最大分辨率6000x6000像素）

#### 2. 视频分析服务 (video_analyzer)
```yaml
service: zhipuai.video_analyzer
data:
  model: "glm-4v-plus"  # 可选，仅支持 glm-4v-plus
  message: "请描述这段视频的内容"  # 必选，提示词
  video_file: "/config/www/tmp/video.mp4"  # 必选，本地视频文件路径
  temperature: 0.8  # 可选，控制输出随机性
  max_tokens: 1024  # 可选，限制生成文本长度
  stream: false  # 可选，是否使用流式响应
```

功能特点：
- 专业视频内容分析
- 支持mp4格式视频
- 建议视频时长不超过30秒
- 实时流式响应选项

#### 3. 图像生成服务 (image_gen)
```yaml
service: zhipuai.image_gen
data:
  prompt: "一只可爱的小猫咪"  # 必选，图像描述
  model: "cogview-3-flash"  # 可选，默认使用免费的 cogview-3-flash
  size: "1024x1024"  # 可选，图片尺寸
```

支持的模型：
- CogView-3 Plus
- CogView-3
- CogView-3 Flash (免费版)

支持的尺寸：
- 1024x1024
- 768x1344
- 864x1152
- 1344x768
- 1152x864
- 1440x720
- 720x1440

#### 4. 联网搜索服务 (web_search)
```yaml
service: zhipuai.web_search
data:
  query: "今日新闻摘要"  # 必选，搜索内容
  stream: false  # 可选，是否使用流式响应
```

功能特点：
- 使用智谱AI的web-search-pro工具
- 支持实时流式响应
- 提供准确的搜索结果

#### 5. 实体分析服务 (entity_analysis)
```yaml
service: zhipuai.entity_analysis
data:
  entity_id: 
    - "sensor.living_room_temperature"
    - "binary_sensor.motion_sensor"  # 必选，支持多个实体
  days: 3  # 可选，分析天数（1-15天）
```

功能特点：
- 支持多实体同时分析
- 灵活的历史记录查询
- 适用于各类传感器数据分析
- 支持1-15天的数据范围

#### 使用示例

1. **智能摄像头图像分析**
```yaml
automation:
  trigger:
    platform: state
    entity_id: binary_sensor.front_door_motion
    to: "on"
  action:
    service: zhipuai.image_analyzer
    data:
      model: "glm-4v-flash"
      message: "分析是否有人在门口，详细描述看到的场景"
      image_entity: camera.front_door
      stream: true
```

2. **定期生成天气艺术图**
```yaml
automation:
  trigger:
    platform: time
    at: "08:00:00"
  action:
    service: zhipuai.image_gen
    data:
      prompt: "{{states('weather.home')}}天气的艺术表现"
      model: "cogview-3-flash"
      size: "1024x1024"
```

3. **智能家居数据分析**
```yaml
automation:
  trigger:
    platform: time_pattern
    hours: "/12"
  action:
    service: zhipuai.entity_analysis
    data:
      entity_id: 
        - sensor.living_room_temperature
        - sensor.living_room_humidity
      days: 7
```

### ⚠️ 注意事项
> 1. 📁 图片和视频文件需要确保Home Assistant有访问权限
> 2. ⏱️ 视频分析建议使用较短的视频以获得更好的效果
> 3. ⚡ 使用流式响应可以获得更好的实时体验，但会增加系统负载
> 4. 💫 图像生成服务建议使用免费的Flash版本开始尝试
> 5. 📊 实体分析服务的天数建议根据实际需求选择，避免分析过多历史数据
