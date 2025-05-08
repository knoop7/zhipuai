import logging
LOGGER = logging.getLogger(__name__)

DOMAIN = "zhipuai"
NAME = "config.step.user.data.name"
DEFAULT_NAME = "智谱清言"
CONF_API_KEY = "api_key"
CONF_RECOMMENDED = "recommended"
CONF_PROMPT = "prompt"
CONF_CHAT_MODEL = "chat_model"
RECOMMENDED_CHAT_MODEL = "glm-4-flash-250414"
CONF_MAX_TOKENS = "max_tokens"
RECOMMENDED_MAX_TOKENS = 250
CONF_TOP_P = "top_p"
RECOMMENDED_TOP_P = 0.5
CONF_REQUEST_TIMEOUT = "request_timeout"
DEFAULT_REQUEST_TIMEOUT = 30  
CONF_TEMPERATURE = "temperature"
RECOMMENDED_TEMPERATURE = 0.3
CONF_MAX_HISTORY_MESSAGES = "max_history_messages"
RECOMMENDED_MAX_HISTORY_MESSAGES = 30

CONF_MAX_TOOL_ITERATIONS = "max_tool_iterations"
DEFAULT_MAX_TOOL_ITERATIONS = 20


CONF_WEB_SEARCH = "web_search"
DEFAULT_WEB_SEARCH = True

STATE_READY = "就绪"
STATE_SPEAKING = "说话中"
STATE_ERROR = "错误"

ZHIPUAI_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"


DEFAULT_LANGUAGE = "zh-CN"
DEFAULT_CONVERSATION_MODE = "conversation.mode.add_name"

ERROR_INVALID_AUTH = "API密钥无效或已过期"
ERROR_TOO_MANY_REQUESTS = "请求过于频繁，请稍后再试"
ERROR_SERVER_ERROR = "AI服务器暂时不可用，请稍后再试"
ERROR_TIMEOUT = "请求超时，请稍后再试"
ERROR_UNKNOWN = "未知错误"

MAX_RETRIES = 3  
RETRY_DELAY = 1  
MAX_HISTORY_LENGTH = 10  

ZHIPUAI_WEB_SEARCH_URL = "https://open.bigmodel.cn/api/paas/v4/tools"

CONF_WEB_SEARCH_STREAM = "web_search_stream"
DEFAULT_WEB_SEARCH_STREAM = False

ZHIPUAI_IMAGE_GEN_URL = "https://open.bigmodel.cn/api/paas/v4/images/generations"
CONF_IMAGE_GEN = "image_gen"
DEFAULT_IMAGE_GEN = False

CONF_IMAGE_SIZE = "image_size"
DEFAULT_IMAGE_SIZE = "1024x1024"

IMAGE_SIZES = [
    "1024x1024",
    "768x1344",
    "864x1152",
    "1344x768",
    "1152x864",
    "1440x720",
    "720x1440"
]


CONF_HISTORY_ANALYSIS = "history_analysis"
CONF_HISTORY_ENTITIES = "history_entities"
CONF_HISTORY_DAYS = "history_days"
CONF_HISTORY_INTERVAL = "history_interval"
DEFAULT_HISTORY_INTERVAL = 10  
DEFAULT_HISTORY_ANALYSIS = False
DEFAULT_HISTORY_DAYS = 1
MAX_HISTORY_DAYS = 15

CONF_PRESENCE_PENALTY = "presence_penalty"
CONF_FREQUENCY_PENALTY = "frequency_penalty"
CONF_STOP_SEQUENCES = "stop_sequences"
CONF_TOOL_CHOICE = "tool_choice"
CONF_LOGIT_BIAS = "logit_bias"

DEFAULT_PRESENCE_PENALTY = 0.0
DEFAULT_FREQUENCY_PENALTY = 0.0
DEFAULT_STOP_SEQUENCES = []
DEFAULT_TOOL_CHOICE = "auto"
DEFAULT_LOGIT_BIAS = {}

CONF_FILTER_MARKDOWN = "filter_markdown"
DEFAULT_FILTER_MARKDOWN = "off"

CONF_NOTIFY_SERVICE = "notify_service"
DEFAULT_NOTIFY_SERVICE = "persistent_notification"
