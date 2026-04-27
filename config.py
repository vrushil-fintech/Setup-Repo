import os
from dotenv import load_dotenv

APP_ENV = "local"

if APP_ENV == "local":
    load_dotenv(dotenv_path=".env.local")

else:
    load_dotenv()

# Database configuration
DB_CONFIG = {
    "drivername": "postgresql+psycopg2",
    "username": os.getenv("DB_USERNAME"),
    "password": os.getenv("DB_PASSWORD"),
    "host": os.getenv("DB_HOST"),
    "port": int(os.getenv("DB_PORT")),
    "database": os.getenv("DB_DATABASE"),
}

MONGODB_CONFIG = {
    "conn_url": os.getenv("MONGODB_CONN_URL"),
    "database": os.getenv("MONGODB_DATABASE"),
}

# Authentication configuration
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 14
OTP_EXPIRE_MINUTES = 5
COOKIE_EXPIRE_SECONDS = 24 * 60 * 60
if APP_ENV == "local":
    COOKIE_SAMESITE = "none"
    COOKIE_DOMAIN = None

else:
    COOKIE_SAMESITE = "strict"
    COOKIE_DOMAIN = ".codesherlock.ai"

# CORS configuration
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    os.getenv("ALLOWED_ORIGIN1"),
    os.getenv("ALLOWED_ORIGIN2"),
    os.getenv("ALLOWED_ORIGIN3"),
]

# Email service configuration
EMAIL_SERVICE_CONNECTION_STRING = os.getenv("EMAIL_SERVICE_CONNECTION_STRING")
EMAIL_SENDER_ADDRESS = os.getenv("EMAIL_SENDER_ADDRESS")
CONTACT_US_RECEIVER_EMAIL = os.getenv("CONTACT_US_RECEIVER_EMAIL")
# LLM Endpoints configuration
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY_1")

OPENAI_API_KEY_1 = os.getenv("OPENAI_API_KEY_1")
OPENAI_API_KEY_2 = os.getenv("OPENAI_API_KEY_2")

AZURE_4o_DEPLOYMENT_1 = {
    "api_key": os.getenv("AZ_DEPLOYMENT_4o_API_KEY"),
    "endpoint": os.getenv("AZ_DEPLOYMENT_4o_ENDPOINT"),
    "deployment": os.getenv("AZ_DEPLOYMENT_4o_DEPLOYMENT"),
    "api_version": os.getenv("AZ_DEPLOYMENT_4o_API_VERSION"),
}

AZURE_DEPLOYMENT_1 = {
    "api_key": os.getenv("AZ_DEPLOYMENT_1_API_KEY"),
    "endpoint": os.getenv("AZ_DEPLOYMENT_1_ENDPOINT"),
    "deployment": os.getenv("AZ_DEPLOYMENT_1_DEPLOYMENT"),
    "api_version": os.getenv("AZ_DEPLOYMENT_1_API_VERSION"),
}

AZURE_DEPLOYMENT_2 = {
    "api_key": os.getenv("AZ_DEPLOYMENT_2_API_KEY"),
    "endpoint": os.getenv("AZ_DEPLOYMENT_2_ENDPOINT"),
    "deployment": os.getenv("AZ_DEPLOYMENT_2_DEPLOYMENT"),
    "api_version": os.getenv("AZ_DEPLOYMENT_2_API_VERSION"),
}

AZURE_DEPLOYMENT_3 = {
    "api_key": os.getenv("AZ_DEPLOYMENT_3_API_KEY"),
    "endpoint": os.getenv("AZ_DEPLOYMENT_3_ENDPOINT"),
    "deployment": os.getenv("AZ_DEPLOYMENT_3_DEPLOYMENT"),
    "api_version": os.getenv("AZ_DEPLOYMENT_3_API_VERSION"),
}

AZURE_DEPLOYMENT_5_MINI_1 = {
    "api_key": os.getenv("AZ_DEPLOYMENT_5_MINI_1_API_KEY"),
    "endpoint": os.getenv("AZ_DEPLOYMENT_5_MINI_1_ENDPOINT"),
    "deployment": os.getenv("AZ_DEPLOYMENT_5_MINI_1_DEPLOYMENT"),
    "api_version": os.getenv("AZ_DEPLOYMENT_5_MINI_1_API_VERSION"),
    "tpm": os.getenv("AZ_DEPLOYMENT_5_MINI_1_TPM"),
    "rpm": os.getenv("AZ_DEPLOYMENT_5_MINI_1_RPM"),
}

AZURE_DEPLOYMENT_5_MINI_2 = {
    "api_key": os.getenv("AZ_DEPLOYMENT_5_MINI_2_API_KEY"),
    "endpoint": os.getenv("AZ_DEPLOYMENT_5_MINI_2_ENDPOINT"),
    "deployment": os.getenv("AZ_DEPLOYMENT_5_MINI_2_DEPLOYMENT"),
    "api_version": os.getenv("AZ_DEPLOYMENT_5_MINI_2_API_VERSION"),
    "tpm": os.getenv("AZ_DEPLOYMENT_5_MINI_2_TPM"),
    "rpm": os.getenv("AZ_DEPLOYMENT_5_MINI_2_RPM"),
}

