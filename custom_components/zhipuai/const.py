import logging

DOMAIN = "zhipuai"
LOGGER = logging.getLogger(__name__)
NAME = "自定义名称"
DEFAULT_NAME = "智谱清言"
CONF_RECOMMENDED = "recommended"
CONF_PROMPT = "prompt"
CONF_CHAT_MODEL = "chat_model"
RECOMMENDED_CHAT_MODEL = "GLM-4-Flash"
CONF_MAX_TOKENS = "max_tokens"
RECOMMENDED_MAX_TOKENS = 350
CONF_TOP_P = "top_p"
RECOMMENDED_TOP_P = 0.7
CONF_TEMPERATURE = "temperature"
RECOMMENDED_TEMPERATURE = 0.4
CONF_MAX_HISTORY_MESSAGES = "max_history_messages"
RECOMMENDED_MAX_HISTORY_MESSAGES = 5

CONF_MAX_TOOL_ITERATIONS = "max_tool_iterations"
DEFAULT_MAX_TOOL_ITERATIONS = 20
CONF_COOLDOWN_PERIOD = "cooldown_period"
DEFAULT_COOLDOWN_PERIOD = 3

ZHIPUAI_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
