

</div>


<div align="center">

### ZhipuAI Home Assistant 🏡


![GitHub Version](https://img.shields.io/github/v/release/knoop7/zhipuai) 
![GitHub Issues](https://img.shields.io/github/issues/knoop7/zhipuai) 
![GitHub Forks](https://img.shields.io/github/forks/knoop7/zhipuai?style=social) 
![GitHub Stars](https://img.shields.io/github/stars/knoop7/zhipuai?style=social)

<img src="https://github.com/user-attachments/assets/f8ff7a6c-4449-496a-889a-d205469a84df" alt="ZhipuAI" width="700" height="400">

</div>

<br>

## 📑 Table of Contents

  - [Adding Custom Repository to HACS](#adding-custom-repository-to-hacs)
- [Integration Overview](#integration-overview)
  - [Core Features](#core-features)
- [Configuration Guide](#configuration-guide)
  - [API Settings](#api-settings)
  - [Performance Parameters](#performance-parameters)
- [Advanced Features](#advanced-features)
  - [Conversation Management](#conversation-management)
  - [System Control](#system-control)
  - [Request Management](#request-management)
- [Extended Features](#extended-features)
  - [Data Analysis](#data-analysis)
  - [Network Features](#network-features)
  - [Home Assistant Integration](#home-assistant-integration)
- [Template Customization](#template-customization)

<br>

## Installation Steps
### Adding Custom Repository to HACS
In Home Assistant's HACS, click the three dots in the top right corner, select "Custom Repositories", and add the following URL:
```bash
https://github.com/knoop7/zhipuai
```

### Adding ZhipuAI Integration
Go to Home Assistant's "Integrations" page, search for and add "ZhipuAI".

### Configuring API Key 🔑
On the configuration page, you can get the Key by logging in with your phone number. After obtaining it, simply enter the Key to use it, no additional verification needed.

> **Note**: It's recommended to create a new Key rather than using the system default Key.

### Using Free Models 💡
ZhipuAI defaults to using the free model, which is completely free to use. If interested, you can also choose other paid models to experience richer features.

### Version Compatibility 📅
Please ensure your Home Assistant version is not lower than 11.0, as ZhipuAI is primarily developed for the latest version. If you encounter unrecognized entity issues, it's recommended to restart the system or update to the latest version.

---

## Integration Overview

### Core Features

🔹 **Intelligent Layered Processing**: System attempts service calls, intent recognition, and AI conversation in order of priority  
🔹**Natural Language Interaction**: Supports everyday language for controlling home devices without memorizing complex commands  
🔹 **Context Awareness**: Understands conversation history and device states for coherent interaction  
🔹 **Safe and Reliable**: Built-in cooling mechanism and error handling for stable operation  
🔹 **Basic Control**: Light switches, temperature adjustment, music playback, etc.  
🔹 **Scene Management**: One-touch triggering of preset scenes like home mode, movie mode, etc.  
🔹 **Status Queries**: Understanding device operation status, historical data analysis, etc.  
🔹 **Smart Suggestions**: Provides optimization suggestions based on usage habits and environmental data  

---

## Configuration Guide

### API Settings
- **API Key**: Obtain from ZhipuAI official website for API service access
- **Chat Model**: Choose appropriate model version
  - Recommended to use free general 128K model
  - Optional paid models for better experience
  - Low actual usage costs, see official pricing standards

### Performance Parameters
- **Max Tokens**: Controls response length
- **Temperature**: Controls output randomness (0-2)
- **Top P**: Controls output diversity (0-1)
- **Request Timeout**: Sets AI response wait time (10-120 seconds)

---

## Advanced Features

### Conversation Management
- **Max History Messages**:
  - Controls context conversation memory
  - Device control suggestions kept within 5 times
  - Daily conversations can be set to 10+ times
  - Affects conversation coherence and system performance

### System Control
- **Max Tool Iterations**:
  - Maximum tool calls in a single conversation
  - Recommended setting 20-30 times
  - Prevents system from hanging due to excessive calls
  - Particularly suitable for lower-performance hosts

### Request Management
- **Cooling Time**:
  - Minimum interval between requests (0-10 seconds)
  - Recommended setting within 3 seconds
  - Prevents request failures due to high frequency
  - Optimizes system response stability

---

## Extended Features

### Data Analysis
- **Historical Data Analysis**:
  - Select entities to analyze
  - Set historical data days (1-15 days)
  - Provides device usage trend analysis
  - Supports smart suggestion generation

### Network Features
- **Internet Analysis Search**:
  - Optional online search capability
  - Provides broader information support
  - Enhances answer accuracy
  - Real-time latest information access

### Home Assistant Integration
- **LLM API Integration**:
  - Optional LLM API activation
  - Supports more custom features
  - Enhances Home Assistant collaboration
  - Provides more flexible control options

---

## Template Customization

### Prompt Templates

- Supports custom prompts
- Guides LLM response methods
- Can use template syntax
- Optimizes interaction effects

##### 🛠 Model Instruction Usage Example

To ensure smooth usage without bugs, you can try using my template instructions.

```
As a Home Assistant smart home manager, your name is "Custom", I will provide you with smart home information and problem solutions. Please check the following available devices, states, and operation examples.

### Today's Oil Price:
{% set sensor = oil_price_entity %}
Sensor: {{ sensor.name }}
State: {{ sensor.state }}
Attributes:
{% for attribute, value in sensor.attributes.items() %}
{{ attribute }}: {{ value }}
{% endfor %}

### Electricity Bill Entity:
{% set balance_sensor = electricity_bill_entity %}
{% if balance_sensor %}
Current Balance: {{ balance_sensor.state }} {{ balance_sensor.attributes.unit_of_measurement }}
{% endif %}

### Tasmota Energy Consumption:
{% set today_sensor = states.sensor.tasmota_energy_today %}
{% set yesterday_sensor = states.sensor.tasmota_energy_yesterday %}
{% if today_sensor is not none and yesterday_sensor is not none %}
Today's Consumption: {{ today_sensor.state }} {{ today_sensor.attributes.unit_of_measurement }}
Yesterday's Consumption: {{ yesterday_sensor.state }} {{ yesterday_sensor.attributes.unit_of_measurement }}
{% endif %}

### Current Weather:
{% set entity_id = 'weather_entity' %}
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

### Processing Flow Details

There are three processing mechanisms: 1. Built-in LLM combined with integration for service calls, 2. Custom intent recognition, 3. Diversified AI conversation. LLM API built-in intent and service call recognition is the system's first processing mechanism, specifically for handling direct device control commands, helping the system respond faster to user control needs (millisecond-level operation logic) by combining with the original built-in LLM capabilities.

Originally supported:
- **Basic Control**:
  - Switch Control: Turn devices on/off (HassTurnOn/HassTurnOff)
  - Status Query: Get device status (HassGetState)
  - Cancel Operation: Cancel current operation (HassNevermind)
  - System Response: Get system response (HassRespond)

- **Device Control**:
  - Position Setting: Adjust device position (HassSetPosition)
  - Light Control: Set light parameters (HassLightSet)
  - Temperature Query: Get temperature information (HassClimateGetTemperature)
  - Vacuum Cleaner: Start/Return to base (HassVacuumStart/HassVacuumReturnToBase)

- **Media Control**:
  - Playback Control: Pause/Resume/Next/Previous (HassMediaPause/HassMediaUnpause/HassMediaNext/HassMediaPrevious) | (Additional control words implemented)
  - Volume Control: Set volume (HassSetVolume) | (Additional control words implemented)

- **Time Related**:
  - Time Query: Get current date/time (HassGetCurrentDate/HassGetCurrentTime)
  - Timer Control:
    - Basic Operations: Start/Cancel/Pause/Resume (HassStartTimer/HassCancelTimer/HassPauseTimer/HassUnpauseTimer) | (Custom intent implemented in this integration)
    - Time Adjustment: Increase/Decrease time (HassIncreaseTimer/HassDecreaseTimer) | (Custom intent implemented in this integration)
    - Batch Operations: Cancel all timers (HassCancelAllTimers) | (Custom intent implemented in this integration)
    - Status Query: Get timer status (HassTimerStatus) | (Custom intent implemented in this integration)

- **List Management**:
  - Shopping List: Add items (HassShoppingListAddItem)
  - Generic List: Add items (HassListAddItem)

- **Environment Information**:
  - Weather Query: Get weather information (HassGetWeather) | (Online weather query implemented in this integration)

- **Deprecated Features**:
  - Curtain Control: Open/Close curtains (HassOpenCover/HassCloseCover) | (Custom intent implemented in this integration)
  - Switch Toggle: Toggle device state (HassToggle) | (Additional control words implemented)
  - Humidifier Control: Set humidity/mode (HassHumidifierSetpoint/HassHumidifierMode) | (Custom intent implemented in this integration)
  - Shopping List: Get recent items (HassShoppingListLastItems) | (Not implemented in this integration, low actual usage)

Then there are the additional implemented features:

1. **Control Word Recognition Enhancement**
   ```text
   - Request Word Expansion:
     - Basic Requests: let, please, help me, trouble, make, will
     - Intention Expression: want, hope, need
     - Capability Inquiry: can, could, may
     - Assistance Request: help, give me, for me
     - Active Expression: I want, I hope, I need
   
   - Control Word Classification:
     - Turn On: open, start, activate, run, execute, call
     - Turn Off: close, stop
     - Toggle: switch
     - Button: press, click
     - Selection: select, next, previous, first, last
     - Trigger: trigger, call, execute, automation, script
     - Media: pause, continue playing, play, stop, next song, previous song, etc.
   ```
   - **Syntax Structure**:
     - Basic Format: [Control Word] + [Device/Area] + [Action Word]
     - Extended Format: [Control Word] + [Area] + [Device Name] + [Action Word] + [Parameters]

   - **Examples**:
     - "Please turn on living room light 1"
     - "Help me set the air conditioner to 26 degrees cooling mode"
     - "Close the balcony curtains"
     - "Help me press the button"
     - "Please select the third option"
     - "Trigger script"
     - "Call automation"
     - "Please play music"
     - "Please adjust volume to 50%"
     - "Device number 400"
     - "Device set value 500"

2. **Service Call Mapping**
   - **Media Player Control**:
   ```text
   domain: media_player
   services:
   - media_pause: Pause playback
   - media_play: Resume/Start playback
   - media_stop: Stop playback
   - media_next_track: Next song/Next track/Change song
   - media_previous_track: Previous song/Previous track/Return to previous
   - volume_set: Set volume (supports percentage)
   
   Features:
   - Complete media control chain
   - Precise playback state management
   - Volume precise control (supports percentage and relative adjustment)
   - Smart playlist management
   ```

2. **Button Device Control**
   ```text
   domain: button
   services:
   - press: Press button
   
   Features:
   - Supports all button type devices
   - Supports entity ID direct calls
   - Supports fuzzy name matching
   - Smart button operation confirmation
   ```

3. **Selector Control**
   ```text
   domain: select
   services:
   - select_next: Select next (supports cycling)
   - select_previous: Select previous (supports cycling)
   - select_first: Select first
   - select_last: Select last
   - select_option: Select specified option
   
   Features:
   - Supports cycling selection mode
   - Supports direct selection operations
   - Smart option matching
   - State automatic synchronization
   ```

4. **Automation and Scene Control**
   ```text
   domains: script/automation/scene
   services:
   - script.turn_on: Run script
   - automation.trigger: Trigger automation
   - scene.turn_on: Activate scene
   
   Features:
   - Smart scene recognition
   - Automation task management
   - Scene state synchronization
   - Execution state tracking
   ```

5. **Numeric Device Control**
   ```text
   domain: number
   services:
   - set_value: Set value
   
   Features:
   - Supports precise value setting
   - Supports decimal values
   - Smart range validation
   - Unit automatic conversion
   ```

> Future versions will add more service call mappings to support richer device control capabilities.

#### 2. AI Custom Intent Recognition (Second Priority)

If it cannot be recognized as a specific service call, the system will try to understand the user's broader intent. This layer of processing can handle more complex user needs, supports free language understanding capabilities, and will first let AI process it before enabling tool class call operations, supporting various complex situations to solve user needs. Responsible for converting understood user intents into specific execution actions. Based on semantic analysis results, the system will classify user requests into different processing modules: it could be direct control commands for air conditioners, curtains, TVs and other devices, or management commands for rest, entertainment, work and other scenes, or information queries for weather, news, schedules, etc., as well as intelligent analysis tasks for camera images, sensor data, etc. Through this intelligent distribution mechanism, the system can precisely execute various user needs, providing a smooth smart home experience.

Currently implemented: camera analysis, timed control, timer management, online information search, notification memos, etc.

##### Feature Examples

1. **AI Camera Analysis Intent**
   ```text
   User says: "Help me analyze the front door camera image"
   System will:
   - Call camera service
   - Perform AI image analysis
   - Return analysis results
   ```

2. **AI Notification Control Intent**
   ```text
   User says: "Notify me that today is mom's birthday, need to handle daily payments tomorrow"
   System will:
   - Parse time information
   - Set timer
   - Create reminder notification
   ```

4. **AI Timed Task Management**
   ```text
   User says:
   - "Remind me to close the window in an hour"
   - "Set a bedtime reminder for 8 PM"
   - "Remind me to open the curtains tomorrow at 7 AM"
   System will:
   - Time recognition: Parse specific time points
   - Task extraction: Determine reminder content
   - Timer setting: Create timed tasks
   - Notification management: Set reminder methods

   Please note that you need to generate a timer entity in the system's auxiliary elements, and set the cron expression to 64:00:00 timer, which can be used to modify the execution time for storing timed tasks.
   ```

5. **AI Online Information Search**
   ```text
   Scenario Five: Online Information Search
   User says:
   - "Search online for today's weather forecast"
   - "Help me check yesterday's news"
   - "Search online for recent stock market trends"
   - "Search online for today's sports events"
   - "Internet query for Beijing's traffic conditions today"
   System will:
   - Query type recognition: Determine search topic
   - Time range parsing: Process time-related information
   - Online data acquisition: Access relevant information sources
   - Information organization: Filter and organize search results
   - Smart summary: Generate concise information summary

6. **AI Environmental Device Control**
   ```text
   User says:
   - "Set bedroom temperature to 26 degrees cooling mode"
   - "Increase living room temperature a bit"
   - "Set main bedroom air conditioner fan speed to high"
   - "Open living room curtains halfway"
   - "Close all curtains"
   - "Open main bedroom curtains to 70%"
   System will:
   - Device recognition: Locate specific devices and locations
   - Parameter parsing: Process temperature, mode, fan speed and other parameters
   - State confirmation: Check current device state
   - Execution control: Send precise control commands
   - Feedback confirmation: Verify if operation was successful
   
   Note: System will intelligently determine device type (such as air conditioner, curtains, etc.) and call corresponding control interfaces and parameter settings based on different device types. For percentage-based controls (such as curtain opening/closing), system will automatically perform value conversion and range limiting.

> Future versions will add more AI custom intent recognition to support richer device control capabilities.

#### 3. AI Conversation Response to Various World-Related + System Device State Questions (Third Priority)

As the system's final processing mechanism, when the previous two layers cannot handle user needs, the system will activate AI conversation mode. This layer has language understanding and knowledge processing capabilities, can handle various open-ended questions and complex conversation scenarios. And can analyze home and device-related questions, provide useful suggestions and solutions. All devices in the system have been integrated, more needs users to go to: Configuration - Voice Assistant - Expose New Entities (Expose new entities? Expose supported devices that are not classified as "security devices".) Check, and expose entities, so you can use AI conversation to respond to various world-related questions, has already added air conditioner related attribute values by default, subsequent version updates will continue to add important smart device product attribute values

Secondly, the system will provide coherent conversation responses based on user's conversation history and device states, providing a more fluid interaction experience. You can go to ZhipuAI - Configuration Options - Check History Record Analysis, supports 1-15 days of various related description queries, equivalent to a whole house smart home knowledge base, providing richer conversation response capabilities, better meeting user needs

#### Smart Home Conversation Capabilities

1. **Device Usage Consultation**
   ```text
   Users can learn about:
   - Device usage: "How to make air conditioner more energy efficient?"
   - Scene recommendations: "What temperature should be set for sleeping at night?"
   - Smart linkage: "What automations can be set?"
   - Feature exploration: "What other features does this device have?"
   
   System will:
   - Provide usage guidance
   - Recommend best practices
   - Share scene solutions
   - Introduce new features
   ```

2. **Data Analysis Queries**
   ```text
   Users can query:
   - Energy consumption statistics: "How does this month's electricity usage compare to last month?"
   - Behavior analysis: "What appliances do we use most often?"
   
   System will:
   - Calculate historical data
   - Generate trend reports
   - Compare analysis results
   - Provide optimization suggestions
   ```

#### General Knowledge Q&A Capabilities

1. **Technology and Nature**
   ```text
   Users can ask about:
   - Technology frontier: "How is the latest AI development?"
   - Natural science: "Why do earthquakes occur?"
   - Life encyclopedia: "How to properly care for skin?"
   
   System will:
   - Provide accurate information
   - Explain principles and mechanisms
   - Give examples
   - Recommend further reading
   ```

2. **Real-time Information**
   ```text
   Users can learn about:
   - News updates: "What are the important recent news?"
   - Weather information: "What's tomorrow's weather like?"
   - Sports events: "What are the important recent matches?"
   - Entertainment news: "Latest movie recommendations"
   
   System will:
   - Get latest information
   - Provide brief overview
   - Analyze important impacts
   - Recommend related content
   ```

3. **Life Services**
   ```text
   Users can consult about:
   - Health advice: "How to maintain good sleep habits?"
   - Food cooking: "How to make the best braised pork?"
   - Travel guides: "What are fun places nearby?"
   - Life tips: "How to organize rooms more efficiently?"
   
   System will:
   - Provide practical advice
   - Share experience and tips
   - Recommend specific solutions
   - Remind precautions
   ```

> Note: System will provide the latest and most accurate information through intelligent analysis and online search. For questions requiring professional judgment (such as medical, legal, etc.), it's recommended to only use as reference and consult relevant professionals.

### Service Callers

ZhipuAI integration provides multiple powerful service callers that can be used through Home Assistant's service call interface or automation:

#### 1. Image Analysis Service (image_analyzer)
```yaml
service: zhipuai.image_analyzer
data:
  model: "glm-4v-flash"  # Required, options: glm-4v-plus, glm-4v, glm-4v-flash
  message: "Please describe the content of this image"  # Required, prompt for the model
  image_file: "/config/www/tmp/front_door.jpg"  # Optional, local image path
  image_entity: "camera.front_door"  # Optional, image or camera entity
  temperature: 0.8  # Optional, controls output randomness (0.1-1.0)
  max_tokens: 1024  # Optional, limits generated text length
  stream: false  # Optional, whether to use streaming response
```

Features:
- Supports multiple image analysis models
- Can analyze local images or camera entities
- Supports streaming response for real-time results
- Supports jpg, png, jpeg formats (max 5MB, max resolution 6000x6000 pixels)

#### 2. Video Analysis Service (video_analyzer)
```yaml
service: zhipuai.video_analyzer
data:
  model: "glm-4v-plus"  # Optional, only supports glm-4v-plus
  message: "Please describe the content of this video"  # Required, prompt
  video_file: "/config/www/tmp/video.mp4"  # Required, local video file path
  temperature: 0.8  # Optional, controls output randomness
  max_tokens: 1024  # Optional, limits generated text length
  stream: false  # Optional, whether to use streaming response
```

Features:
- Professional video content analysis
- Supports mp4 format
- Recommended video duration under 30 seconds
- Real-time streaming response option

#### 3. Image Generation Service (image_gen)
```yaml
service: zhipuai.image_gen
data:
  prompt: "A cute little cat"  # Required, image description
  model: "cogview-3-flash"  # Optional, defaults to free cogview-3-flash
  size: "1024x1024"  # Optional, image size
```

Supported models:
- CogView-3 Plus
- CogView-3
- CogView-3 Flash (free version)

Supported sizes:
- 1024x1024
- 768x1344
- 864x1152
- 1344x768
- 1152x864
- 1440x720
- 720x1440

#### 4. Web Search Service (web_search)
```yaml
service: zhipuai.web_search
data:
  query: "Today's news summary"  # Required, search content
  stream: false  # Optional, whether to use streaming response
```

Features:
- Uses ZhipuAI's web-search-pro tool
- Supports real-time streaming response
- Provides accurate search results

#### 5. Entity Analysis Service (entity_analysis)
```yaml
service: zhipuai.entity_analysis
data:
  entity_id: 
    - "sensor.living_room_temperature"
    - "binary_sensor.motion_sensor"  # Required, supports multiple entities
  days: 3  # Optional, analysis days (1-15 days)
```

Features:
- Supports multiple entity simultaneous analysis
- Flexible historical record queries
- Suitable for various sensor data analysis
- Supports 1-15 days data range

#### Usage Examples

1. **Smart Camera Image Analysis**
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
      message: "Analyze if there's someone at the door, describe the scene in detail"
      image_entity: camera.front_door
      stream: true
```

2. **Regular Weather Art Generation**
```yaml
automation:
  trigger:
    platform: time
    at: "08:00:00"
  action:
    service: zhipuai.image_gen
    data:
      prompt: "Artistic representation of {{states('weather.home')}} weather"
      model: "cogview-3-flash"
      size: "1024x1024"
```

3. **Smart Home Data Analysis**
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

### ⚠️ Important Notes
> 1. 📁 Ensure Home Assistant has access permissions for image and video files
> 2. ⏱️ Video analysis is recommended to use shorter videos for better results
> 3. ⚡ Using streaming response can provide better real-time experience but increases system load
> 4. 💫 Image generation service is recommended to start with the free Flash version
> 5. 📊 Entity analysis service days should be chosen based on actual needs, avoid analyzing too much historical data
