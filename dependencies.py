from datetime import datetime, timezone

import os
import google.generativeai as genai
from openai import AsyncOpenAI, AsyncAzureOpenAI
from app.config import AZURE_DEPLOYMENT_5_MINI_1, AZURE_DEPLOYMENT_5_MINI_2, AZURE_DEPLOYMENT_5_MINI_3, GOOGLE_API_KEY, OPENAI_API_KEY_1, OPENAI_API_KEY_2, AZURE_4o_DEPLOYMENT_1, AZURE_DEPLOYMENT_1, AZURE_DEPLOYMENT_2, AZURE_DEPLOYMENT_3, APP_ENV

# Use this if you want to save the output to a file locally
cache_file_path = os.path.join(os.getcwd(), "cache_file.md")

websocket_connections = {}

try:
    genai.configure(api_key=GOOGLE_API_KEY)
except Exception as e:
    print("Error accessing Gemini API key: " + str(e))

handler_functions_status = [True] * 4
handler_functions_timeouts = [datetime(1970, 1, 1, 0, 0, 0, 0, timezone.utc)] * 4

model_list = [{
    "model_name": "gpt-4o-mini",
    "litellm_params": {
        "model": "azure/" + AZURE_DEPLOYMENT_1["deployment"],
        "api_key": AZURE_DEPLOYMENT_1["api_key"],
        "api_version": AZURE_DEPLOYMENT_1["api_version"],
        "api_base": AZURE_DEPLOYMENT_1["endpoint"],
        "tpm": 2000000,
        "rpm": 20000,
    },
    "model_info": {
        "base_model": "azure/gpt-4o-mini"
    }
}, {
    "model_name": "gpt-4o-mini",
    "litellm_params": {
        "model": "azure/" + AZURE_DEPLOYMENT_2["deployment"],
        "api_key": AZURE_DEPLOYMENT_2["api_key"],
        "api_version": AZURE_DEPLOYMENT_2["api_version"],
        "api_base": AZURE_DEPLOYMENT_2["endpoint"],
        "tpm": 2000000,
        "rpm": 20000,
    },
    "model_info": {
        "base_model": "azure/gpt-4o-mini"
    }
}, {
    "model_name": "gpt-4o-mini-fallback",
    "litellm_params": {
        "model": "azure/" + AZURE_DEPLOYMENT_3["deployment"],
        "api_key": AZURE_DEPLOYMENT_3["api_key"],
        "api_version": AZURE_DEPLOYMENT_3["api_version"],
        "api_base": AZURE_DEPLOYMENT_3["endpoint"],
        "tpm": 2000000,
        "rpm": 20000,
    },
    "model_info": {
        "base_model": "azure/gpt-4o-mini"
    }
}, {
    "model_name": "gpt-5-mini",
    "litellm_params": {
        "model": "azure/" + AZURE_DEPLOYMENT_5_MINI_1["deployment"],
        "api_key": AZURE_DEPLOYMENT_5_MINI_1["api_key"],
        "api_version": AZURE_DEPLOYMENT_5_MINI_1["api_version"],
        "api_base": AZURE_DEPLOYMENT_5_MINI_1["endpoint"],
        "tpm": AZURE_DEPLOYMENT_5_MINI_1["tpm"],
        "rpm": AZURE_DEPLOYMENT_5_MINI_1["rpm"],
    },
    "model_info": {
        "base_model": "azure/gpt-5-mini"
    }
}, {
    "model_name": "gpt-5-mini",
    "litellm_params": {
        "model": "azure/" + AZURE_DEPLOYMENT_5_MINI_2["deployment"],
        "api_key": AZURE_DEPLOYMENT_5_MINI_2["api_key"],
        "api_version": AZURE_DEPLOYMENT_5_MINI_2["api_version"],
        "api_base": AZURE_DEPLOYMENT_5_MINI_2["endpoint"],
        "tpm": AZURE_DEPLOYMENT_5_MINI_2["tpm"],
        "rpm": AZURE_DEPLOYMENT_5_MINI_2["rpm"],
    },
    "model_info": {
        "base_model": "azure/gpt-5-mini"
    }
}, {
    "model_name": "gpt-5-mini-fallback",
    "litellm_params": {
        "model": "azure/" + AZURE_DEPLOYMENT_5_MINI_3["deployment"],
        "api_key": AZURE_DEPLOYMENT_5_MINI_3["api_key"],
        "api_version": AZURE_DEPLOYMENT_5_MINI_3["api_version"],
        "api_base": AZURE_DEPLOYMENT_5_MINI_3["endpoint"],
        "tpm": AZURE_DEPLOYMENT_5_MINI_3["tpm"],
        "rpm": AZURE_DEPLOYMENT_5_MINI_3["rpm"],
    },
    "model_info": {
        "base_model": "azure/gpt-5-mini"
    }
}]

SEVERITY_MAP = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
}

EXTENSION_TO_LANGUAGE = {
    '.py': 'Python',
    '.js': 'JavaScript',
    '.ts': 'TypeScript',
    '.jsx': 'JavaScript',
    '.tsx': 'TypeScript',
    '.java': 'Java',
    '.go': 'Go',
    '.rb': 'Ruby',
    '.cpp': 'C++',
    '.c': 'C',
    '.cs': 'CSharp',
    '.php': 'PHP',
    '.rs': 'Rust',
    '.swift': 'Swift',
    '.kt': 'Kotlin',
    '.m': 'Objective-C',
    '.scala': 'Scala',
    '.html': 'HTML',
    '.css': 'CSS',
    '.scss': 'SCSS',
    '.vue': 'Vue',
    '.sh': 'Shell',
    '.sql': 'SQL',
}

from azure.monitor.opentelemetry import configure_azure_monitor
from logging import getLogger

if APP_ENV == "local":
    logger = getLogger("uvicorn")

else:
    configure_azure_monitor()
    logger = getLogger("CodeSherlock Monitor")

logger.setLevel("INFO")