AZURE_DEPLOYMENT_5_MINI_3 = {
    "api_key": os.getenv("AZ_DEPLOYMENT_5_MINI_3_API_KEY"),
    "endpoint": os.getenv("AZ_DEPLOYMENT_5_MINI_3_ENDPOINT"),
    "deployment": os.getenv("AZ_DEPLOYMENT_5_MINI_3_DEPLOYMENT"),
    "api_version": os.getenv("AZ_DEPLOYMENT_5_MINI_3_API_VERSION"),
    "tpm": os.getenv("AZ_DEPLOYMENT_5_MINI_3_TPM"),
    "rpm": os.getenv("AZ_DEPLOYMENT_5_MINI_3_RPM"),
}

LLM_API_COUNTER = 3

# Cost configuration
OPENAI_COST = {
    "gpt-3.5-turbo-0125": {
        "input_tokens": 0.0005,
        "response_tokens": 0.0015,
    },
    "gpt-4-turbo-preview": {
        "input_tokens": 0.01,
        "response_tokens": 0.03,
    },
    "gpt-4o-mini": {
        "input_tokens": 0.00015,
        "cached_input_tokens": 0.000075,
        "response_tokens": 0.00060,
    },
    "gpt-5-mini": {
        "input_tokens": 0.00025,
        "cached_input_tokens": 0.000025,
        "response_tokens": 0.002,
    },
}

GEMINI_COST = {
    "gemini-1.0-pro": {
        "input_tokens": 0.0005,
        "response_tokens": 0.0015,
    },
    "gemini-1.5-flash": {
        "input_tokens": 0.00035,
        "response_tokens": 0.00105,
    },
    "gemini-1.5-pro": {
        "input_tokens": 0.0035,
        "response_tokens": 0.0105,
    },
}
MAX_INPUT_TOKENS = 127000
GPT_4O_INPUT_TOKENS = 14000
MIN_INPUT_TOKENS = 400
MIN_ISSUE_LIMIT = 3
SMALL_LINES_TOKEN_LIMIT = 150

EVENT_GRID_NEWSLETTER_ENDPOINT = os.getenv("EVENT_GRID_NEWSLETTER_ENDPOINT")
EVENT_GRID_NEWSLETTER_ACCESS_KEY = os.getenv("EVENT_GRID_NEWSLETTER_ACCESS_KEY")
GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET")

LITELLM_ALLOWED_FAILS = int(os.getenv("LITELLM_ALLOWED_FAILS"))
LITELLM_COOLDOWN_TIME = int(os.getenv("LITELLM_COOLDOWN_TIME"))

# Default LLM Model Configuration
DEFAULT_LLM_MODEL = "gpt-5-mini"

GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")
GITHUB_APP_ID = os.getenv("GITHUB_APP_ID")
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_API_URL = "https://api.github.com/user"
GITHUB_AUTH_URL = "https://github.com/login/oauth/authorize"
GITHUB_APP_INSTALL_URL = f"https://github.com/apps/{GITHUB_APP_ID}/installations/new"

frontend_urls = {
    "local": "http://127.0.0.1:3000",
    "dev": "https://dev.codesherlock.ai",
    "test": "https://test.codesherlock.ai",
    "prelive": "https://prelive.codesherlock.ai",
    "prod": "https://codesherlock.ai",
}
FRONTEND_URL = frontend_urls[APP_ENV]

private_key_paths = {
    "local": "local.private-key.pem",
    "dev": "codesherlock-ai-dev.2025-04-04.private-key.pem",
    "test": "codesherlock-ai-test.2025-04-14.private-key.pem",
    "prelive": "codesherlock-ai-prelive.2025-04-22.private-key.pem",
    "prod": "codesherlock-ai.2026-01-08.private-key.pem",
}
PRIVATE_KEY_PATH = private_key_paths.get(APP_ENV)
if PRIVATE_KEY_PATH is None:
    raise ValueError(
        f"Invalid APP_ENV value: {APP_ENV}. Expected one of: {', '.join(private_key_paths.keys())}"
    )

FREE_TOKENS_LIMIT = 150_000
PAID_TOKENS_LIMIT = 3_000_000

FACTORS_LIST = [
    "maintainability",
    "performance",
    "reliability",
    "resilience",
    "scalability",
    "unittestability",
    "security",
    "power_analysis",
    "owasp",
    # "cwe",
    # "soc2",
    "cwe_mitre",
    "cwe_kev",
]


RANDOM_CODE_MIN = 100000
RANDOM_CODE_MAX = 999999

YAML_FILE_PATH = ".github/codesherlock.yaml"
STRIPE_REST_API = os.getenv("STRIPE_REST_API")
