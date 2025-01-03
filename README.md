# Zhipu Clear Words AI Home Assistant 🏡  

![GitHub Version]( https://img.shields.io/github/v/release/knoop7/zhipuai ) ![GitHub Issues]( https://img.shields.io/github/issues/knoop7/zhipuai ) ![GitHub Forks]( https://img.shields.io/github/forks/knoop7/zhipuai?style=social ) ![GitHub Stars]( https://img.shields.io/github/stars/knoop7/zhipuai?style=social )

<a href="README.md">English</a> |  <a href="README-CN.md">简体中文</a> 


---
## Notice: This project is strictly prohibited from commercial use without permission. You may use it as a means of profit, but it cannot be concealed.
###  📦  Installation steps
#### 1.  HACS adds custom repository
In the HACS of Home Assistant, click on the three dots in the upper right corner, select "Custom Repository", and add the following URL:

```
https://github.com/knoop7/zhipuai
```


#### 2.  Add Zhipu Qingyan Integration
Go to the "Integration" page of Home Assistant, search for and add "Zhipu Qingyan".

#### 3.  Configure Key 🔑  
In the configuration page, you can log in with your phone number to obtain the Key. After obtaining it, simply fill in the Key for use without the need for additional verification.
**Attention * *: It is recommended that you create a new Key and avoid using the system's default Key.

#### 4.  Free model usage 💡  
Zhipu Qingyan has chosen the free model by default, which is completely free and there is no need to worry about charging. If you are interested, you can also choose other paid models to experience richer features.

#### 5.  Version compatibility 📅  
Please ensure that the version of Home Assistant is not lower than 8.0, as Zhipu Qingyan is mainly developed for the latest version. If encountering unrecognized entity issues, it is recommended to restart the system or update to the latest version.

---

###  🛠  Example of Model Instruction Usage
To ensure that everyone can use it smoothly and without any bugs, you can use my template instructions to try it out

````
As the smart home manager of Home Assistant, your name is "Custom", and I will provide you with smart home information and answers to your questions. Please review the following available devices, status, and operational examples.
###Display of available devices
#Note that if the entity exceeds 1000 or more
#Delete this sentence directly
###Today's oil prices:
```yaml
{% set sensor=oil price entity%}
Sensor: {{ sensor.name }}
State: {{ sensor.state }}
Attributes:
{% for attribute, value in sensor.attributes.items() %}
{{ attribute }}: {{ value }}
{% endfor %}
```
###Electricity balance information:
```yaml
{% set balance_densor=Electricity entity%}
{% if balance_sensor %}
Current balance: {{ balance_sensor.state }} {{ balance_sensor.attributes.unit_of_measurement }}
{% endif %}
```
###Tasmota energy consumption:
```yaml
{% set today_sensor = states.sensor.tasmota_energy_today %}
{% set yesterday_sensor = states.sensor.tasmota_energy_yesterday %}
{% if today_sensor is not none and yesterday_sensor is not none %}
Today's consumption: {{ today_sensor.state }} {{ today_sensor.attributes.unit_of_measurement }}
Yesterday's consumption: {{ yesterday_sensor.state }} {{ yesterday_sensor.attributes.unit_of_measurement }}
{% endif %}
```
###At this time, the weather is:
```json
{% set entity id='weather entity'%}
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
````
Or this template instruction
````
###Display of available devices
```csv
entity_id,name,state,category
{%- for entity in states if 'automation.' not in entity.entity_id and entity.state not in ['unknown'] and not ('device_tracker.' in entity.entity_id and  ('huawei' in entity.entity_id or 'Samsung' in entity.entity_id)) and 'iphone' not in entity.entity_id and 'daily_english' not in entity.entity_id and 'lenovo' not in entity.entity_id and 'time' not in entity.entity_id and 'zone' not in entity.entity_id and 'n1' not in entity.entity_id and 'z470' not in entity.entity_id and 'lao_huang' not in entity.entity_id and 'lao_huang_li' not in entity.entity_id and 'input_text' not in entity.entity_id and 'conversation' not in entity.entity_id  and 'camera' not in entity.entity_id  and 'update' not in entity.entity_id and 'IPhone' not in entity.entity_id and 'mac' not in entity.entity_id and 'macmini' not in entity.entity_id and 'macbook' not in entity.entity_id and 'ups' not in entity.entity_id and  'OPENWRT' not in entity.entity_id  and 'OPENWRT' not in entity.entity_id%}
{% - set category='Other'%}
{% - if 'light.' in entity. entity_id%} {% set category='light'%}
{%- elif 'sensor.' in entity.entity_id and 'battery' in entity.entity_id %}
{% set category='Battery'%}
{%- elif 'sensor.' in entity.entity_id and 'sun' in entity.entity_id %}
{% set category='Sun'%}
{%- elif 'sensor.' in entity.entity_id and ('motion' in entity.entity_id or 'presence' in entity.entity_id) %}
{% set category='human existence'%}
{%- elif 'sensor.' in entity.entity_id and ('motion' in entity.entity_id or 'presence' in entity.entity_id) %}
{% set category='human existence'%}
{% - elif 'climate.' in entity. entity_id%} {% set category='air conditioning'%}
{% - elif 'media_player.' in entity. entity_id%} {% set category='media player'%}
{% - elif 'cover.' in entity. entity_id%} {% set category='doors and windows'%}
{% - elif 'lock.' in entity. entity_id%} {% set category='door lock'%}
{% - elif's switch. 'in entity. entity_id%} {% set category=' switch '%}
{% - elif's sensor. 'in entity. entity_id%} {% set category=' sensor '%}
{% - elif 'watering.' in entity. entity_id%} {% set category='watering plant'%}
{% - elif 'fan.' in entity. entity_id%} {% set category='fan'%}
{% - elif'air_quality. 'in entity. entity_id%} {% set category=' air quality '%}
{% - elif 'vacuum.' in entity. entity_id%} {% set category='robotic vacuum cleaner'%}
{% - elif 'person.' in entity. entity_id%} {% set category='personnel'%}
{%- elif 'binary_sensor.' in entity.entity_id and ('door' in entity.entity_id or 'window' in entity.entity_id) %}{% set category = ' Doors and windows'%}
{% - elif 'gas.' in entity. entity_id%} {% set category='natural gas'%}
{% - elif 'energy.' in entity. entity_id%} {% set category='electricity consumption'%}
{% - elif's script. 'in entity. entity_id%} {% set category=' script '%}
{% - elif's scene. 'in entity. entity_id%} {% set category=' scene '%}
{%- endif %}
{{- entity.entity_id }},{{ entity.name }},{{ entity.state }},{{ category }}
{%- endfor %}
````
---
### Using the built-in API to expose entities 🌐  

You can use the built-in API of Zhipu Qingyan to expose entities and set aliases for them. By renaming entities, you can avoid confusion caused by using system default names and improve management efficiency.

---
###  🚀  Usage Guide
1. Access interface
  Open the Home Assistant dashboard and find the "Zhipu Qingyan" integrated card or corresponding integrated page.
  
2. Enter commands
   In the integrated page or dialog box, enter natural language commands or use voice assistants to issue commands.

3.  View response
   The system will execute tasks according to your instructions, and real-time display and feedback of device status changes will be provided.

---
###  📑  Common Instruction Examples

- Turn on the living room light
- Set the bedroom temperature to 22 degrees
- Play music
- Remind me of the memo tomorrow at 7 o'clock
- Check the status of the door lock
- Take a look at the temperature and humidity throughout the house“
---

###  🛠  Bug Handling

If you encounter persistent Python errors during use, it is recommended to restart the dialog box and reload the environment. This can solve some potential code issues.

---

###  🗂  Dealing with entities that are not recognized by Home Assistant

If there are entities in Home Assistant that are not recognized, you can remove these entities from the scope of automated control. By adding Jinja2 templates to instructions, it is possible to effectively avoid Python error prompts and eliminate potential issues.

---

### Additional Tips
- System version requirement : Zhipu Qingyan requires Home Assistant to support at least version 8.0.
-  Suggestion: If you encounter compatibility issues, it is recommended to restart or update the system. Usually, this can solve most problems.
-  Related projects * * If voice to text conversion is required, free online AI model integration can be used for personal secondary deep modification
    ```` https://github.com/knoop7/groqcloud_whisper ````
