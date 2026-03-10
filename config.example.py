"""
UICS配置文件示例
复制此文件为config.py并修改配置
"""

import os

# 服务器配置
SERVER_HOST = '0.0.0.0'
SERVER_PORT = 5000
DEBUG = True

# 安全配置
SECRET_KEY = os.environ.get('SECRET_KEY', 'change-this-in-production')

# 文件路径配置
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXCEL_FILE = os.path.join(os.path.dirname(BASE_DIR), 'all_episodes.xlsx')
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
OUTPUT_FOLDER = os.path.join(BASE_DIR, 'output')

# 生成器配置
COMFYUI_SERVER = '127.0.0.1:8188'
SORA_API_KEY = None  # 从环境变量或配置文件读取
SORA_HOST = 'https://grsai.dakka.com.cn'

# 音频生成器配置（火山引擎）
VOLCENGINE_APPID = None  # 从环境变量或配置文件读取
VOLCENGINE_ACCESS_TOKEN = None
VOLCENGINE_ENDPOINT = 'wss://openspeech.bytedance.com/api/v1/tts/ws_binary'

# 数据库配置（如果使用数据库）
DATABASE_URL = 'sqlite:///uics.db'

# 用户配置
DEFAULT_ADMIN_USERNAME = 'admin'
DEFAULT_ADMIN_PASSWORD = 'admin123'  # 生产环境请更改

