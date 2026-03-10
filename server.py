"""
UICS服务器端 - 多用户Excel编辑和媒体生成系统 (FastAPI版本)
"""
import os
import json
import logging
import threading
import uuid
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from fastapi import FastAPI, HTTPException, Depends, WebSocket, WebSocketDisconnect, Header, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pandas as pd
from passlib.context import CryptContext

# 导入现有的生成器模块：优先使用 UICS/lib（便于整体移动部署），否则使用项目根目录
import sys
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(_BASE_DIR, "lib")
_PROJECT_ROOT = os.path.dirname(_BASE_DIR)
if os.path.isdir(_LIB_DIR) and os.path.isfile(os.path.join(_LIB_DIR, "excel_reader.py")):
    sys.path.insert(0, _LIB_DIR)
else:
    sys.path.insert(0, _PROJECT_ROOT)
try:
    from excel_reader import ExcelDataReader
    from image_generator import batch_generate_images_from_excel_data, create_generator as create_image_generator
    from video_generator import (
        batch_generate_videos_from_excel_data,
        create_video_generator,
        DEFAULT_COMFYUI_VIDEO_WORKFLOW,
    )
    from audio_generator import batch_generate_audio_from_excel_data, create_audio_generator
except ImportError as e:
    print(f"警告: 无法导入生成器模块: {e}")
    ExcelDataReader = None

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 初始化FastAPI应用
app = FastAPI(title="UICS API", description="多用户Excel编辑与媒体生成系统", version="1.0.0")

# 配置
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)  # 项目根目录（050tool）
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
# 输出目录使用UICS目录下的output
OUTPUT_FOLDER = os.path.join(BASE_DIR, 'output')
# Excel文件路径：服务器使用UICS目录下的all_episodes.xlsx，而不是项目根目录的all_episodes.xlsx
# excel_reader.py仍然从项目根目录的all_episodes.xlsx加载（保持不变）
EXCEL_FILE = os.path.join(BASE_DIR, 'all_episodes.xlsx')  # UICS/all_episodes.xlsx
SECRET_KEY = os.environ.get('SECRET_KEY', 'your-secret-key-change-in-production')

# 输出配置信息
logger.info("=" * 60)
logger.info("UICS服务器配置信息:")
logger.info(f"  项目根目录: {PROJECT_ROOT}")
logger.info(f"  UICS目录: {BASE_DIR}")
logger.info(f"  输出目录: {OUTPUT_FOLDER}")
logger.info(f"  输出目录存在: {os.path.exists(OUTPUT_FOLDER)}")
logger.info(f"  Excel文件: {EXCEL_FILE}")
logger.info(f"  Excel文件存在: {os.path.exists(EXCEL_FILE)}")
if os.path.exists(OUTPUT_FOLDER):
    files = os.listdir(OUTPUT_FOLDER)
    logger.info(f"  输出目录文件数量: {len(files)}")
    if files:
        logger.info(f"  输出目录示例文件: {files[:5]}")
logger.info("=" * 60)

# 确保目录存在
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# 启用CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 密码加密上下文
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 用户数据文件路径
USERS_FILE = os.path.join(BASE_DIR, 'users.json')
users_lock = threading.Lock()

def load_users() -> Dict[str, Dict]:
    """从文件加载用户数据"""
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.info(f"从文件加载用户数据: {len(data)} 个用户")
                return data
        except Exception as e:
            logger.error(f"加载用户数据失败: {e}")
            # 如果加载失败，返回默认管理员用户
            return {
                'admin': {
                    'password': pwd_context.hash('admin123'),
                    'role': 'admin',
                    'created_at': datetime.now().isoformat()
                }
            }
    else:
        # 如果文件不存在，创建默认管理员用户
        default_users = {
            'admin': {
                'password': pwd_context.hash('admin123'),
                'role': 'admin',
                'created_at': datetime.now().isoformat()
            }
        }
        save_users(default_users)
        logger.info("创建默认用户数据文件")
        return default_users

def save_users(users_data: Dict[str, Dict]):
    """保存用户数据到文件"""
    try:
        logger.info(f"[保存用户] 开始保存用户数据，用户数量: {len(users_data)}")
        logger.info(f"[保存用户] 文件路径: {USERS_FILE}")
        logger.info(f"[保存用户] 文件目录存在: {os.path.exists(os.path.dirname(USERS_FILE))}")
        
        # 确保目录存在
        os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True)
        
        # 准备要保存的数据（确保所有值都是可序列化的）
        save_data = {}
        for username, user_info in users_data.items():
            save_data[username] = {
                'password': str(user_info.get('password', '')),
                'role': str(user_info.get('role', 'user')),
                'created_at': str(user_info.get('created_at', datetime.now().isoformat()))
            }
        
        logger.info(f"[保存用户] 准备写入文件，用户列表: {list(save_data.keys())}")
        
        # 使用临时文件，然后原子性重命名
        temp_file = USERS_FILE + '.tmp'
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(save_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"[保存用户] 临时文件已写入: {temp_file}")
        
        # 原子性重命名
        import shutil
        try:
            shutil.move(temp_file, USERS_FILE)
            logger.info(f"[保存用户] 文件重命名成功")
        except Exception as e:
            logger.error(f"[保存用户] 文件重命名失败: {e}")
            # 如果重命名失败，尝试直接写入
            if os.path.exists(temp_file):
                shutil.copy(temp_file, USERS_FILE)
                os.remove(temp_file)
                logger.info(f"[保存用户] 使用复制方式保存文件")
        
        logger.info(f"[保存用户] ✓ 保存用户数据到文件成功: {len(save_data)} 个用户")
        
        # 验证文件是否真的写入了
        if os.path.exists(USERS_FILE):
            file_size = os.path.getsize(USERS_FILE)
            logger.info(f"[保存用户] ✓ 文件已创建，大小: {file_size} bytes")
            
            # 读取并验证
            try:
                with open(USERS_FILE, 'r', encoding='utf-8') as f:
                    verify_data = json.load(f)
                    logger.info(f"[保存用户] ✓ 验证: 文件中包含 {len(verify_data)} 个用户")
                    for username in verify_data.keys():
                        logger.info(f"[保存用户]   用户: {username}")
            except Exception as e:
                logger.error(f"[保存用户] ✗ 验证文件内容失败: {e}")
        else:
            logger.error(f"[保存用户] ✗ 文件不存在: {USERS_FILE}")
    except Exception as e:
        logger.error(f"[保存用户] ✗ 保存用户数据失败: {e}", exc_info=True)
        import traceback
        logger.error(f"[保存用户] 错误堆栈: {traceback.format_exc()}")
        raise  # 重新抛出异常，让调用者知道保存失败

# 用户管理（从文件加载，支持持久化）
users = load_users()
logger.info(f"当前用户数量: {len(users)}")
for username in users.keys():
    logger.info(f"  用户: {username} (角色: {users[username].get('role', 'user')})")

# 活跃会话（内存存储，重启后需要重新登录）
active_sessions = {}
session_lock = threading.Lock()

# 全局事件循环引用（用于后台线程）
_global_loop = None

def set_event_loop(loop):
    """设置全局事件循环"""
    global _global_loop
    _global_loop = loop

# WebSocket连接管理
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self.websocket_rooms: Dict[WebSocket, List[str]] = {}
    
    async def connect(self, websocket: WebSocket, room: str = "default"):
        await websocket.accept()
        if room not in self.active_connections:
            self.active_connections[room] = []
        if websocket not in self.active_connections[room]:
            self.active_connections[room].append(websocket)
        if websocket not in self.websocket_rooms:
            self.websocket_rooms[websocket] = []
        if room not in self.websocket_rooms[websocket]:
            self.websocket_rooms[websocket].append(room)
    
    def disconnect(self, websocket: WebSocket, room: str = "default"):
        if room in self.active_connections:
            if websocket in self.active_connections[room]:
                self.active_connections[room].remove(websocket)
        if websocket in self.websocket_rooms:
            if room in self.websocket_rooms[websocket]:
                self.websocket_rooms[websocket].remove(room)
            if not self.websocket_rooms[websocket]:
                del self.websocket_rooms[websocket]
    
    async def send_personal_message(self, message: dict, websocket: WebSocket):
        try:
            await websocket.send_json(message)
        except:
            # 连接已断开，清理
            if websocket in self.websocket_rooms:
                for room in self.websocket_rooms[websocket].copy():
                    self.disconnect(websocket, room)
    
    async def broadcast_to_room(self, message: dict, room: str):
        if room in self.active_connections:
            disconnected = []
            for connection in self.active_connections[room].copy():
                try:
                    await connection.send_json(message)
                except:
                    disconnected.append(connection)
            for conn in disconnected:
                self.disconnect(conn, room)
    
    async def broadcast(self, message: dict):
        disconnected = []
        for room, connections in list(self.active_connections.items()):
            for connection in connections.copy():
                try:
                    await connection.send_json(message)
                except:
                    disconnected.append((connection, room))
        for conn, room in disconnected:
            self.disconnect(conn, room)

manager = ConnectionManager()


# ==================== Pydantic模型 ====================

class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    password: str

class LogoutRequest(BaseModel):
    session_id: str

class ExcelWriteRequest(BaseModel):
    sheet_name: str
    row_index: int
    row_data: Dict[str, Any]

class ExcelAddRowRequest(BaseModel):
    sheet_name: str
    row_data: Dict[str, Any] = {}

class ExcelDeleteRowRequest(BaseModel):
    sheet_name: str
    row_index: int

class GenerateImageRequest(BaseModel):
    output_dir: str = "./output"
    episode_filter: Optional[str] = None
    shot_filter: Optional[str] = None  # 添加分镜过滤参数
    generator_type: str = "comfyui"  # 生成器类型：comfyui 或 nanobanana
    comfyui_server: str = "127.0.0.1:8188"
    generate_reference: bool = True
    generate_first_frame: bool = False  # 添加首帧生成参数
    generate_last_frame: bool = False  # 添加末帧生成参数
    enable_prompt_expansion: bool = True

class GenerateVideoRequest(BaseModel):
    output_dir: str = "./output"
    episode_filter: Optional[str] = None
    shot_filter: Optional[str] = None
    generator_type: str = "comfyui"
    comfyui_server: str = "127.0.0.1:8188"
    enable_prompt_expansion: bool = True

class GenerateAudioRequest(BaseModel):
    output_dir: str = "./output"
    episode_filter: Optional[str] = None
    shot_filter: Optional[str] = None
    generator_type: str = "volcengine"  # 生成器类型：volcengine 或 comfyui
    config_path: Optional[str] = None
    comfyui_server: str = "127.0.0.1:8188"  # ComfyUI服务器地址（用于comfyui类型）
    workflow_path: Optional[str] = None  # 工作流文件路径（用于comfyui类型，默认: Qwen3-TTSVoiceCloneAPI.json）


# ==================== 认证依赖 ====================

def get_current_user(session_id: Optional[str] = Header(None, alias="X-Session-ID")):
    """获取当前用户"""
    if not session_id or session_id not in active_sessions:
        raise HTTPException(status_code=401, detail="未认证")
    return active_sessions[session_id]


# ==================== 任务管理器 ====================

class TaskManager:
    """任务管理器"""
    
    def __init__(self):
        self.tasks = {}
        self.lock = threading.Lock()
    
    def create_task(self, task_type: str, user_id: str, params: Dict) -> str:
        """创建新任务"""
        task_id = str(uuid.uuid4())
        with self.lock:
            self.tasks[task_id] = {
                'id': task_id,
                'type': task_type,
                'user_id': user_id,
                'status': 'pending',
                'progress': 0,
                'params': params,
                'created_at': datetime.now().isoformat(),
                'result': None,
                'error': None
            }
        return task_id
    
    def update_task(self, task_id: str, **kwargs):
        """更新任务状态"""
        with self.lock:
            if task_id in self.tasks:
                self.tasks[task_id].update(kwargs)
                task_data = self.tasks[task_id].copy()
        
        # 通过WebSocket通知客户端
        # 使用全局事件循环在后台线程中发送消息
        global _global_loop
        if _global_loop and not _global_loop.is_closed():
            try:
                _global_loop.call_soon_threadsafe(
                    lambda: asyncio.create_task(manager.broadcast_to_room({
                        'type': 'task_update',
                        'data': task_data
                    }, task_id))
                )
            except Exception as e:
                logger.error(f"发送任务更新通知失败: {e}")
    
    def get_task(self, task_id: str) -> Optional[Dict]:
        """获取任务信息"""
        with self.lock:
            return self.tasks.get(task_id)
    
    def list_tasks(self, user_id: Optional[str] = None) -> List[Dict]:
        """列出任务"""
        with self.lock:
            if user_id:
                return [t for t in self.tasks.values() if t['user_id'] == user_id]
            return list(self.tasks.values())


task_manager = TaskManager()


def _make_task_json_safe(obj: Any) -> Any:
    """递归移除或替换不可 JSON 序列化的类型（如 bytes），避免 GET /api/tasks 返回时 UnicodeDecodeError。"""
    if isinstance(obj, dict):
        return {k: _make_task_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_make_task_json_safe(v) for v in obj]
    if isinstance(obj, bytes):
        return None  # 前端不需要原始二进制，可改为 base64 若需传输
    return obj


# ==================== 认证相关API ====================

@app.post("/api/auth/login")
async def login(request: LoginRequest):
    """用户登录"""
    username = request.username
    password = request.password
    
    logger.info(f"[登录] 收到登录请求: 用户名={username}")
    
    if not username or not password:
        logger.warning(f"[登录] 用户名或密码为空")
        raise HTTPException(status_code=400, detail="用户名和密码不能为空")
    
    # 重新加载用户数据（以防文件已更新）
    global users
    with users_lock:
        if os.path.exists(USERS_FILE):
            try:
                users = load_users()
                logger.info(f"[登录] 重新加载用户数据: {len(users)} 个用户")
            except Exception as e:
                logger.warning(f"[登录] 重新加载用户数据失败: {e}，使用内存中的数据")
    
    logger.info(f"[登录] 当前用户列表: {list(users.keys())}")
    
    if username not in users:
        logger.warning(f"[登录] 用户不存在: {username}")
        raise HTTPException(status_code=401, detail="用户不存在")
    
    stored_password = users[username].get('password', '')
    logger.info(f"[登录] 验证密码，存储的密码哈希长度: {len(stored_password)}")
    
    try:
        password_valid = pwd_context.verify(password, stored_password)
        logger.info(f"[登录] 密码验证结果: {password_valid}")
    except Exception as e:
        logger.error(f"[登录] 密码验证出错: {e}", exc_info=True)
        raise HTTPException(status_code=401, detail="密码验证失败")
    
    if not password_valid:
        logger.warning(f"[登录] 密码错误")
        raise HTTPException(status_code=401, detail="密码错误")
    
    # 创建会话
    session_id = str(uuid.uuid4())
    with session_lock:
        active_sessions[session_id] = {
            'username': username,
            'role': users[username]['role'],
            'created_at': datetime.now().isoformat()
        }
    
    return {
        'success': True,
        'session_id': session_id,
        'username': username,
        'role': users[username]['role']
    }


@app.post("/api/auth/logout")
async def logout(request: LogoutRequest):
    """用户登出"""
    session_id = request.session_id
    
    with session_lock:
        if session_id in active_sessions:
            del active_sessions[session_id]
    
    return {'success': True}


@app.post("/api/auth/register")
async def register(request: RegisterRequest):
    """用户注册"""
    try:
        username = request.username
        password = request.password
        
        logger.info(f"[注册] 收到注册请求: 用户名={username}")
        
        if not username or not password:
            logger.warning(f"[注册] 用户名或密码为空")
            raise HTTPException(status_code=400, detail="用户名和密码不能为空")
        
        # 验证用户名和密码格式
        if len(username) < 3:
            logger.warning(f"[注册] 用户名太短: {username}")
            raise HTTPException(status_code=400, detail="用户名至少需要3个字符")
        
        if len(password) < 6:
            logger.warning(f"[注册] 密码太短")
            raise HTTPException(status_code=400, detail="密码至少需要6个字符")
        
        with users_lock:
            if username in users:
                logger.warning(f"[注册] 用户已存在: {username}")
                raise HTTPException(status_code=400, detail="用户已存在")
            
            # 创建新用户
            hashed_password = pwd_context.hash(password)
            users[username] = {
                'password': hashed_password,
                'role': 'user',
                'created_at': datetime.now().isoformat()
            }
            
            logger.info(f"[注册] 创建用户成功: {username}")
        
        # 保存到文件（在锁外执行，避免死锁）
        try:
            logger.info(f"[注册] 准备保存用户数据到文件: {USERS_FILE}")
            save_users(users)
            logger.info(f"[注册] ✓ 用户数据已保存到文件")
            
            # 验证文件是否真的保存了
            if os.path.exists(USERS_FILE):
                with open(USERS_FILE, 'r', encoding='utf-8') as f:
                    saved_data = json.load(f)
                    if username in saved_data:
                        logger.info(f"[注册] ✓ 验证: 用户 {username} 已成功保存到文件")
                    else:
                        logger.error(f"[注册] ✗ 验证失败: 用户 {username} 未在文件中找到")
            else:
                logger.error(f"[注册] ✗ 文件不存在: {USERS_FILE}")
        except Exception as e:
            logger.error(f"[注册] ✗ 保存用户数据失败: {e}", exc_info=True)
            # 即使保存失败，也返回成功（用户已在内存中创建）
            # 但记录错误以便排查
        
        result = {
            'success': True, 
            'message': '注册成功',
            'username': username
        }
        logger.info(f"[注册] ✓ 返回成功响应: {result}")
        return result
    except HTTPException as e:
        logger.warning(f"[注册] HTTP异常: {e.status_code} - {e.detail}")
        raise
    except Exception as e:
        logger.error(f"[注册] ✗ 注册过程发生错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"注册失败: {str(e)}")


# ==================== 预览文件查找函数 ====================

def find_preview_files(shot_id: str, output_dir: str) -> Dict[str, Optional[str]]:
    """
    查找分镜对应的预览文件
    
    Args:
        shot_id: 分镜号，如 EP01_SQ01
        output_dir: 输出目录
        
    Returns:
        包含预览文件路径的字典
    """
    import glob
    
    previews = {
        '图像预览': None,
        '首帧预览': None,
        '末帧预览': None,
        '视频预览': None
    }
    
    logger.info(f"[预览查找] 开始查找分镜 {shot_id} 的预览文件")
    logger.info(f"[预览查找] 输出目录: {output_dir}")
    logger.info(f"[预览查找] 输出目录存在: {os.path.exists(output_dir)}")
    
    if not os.path.exists(output_dir):
        logger.warning(f"[预览查找] 输出目录不存在: {output_dir}")
        return previews
    
    if not shot_id or shot_id == 'nan' or shot_id.strip() == '':
        logger.warning(f"[预览查找] 无效的分镜号: {shot_id}")
        return previews
    
    shot_id = shot_id.strip()
    logger.info(f"[预览查找] 查找分镜号: {shot_id}")
    logger.info(f"[预览查找] 输出目录绝对路径: {os.path.abspath(output_dir)}")
    
    # 列出输出目录中的所有文件（用于调试）
    try:
        all_files = os.listdir(output_dir)
        matching_files = [f for f in all_files if shot_id in f]
        logger.info(f"[预览查找] 输出目录总文件数: {len(all_files)}")
        logger.info(f"[预览查找] 包含分镜号 '{shot_id}' 的文件数: {len(matching_files)}")
        if matching_files:
            logger.info(f"[预览查找] 包含分镜号的所有文件:")
            for f in matching_files:
                full_path = os.path.join(output_dir, f)
                exists = os.path.exists(full_path)
                size = os.path.getsize(full_path) if exists else 0
                logger.info(f"[预览查找]   - {f} (存在: {exists}, 大小: {size} bytes, 完整路径: {os.path.abspath(full_path)})")
        else:
            logger.warning(f"[预览查找] 未找到包含分镜号 '{shot_id}' 的文件")
            logger.info(f"[预览查找] 输出目录中的前20个文件:")
            for f in all_files[:20]:
                logger.info(f"[预览查找]   - {f}")
    except Exception as e:
        logger.error(f"[预览查找] 列出目录文件失败: {e}", exc_info=True)
    
    # 支持的图片扩展名
    image_extensions = ['png', 'jpg', 'jpeg', 'webp']
    # 支持的视频扩展名
    video_extensions = ['mp4', 'webm', 'webp']
    
    # 查找参考图（图像预览）- 格式: {分镜号}_ref_*.{ext}
    logger.info(f"[预览查找] ========== 查找参考图 ==========")
    for ext in image_extensions:
        pattern = os.path.join(output_dir, f"{shot_id}_ref_*.{ext}")
        logger.info(f"[预览查找] 参考图模式: {pattern}")
        matches = glob.glob(pattern)
        logger.info(f"[预览查找] 匹配到的文件数量: {len(matches)}")
        if matches:
            # 按文件修改时间排序，选择最新的文件
            matches.sort(key=lambda x: os.path.getmtime(x), reverse=True)
            for i, match in enumerate(matches):
                full_path = os.path.abspath(match)
                filename = os.path.basename(match)
                file_exists = os.path.exists(full_path)
                file_size = os.path.getsize(full_path) if file_exists else 0
                file_mtime = os.path.getmtime(full_path) if file_exists else 0
                logger.info(f"[预览查找]   匹配文件 #{i+1}:")
                logger.info(f"[预览查找]     完整路径: {full_path}")
                logger.info(f"[预览查找]     文件名: {filename}")
                logger.info(f"[预览查找]     文件存在: {file_exists}")
                logger.info(f"[预览查找]     文件大小: {file_size} bytes")
                logger.info(f"[预览查找]     修改时间: {datetime.fromtimestamp(file_mtime).strftime('%Y-%m-%d %H:%M:%S')}")
            previews['图像预览'] = os.path.basename(matches[0])
            logger.info(f"[预览查找] ✓ 选择参考图: {previews['图像预览']} (完整路径: {os.path.abspath(matches[0])}, 修改时间: {datetime.fromtimestamp(os.path.getmtime(matches[0])).strftime('%Y-%m-%d %H:%M:%S')})")
            break
        else:
            logger.info(f"[预览查找]   未找到匹配文件")
    if not previews['图像预览']:
        logger.warning(f"[预览查找] ✗ 未找到参考图")
    
    # 查找首帧 - 格式: {分镜号}_first_*.{ext}
    logger.info(f"[预览查找] ========== 查找首帧 ==========")
    for ext in image_extensions:
        pattern = os.path.join(output_dir, f"{shot_id}_first_*.{ext}")
        logger.info(f"[预览查找] 首帧模式: {pattern}")
        matches = glob.glob(pattern)
        logger.info(f"[预览查找] 匹配到的文件数量: {len(matches)}")
        if matches:
            # 按文件修改时间排序，选择最新的文件
            matches.sort(key=lambda x: os.path.getmtime(x), reverse=True)
            for i, match in enumerate(matches):
                full_path = os.path.abspath(match)
                filename = os.path.basename(match)
                file_exists = os.path.exists(full_path)
                file_size = os.path.getsize(full_path) if file_exists else 0
                file_mtime = os.path.getmtime(full_path) if file_exists else 0
                logger.info(f"[预览查找]   匹配文件 #{i+1}:")
                logger.info(f"[预览查找]     完整路径: {full_path}")
                logger.info(f"[预览查找]     文件名: {filename}")
                logger.info(f"[预览查找]     文件存在: {file_exists}")
                logger.info(f"[预览查找]     文件大小: {file_size} bytes")
                logger.info(f"[预览查找]     修改时间: {datetime.fromtimestamp(file_mtime).strftime('%Y-%m-%d %H:%M:%S')}")
            previews['首帧预览'] = os.path.basename(matches[0])
            logger.info(f"[预览查找] ✓ 选择首帧: {previews['首帧预览']} (完整路径: {os.path.abspath(matches[0])}, 修改时间: {datetime.fromtimestamp(os.path.getmtime(matches[0])).strftime('%Y-%m-%d %H:%M:%S')})")
            break
        else:
            logger.info(f"[预览查找]   未找到匹配文件")
    if not previews['首帧预览']:
        logger.warning(f"[预览查找] ✗ 未找到首帧")
    
    # 查找末帧 - 格式: {分镜号}_last_*.{ext}
    logger.info(f"[预览查找] ========== 查找末帧 ==========")
    for ext in image_extensions:
        pattern = os.path.join(output_dir, f"{shot_id}_last_*.{ext}")
        logger.info(f"[预览查找] 末帧模式: {pattern}")
        matches = glob.glob(pattern)
        logger.info(f"[预览查找] 匹配到的文件数量: {len(matches)}")
        if matches:
            # 按文件修改时间排序，选择最新的文件
            matches.sort(key=lambda x: os.path.getmtime(x), reverse=True)
            for i, match in enumerate(matches):
                full_path = os.path.abspath(match)
                filename = os.path.basename(match)
                file_exists = os.path.exists(full_path)
                file_size = os.path.getsize(full_path) if file_exists else 0
                file_mtime = os.path.getmtime(full_path) if file_exists else 0
                logger.info(f"[预览查找]   匹配文件 #{i+1}:")
                logger.info(f"[预览查找]     完整路径: {full_path}")
                logger.info(f"[预览查找]     文件名: {filename}")
                logger.info(f"[预览查找]     文件存在: {file_exists}")
                logger.info(f"[预览查找]     文件大小: {file_size} bytes")
                logger.info(f"[预览查找]     修改时间: {datetime.fromtimestamp(file_mtime).strftime('%Y-%m-%d %H:%M:%S')}")
            previews['末帧预览'] = os.path.basename(matches[0])
            logger.info(f"[预览查找] ✓ 选择末帧: {previews['末帧预览']} (完整路径: {os.path.abspath(matches[0])}, 修改时间: {datetime.fromtimestamp(os.path.getmtime(matches[0])).strftime('%Y-%m-%d %H:%M:%S')})")
            break
        else:
            logger.info(f"[预览查找]   未找到匹配文件")
    if not previews['末帧预览']:
        logger.warning(f"[预览查找] ✗ 未找到末帧")
    
    # 查找视频 - 格式: {分镜号}_video_*.{ext}
    logger.info(f"[预览查找] ========== 查找视频 ==========")
    for ext in video_extensions:
        pattern = os.path.join(output_dir, f"{shot_id}_video_*.{ext}")
        logger.info(f"[预览查找] 视频模式: {pattern}")
        matches = glob.glob(pattern)
        logger.info(f"[预览查找] 匹配到的文件数量: {len(matches)}")
        if matches:
            # 按文件修改时间排序，选择最新的文件
            matches.sort(key=lambda x: os.path.getmtime(x), reverse=True)
            for i, match in enumerate(matches):
                full_path = os.path.abspath(match)
                filename = os.path.basename(match)
                file_exists = os.path.exists(full_path)
                file_size = os.path.getsize(full_path) if file_exists else 0
                file_mtime = os.path.getmtime(full_path) if file_exists else 0
                logger.info(f"[预览查找]   匹配文件 #{i+1}:")
                logger.info(f"[预览查找]     完整路径: {full_path}")
                logger.info(f"[预览查找]     文件名: {filename}")
                logger.info(f"[预览查找]     文件存在: {file_exists}")
                logger.info(f"[预览查找]     文件大小: {file_size} bytes")
                logger.info(f"[预览查找]     修改时间: {datetime.fromtimestamp(file_mtime).strftime('%Y-%m-%d %H:%M:%S')}")
            previews['视频预览'] = os.path.basename(matches[0])
            logger.info(f"[预览查找] ✓ 选择视频: {previews['视频预览']} (完整路径: {os.path.abspath(matches[0])}, 修改时间: {datetime.fromtimestamp(os.path.getmtime(matches[0])).strftime('%Y-%m-%d %H:%M:%S')})")
            break
        else:
            logger.info(f"[预览查找]   未找到匹配文件")
    if not previews['视频预览']:
        logger.warning(f"[预览查找] ✗ 未找到视频")
    
    logger.info(f"[预览查找] 查找结果: {previews}")
    return previews


# ==================== Excel相关API ====================

@app.get("/api/excel/read")
async def read_excel(current_user: dict = Depends(get_current_user)):
    """读取Excel文件"""
    try:
        if not os.path.exists(EXCEL_FILE):
            raise HTTPException(status_code=404, detail="Excel文件不存在")
        
        # 读取所有工作表
        excel_file = pd.ExcelFile(EXCEL_FILE)
        data = {}
        
        for sheet_name in excel_file.sheet_names:
            df = pd.read_excel(excel_file, sheet_name=sheet_name)
            
            # 如果是"图像汇总"工作表，添加预览列
            if sheet_name == '图像汇总':
                # 检查是否已有预览列，如果没有则添加
                preview_columns = ['图像预览', '首帧预览', '末帧预览', '视频预览']
                for col in preview_columns:
                    if col not in df.columns:
                        df[col] = ''  # 使用字符串类型而不是None
                
                # 确保预览列是字符串类型
                for col in preview_columns:
                    if col in df.columns:
                        df[col] = df[col].astype(str)
                
                # 为每一行查找预览文件
                logger.info(f"[Excel读取] ========== 开始为图像汇总工作表查找预览文件 ==========")
                logger.info(f"[Excel读取] 工作表总行数: {len(df)}")
                logger.info(f"[Excel读取] 输出目录: {OUTPUT_FOLDER}")
                logger.info(f"[Excel读取] 输出目录绝对路径: {os.path.abspath(OUTPUT_FOLDER)}")
                logger.info(f"[Excel读取] 输出目录存在: {os.path.exists(OUTPUT_FOLDER)}")
                
                for idx, row in df.iterrows():
                    shot_id_raw = row.get('分镜号', '')
                    shot_id = str(shot_id_raw).strip() if shot_id_raw else ''
                    logger.info(f"[Excel读取] ---------- 处理行 {idx} ----------")
                    logger.info(f"[Excel读取] 原始分镜号值: {repr(shot_id_raw)}")
                    logger.info(f"[Excel读取] 处理后分镜号: {repr(shot_id)}")
                    
                    if shot_id and shot_id != 'nan' and shot_id:
                        previews = find_preview_files(shot_id, OUTPUT_FOLDER)
                        found_count = sum(1 for v in previews.values() if v)
                        logger.info(f"[Excel读取] 行 {idx}, 分镜号 '{shot_id}': 找到 {found_count} 个预览文件")
                        logger.info(f"[Excel读取] 预览结果详情:")
                        for col, value in previews.items():
                            logger.info(f"[Excel读取]   {col}: {repr(value)}")
                        
                        for col in preview_columns:
                            preview_value = previews[col] if previews[col] else ''
                            df.at[idx, col] = str(preview_value)
                            logger.info(f"[Excel读取] 设置列 '{col}' = {repr(preview_value)}")
                    else:
                        logger.warning(f"[Excel读取] 行 {idx}: 跳过（分镜号为空或无效: {repr(shot_id)}）")
            
            # 将NaN转换为None，然后转换为列表
            data[sheet_name] = df.fillna('').to_dict('records')
        
        return {
            'success': True,
            'sheets': excel_file.sheet_names,
            'data': data
        }
    except Exception as e:
        logger.error(f"读取Excel文件失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/excel/write")
async def write_excel(request: ExcelWriteRequest, current_user: dict = Depends(get_current_user)):
    """写入Excel文件"""
    try:
        sheet_name = request.sheet_name
        row_data = request.row_data
        row_index = request.row_index
        
        if not os.path.exists(EXCEL_FILE):
            raise HTTPException(status_code=404, detail="Excel文件不存在")
        
        # 读取现有Excel
        excel_file = pd.ExcelFile(EXCEL_FILE)
        all_sheets = {}
        
        for sheet in excel_file.sheet_names:
            all_sheets[sheet] = pd.read_excel(excel_file, sheet_name=sheet)
        
        # 更新指定工作表的数据
        if sheet_name in all_sheets:
            df = all_sheets[sheet_name]
            
            # 如果是图像汇总工作表，确保预览列存在
            if sheet_name == '图像汇总':
                preview_columns = ['图像预览', '首帧预览', '末帧预览', '视频预览']
                for col in preview_columns:
                    if col not in df.columns:
                        df[col] = None
            
            # 确保行索引有效
            if row_index >= len(df):
                # 添加新行
                new_row = pd.DataFrame([row_data])
                df = pd.concat([df, new_row], ignore_index=True)
                
                # 如果是图像汇总，更新预览
                if sheet_name == '图像汇总':
                    shot_id = row_data.get('分镜号', '')
                    if shot_id:
                        previews = find_preview_files(str(shot_id), OUTPUT_FOLDER)
                        for col, value in previews.items():
                            if value:
                                df.at[len(df) - 1, col] = value
            else:
                # 更新现有行（排除预览列，预览列是只读的）
                preview_columns = ['图像预览', '首帧预览', '末帧预览', '视频预览']
                for col, value in row_data.items():
                    if col in df.columns and col not in preview_columns:
                        df.at[row_index, col] = value
                
                # 更新预览（如果分镜号改变）
                if sheet_name == '图像汇总':
                    shot_id = row_data.get('分镜号', '')
                    if shot_id:
                        previews = find_preview_files(str(shot_id), OUTPUT_FOLDER)
                        for col, value in previews.items():
                            if value:
                                df.at[row_index, col] = value
            
            all_sheets[sheet_name] = df
        
        # 写入Excel文件
        with pd.ExcelWriter(EXCEL_FILE, engine='openpyxl') as writer:
            for sheet, df in all_sheets.items():
                df.to_excel(writer, sheet_name=sheet, index=False)
        
        # 通知所有客户端更新
        await manager.broadcast({
            'type': 'excel_updated',
            'data': {
                'sheet_name': sheet_name,
                'row_index': row_index
            }
        })
        
        return {'success': True}
    except Exception as e:
        logger.error(f"写入Excel文件失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/excel/add_row")
async def add_row(request: ExcelAddRowRequest, current_user: dict = Depends(get_current_user)):
    """添加新行"""
    try:
        sheet_name = request.sheet_name
        row_data = request.row_data
        
        if not os.path.exists(EXCEL_FILE):
            raise HTTPException(status_code=404, detail="Excel文件不存在")
        
        # 读取现有Excel
        excel_file = pd.ExcelFile(EXCEL_FILE)
        all_sheets = {}
        
        for sheet in excel_file.sheet_names:
            all_sheets[sheet] = pd.read_excel(excel_file, sheet_name=sheet)
        
        # 添加新行
        if sheet_name in all_sheets:
            df = all_sheets[sheet_name]
            
            # 如果是图像汇总工作表，确保预览列存在
            if sheet_name == '图像汇总':
                preview_columns = ['图像预览', '首帧预览', '末帧预览', '视频预览']
                for col in preview_columns:
                    if col not in df.columns:
                        df[col] = None
            
            new_row = pd.DataFrame([row_data])
            df = pd.concat([df, new_row], ignore_index=True)
            
            # 如果是图像汇总，更新预览
            if sheet_name == '图像汇总':
                shot_id = row_data.get('分镜号', '')
                if shot_id:
                    previews = find_preview_files(str(shot_id), OUTPUT_FOLDER)
                    for col, value in previews.items():
                        if value:
                            df.at[len(df) - 1, col] = value
            
            all_sheets[sheet_name] = df
        
        # 写入Excel文件
        with pd.ExcelWriter(EXCEL_FILE, engine='openpyxl') as writer:
            for sheet, df in all_sheets.items():
                df.to_excel(writer, sheet_name=sheet, index=False)
        
        # 通知所有客户端更新
        await manager.broadcast({
            'type': 'excel_updated',
            'data': {
                'sheet_name': sheet_name,
                'action': 'add_row'
            }
        })
        
        return {'success': True}
    except Exception as e:
        logger.error(f"添加行失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/excel/delete_row")
async def delete_row(request: ExcelDeleteRowRequest, current_user: dict = Depends(get_current_user)):
    """删除行"""
    try:
        sheet_name = request.sheet_name
        row_index = request.row_index
        
        if not os.path.exists(EXCEL_FILE):
            raise HTTPException(status_code=404, detail="Excel文件不存在")
        
        # 读取现有Excel
        excel_file = pd.ExcelFile(EXCEL_FILE)
        all_sheets = {}
        
        for sheet in excel_file.sheet_names:
            all_sheets[sheet] = pd.read_excel(excel_file, sheet_name=sheet)
        
        # 删除行
        if sheet_name in all_sheets:
            df = all_sheets[sheet_name]
            if row_index < len(df):
                df = df.drop(df.index[row_index]).reset_index(drop=True)
                all_sheets[sheet_name] = df
        
        # 写入Excel文件
        with pd.ExcelWriter(EXCEL_FILE, engine='openpyxl') as writer:
            for sheet, df in all_sheets.items():
                df.to_excel(writer, sheet_name=sheet, index=False)
        
        # 通知所有客户端更新
        await manager.broadcast({
            'type': 'excel_updated',
            'data': {
                'sheet_name': sheet_name,
                'action': 'delete_row',
                'row_index': row_index
            }
        })
        
        return {'success': True}
    except Exception as e:
        logger.error(f"删除行失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 生成任务相关API ====================

@app.post("/api/generate/image")
async def generate_image(request: GenerateImageRequest, current_user: dict = Depends(get_current_user)):
    """生成图片任务"""
    if not ExcelDataReader:
        raise HTTPException(status_code=500, detail="Excel读取器不可用")
    
    try:
        params = request.dict()
        
        # 创建任务
        task_id = task_manager.create_task('image', current_user['username'], params)
        
        # 在后台线程中执行任务
        thread = threading.Thread(
            target=_generate_image_task,
            args=(task_id, params)
        )
        thread.daemon = True
        thread.start()
        
        return {
            'success': True,
            'task_id': task_id
        }
    except Exception as e:
        logger.error(f"创建图片生成任务失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/generate/video")
async def generate_video(request: GenerateVideoRequest, current_user: dict = Depends(get_current_user)):
    """生成视频任务"""
    if not ExcelDataReader:
        raise HTTPException(status_code=500, detail="Excel读取器不可用")
    
    try:
        params = request.dict()
        
        # 创建任务
        task_id = task_manager.create_task('video', current_user['username'], params)
        
        # 在后台线程中执行任务
        thread = threading.Thread(
            target=_generate_video_task,
            args=(task_id, params)
        )
        thread.daemon = True
        thread.start()
        
        return {
            'success': True,
            'task_id': task_id
        }
    except Exception as e:
        logger.error(f"创建视频生成任务失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/generate/audio")
async def generate_audio(request: GenerateAudioRequest, current_user: dict = Depends(get_current_user)):
    """生成音频任务"""
    if not ExcelDataReader:
        raise HTTPException(status_code=500, detail="Excel读取器不可用")
    
    try:
        params = request.dict()
        
        # 创建任务
        task_id = task_manager.create_task('audio', current_user['username'], params)
        
        # 在后台线程中执行任务
        thread = threading.Thread(
            target=_generate_audio_task,
            args=(task_id, params)
        )
        thread.daemon = True
        thread.start()
        
        return {
            'success': True,
            'task_id': task_id
        }
    except Exception as e:
        logger.error(f"创建音频生成任务失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str, current_user: dict = Depends(get_current_user)):
    """获取任务状态"""
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    # 检查权限
    if task['user_id'] != current_user['username'] and current_user['role'] != 'admin':
        raise HTTPException(status_code=403, detail="无权访问此任务")
    
    return _make_task_json_safe(task)


@app.get("/api/tasks")
async def list_tasks(current_user: dict = Depends(get_current_user)):
    """列出任务"""
    user_tasks = task_manager.list_tasks(
        user_id=None if current_user['role'] == 'admin' else current_user['username']
    )
    return {'tasks': [_make_task_json_safe(t) for t in user_tasks]}


# ==================== 后台任务执行函数 ====================

def _generate_image_task(task_id: str, params: Dict):
    """执行图片生成任务"""
    try:
        task_manager.update_task(task_id, status='running', progress=10)
        
        excel_path = EXCEL_FILE
        # 强制使用UICS目录下的output目录（UICS/output），忽略前端发送的路径
        output_dir = OUTPUT_FOLDER
        logger.info(f"[生成任务] 前端请求的输出目录: {params.get('output_dir', '未指定')}")
        logger.info(f"[生成任务] 实际使用的输出目录: {output_dir}")
        logger.info(f"[生成任务] 输出目录绝对路径: {os.path.abspath(output_dir)}")
        logger.info(f"[生成任务] 输出目录存在: {os.path.exists(output_dir)}")
        
        # 读取Excel数据
        reader = ExcelDataReader(excel_path, debug=False)
        data = reader.read_all()
        
        task_manager.update_task(task_id, progress=30)
        
        # 获取生成器类型
        generator_type = params.get('generator_type', 'comfyui')
        logger.info(f"[生成任务] 生成器类型: {generator_type}")
        
        # 生成图片
        # 如果指定了 shot_filter，需要先过滤图像提示词（支持多个分镜，逗号/空格分隔）
        image_prompts = reader.image_prompts
        shot_filter = params.get('shot_filter')
        if shot_filter:
            import re
            ids = [s.strip() for s in re.split(r'[,，;；\s]+', str(shot_filter)) if s.strip()]
            if ids:
                shot_set = set(ids)
                image_prompts = [p for p in image_prompts if getattr(p, '分镜号', None) in shot_set]
                if not image_prompts:
                    raise ValueError(f"未找到分镜号 {shot_filter} 的图像提示词")
        
        # 参考图目录使用 UICS 下的 scenes、characters，参考图列基准目录用 output_dir（UICS/output）
        scene_image_dir = os.path.join(BASE_DIR, 'scenes')
        character_image_dir = os.path.join(BASE_DIR, 'characters')
        # 如果指定了 shot_filter，使用过滤后的提示词列表
        if shot_filter:
            from image_generator import batch_generate_images_from_excel_data
            results = batch_generate_images_from_excel_data(
                image_prompts=image_prompts,
                output_dir=output_dir,
                generate_reference=params.get('generate_reference', True),
                generate_first_frame=params.get('generate_first_frame', False),
                generate_last_frame=params.get('generate_last_frame', False),
                comfyui_server=params.get('comfyui_server', '127.0.0.1:8188'),
                episode_filter=params.get('episode_filter'),
                generator_type=generator_type,
                enable_prompt_expansion=params.get('enable_prompt_expansion', True),
                characters=reader.characters,
                audio_tracks=reader.audio_tracks,
                scenes=reader.scenes,
                scene_image_dir=scene_image_dir,
                character_image_dir=character_image_dir,
                reference_image_dir=output_dir,
            )
        else:
            results = reader.batch_generate_images_from_prompts(
                output_dir=output_dir,
                generate_reference=params.get('generate_reference', True),
                generate_first_frame=params.get('generate_first_frame', False),
                generate_last_frame=params.get('generate_last_frame', False),
                comfyui_server=params.get('comfyui_server', '127.0.0.1:8188'),
                episode_filter=params.get('episode_filter'),
                generator_type=generator_type,
                enable_prompt_expansion=params.get('enable_prompt_expansion', True),
                scene_image_dir=scene_image_dir,
                character_image_dir=character_image_dir,
                reference_image_dir=output_dir,
            )
        
        task_manager.update_task(task_id, status='completed', progress=100, result={
            'results': results,
            'count': len(results)
        })
        
        # 通知前端刷新Excel预览（延迟发送，确保文件已写入）
        global _global_loop
        if _global_loop and not _global_loop.is_closed():
            try:
                # 延迟后发送刷新通知，确保文件已完全写入磁盘
                async def delayed_refresh():
                    shot_filter = params.get('shot_filter')
                    # 等待文件生成，最多等待10秒
                    max_wait = 10
                    wait_interval = 1
                    waited = 0
                    files_found = False
                    
                    while waited < max_wait:
                        await asyncio.sleep(wait_interval)
                        waited += wait_interval
                        
                        if shot_filter:
                            previews = find_preview_files(shot_filter, OUTPUT_FOLDER)
                            found_count = sum(1 for v in previews.values() if v)
                            logger.info(f"[图片生成] 等待文件生成 ({waited}秒): 分镜号 '{shot_filter}' 找到 {found_count} 个预览文件")
                            for col, value in previews.items():
                                if value:
                                    logger.info(f"[图片生成]   {col}: {value}")
                            
                            # 如果找到了文件，再等待2秒确保文件完全写入并刷新文件系统缓存
                            if found_count > 0:
                                files_found = True
                                await asyncio.sleep(2)
                                # 再次验证文件，确保选择的是最新文件
                                previews = find_preview_files(shot_filter, OUTPUT_FOLDER)
                                logger.info(f"[图片生成] 最终验证：分镜号 '{shot_filter}' 找到的预览文件:")
                                for col, value in previews.items():
                                    if value:
                                        logger.info(f"[图片生成]   {col}: {value}")
                                break
                    
                    if shot_filter:
                        previews = find_preview_files(shot_filter, OUTPUT_FOLDER)
                        found_count = sum(1 for v in previews.values() if v)
                        logger.info(f"[图片生成] 刷新前最终验证：分镜号 '{shot_filter}' 找到 {found_count} 个预览文件")
                        for col, value in previews.items():
                            if value:
                                logger.info(f"[图片生成]   {col}: {value}")
                        if not files_found and found_count == 0:
                            logger.warning(f"[图片生成] 警告：等待{max_wait}秒后仍未找到预览文件，可能生成失败")
                    
                    await manager.broadcast({
                        'type': 'refresh_preview',
                        'data': {
                            'task_type': 'image',
                            'task_id': task_id,
                            'shot_filter': shot_filter
                        }
                    })
                    logger.info(f"[图片生成] 已发送刷新预览通知（等待{waited}秒）")
                
                _global_loop.call_soon_threadsafe(
                    lambda: asyncio.create_task(delayed_refresh())
                )
            except Exception as e:
                logger.error(f"发送刷新预览通知失败: {e}")
        
    except Exception as e:
        logger.error(f"图片生成任务失败: {e}")
        task_manager.update_task(task_id, status='failed', error=str(e))


def _generate_video_task(task_id: str, params: Dict):
    """执行视频生成任务"""
    try:
        task_manager.update_task(task_id, status='running', progress=10)
        
        excel_path = EXCEL_FILE
        # 强制使用UICS目录下的output目录（UICS/output），忽略前端发送的路径
        output_dir = OUTPUT_FOLDER
        logger.info(f"[生成任务] 前端请求的输出目录: {params.get('output_dir', '未指定')}")
        logger.info(f"[生成任务] 实际使用的输出目录: {output_dir}")
        logger.info(f"[生成任务] 输出目录绝对路径: {os.path.abspath(output_dir)}")
        logger.info(f"[生成任务] 输出目录存在: {os.path.exists(output_dir)}")
        
        # 读取Excel数据
        reader = ExcelDataReader(excel_path, debug=False)
        data = reader.read_all()
        
        task_manager.update_task(task_id, progress=30)
        
        # 生成视频（输入图片从本地 output_dir 下查找 {分镜号}_ref.*）；ComfyUI 图生视频使用 act_video_wan2_2_14B_i2v 工作流
        generator_type = params.get('generator_type', 'comfyui')
        workflow_path = params.get('workflow_path')
        if generator_type == 'comfyui' and not workflow_path:
            import video_generator as _vg
            workflow_path = os.path.join(os.path.dirname(_vg.__file__), DEFAULT_COMFYUI_VIDEO_WORKFLOW)
            logger.info(f"[生成任务] ComfyUI 图生视频使用工作流: {workflow_path}")
        results = reader.batch_generate_videos_from_prompts(
            output_dir=output_dir,
            comfyui_server=params.get('comfyui_server', '127.0.0.1:8188'),
            workflow_path=workflow_path,
            episode_filter=params.get('episode_filter'),
            shot_filter=params.get('shot_filter'),
            generator_type=generator_type,
            enable_prompt_expansion=params.get('enable_prompt_expansion', True),
            reference_image_dir=params.get('reference_image_dir') or output_dir
        )
        
        task_manager.update_task(task_id, status='completed', progress=100, result={
            'results': results,
            'count': len(results)
        })
        
        # 通知前端刷新Excel预览（延迟发送，确保文件已写入）
        global _global_loop
        if _global_loop and not _global_loop.is_closed():
            try:
                # 延迟2秒后发送刷新通知，确保文件已完全写入磁盘
                async def delayed_refresh():
                    await asyncio.sleep(2)
                    await manager.broadcast({
                        'type': 'refresh_preview',
                        'data': {
                            'task_type': 'video',
                            'task_id': task_id,
                            'shot_filter': params.get('shot_filter')
                        }
                    })
                    logger.info(f"[视频生成] 已发送刷新预览通知（延迟2秒）")
                
                _global_loop.call_soon_threadsafe(
                    lambda: asyncio.create_task(delayed_refresh())
                )
            except Exception as e:
                logger.error(f"发送刷新预览通知失败: {e}")
        
    except Exception as e:
        logger.error(f"视频生成任务失败: {e}")
        task_manager.update_task(task_id, status='failed', error=str(e))


def _generate_audio_task(task_id: str, params: Dict):
    """执行音频生成任务"""
    try:
        task_manager.update_task(task_id, status='running', progress=10)
        
        excel_path = EXCEL_FILE
        # 强制使用UICS目录下的output目录（UICS/output），忽略前端发送的路径
        output_dir = OUTPUT_FOLDER
        logger.info(f"[生成任务] 前端请求的输出目录: {params.get('output_dir', '未指定')}")
        logger.info(f"[生成任务] 实际使用的输出目录: {output_dir}")
        logger.info(f"[生成任务] 输出目录绝对路径: {os.path.abspath(output_dir)}")
        logger.info(f"[生成任务] 输出目录存在: {os.path.exists(output_dir)}")
        
        # 读取Excel数据
        reader = ExcelDataReader(excel_path, debug=False)
        data = reader.read_all()
        
        task_manager.update_task(task_id, progress=30)
        
        # 获取生成器类型
        generator_type = params.get('generator_type', 'volcengine')
        logger.info(f"[生成任务] 生成器类型: {generator_type}")
        
        # 生成音频
        generator_kwargs = {}
        if generator_type == 'comfyui':
            # ComfyUI特定参数
            generator_kwargs['server_address'] = params.get('comfyui_server', '127.0.0.1:8188')
            generator_kwargs['workflow_path'] = params.get('workflow_path')
            logger.info(f"[生成任务] ComfyUI服务器: {generator_kwargs['server_address']}")
            if generator_kwargs['workflow_path']:
                logger.info(f"[生成任务] 工作流文件: {generator_kwargs['workflow_path']}")
        
        results = reader.batch_generate_audio_from_tracks(
            output_dir=output_dir,
            generator_type=generator_type,
            episode_filter=params.get('episode_filter'),
            shot_filter=params.get('shot_filter'),
            config_path=params.get('config_path'),
            **generator_kwargs
        )
        
        task_manager.update_task(task_id, status='completed', progress=100, result={
            'results': results,
            'count': len(results)
        })
        
        # 通知前端刷新Excel预览（音频生成也可能影响预览）
        global _global_loop
        if _global_loop and not _global_loop.is_closed():
            try:
                _global_loop.call_soon_threadsafe(
                    lambda: asyncio.create_task(manager.broadcast({
                        'type': 'refresh_preview',
                        'data': {
                            'task_type': 'audio',
                            'task_id': task_id
                        }
                    }))
                )
                logger.info(f"[音频生成] 已发送刷新预览通知")
            except Exception as e:
                logger.error(f"发送刷新预览通知失败: {e}")
        
    except Exception as e:
        logger.error(f"音频生成任务失败: {e}")
        task_manager.update_task(task_id, status='failed', error=str(e))


# ==================== WebSocket端点 ====================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket连接端点"""
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            message_type = data.get('type')
            
            if message_type == 'join_task':
                task_id = data.get('task_id')
                if task_id:
                    await manager.connect(websocket, task_id)
                    await manager.send_personal_message({
                        'type': 'joined_task',
                        'task_id': task_id
                    }, websocket)
            
            elif message_type == 'leave_task':
                task_id = data.get('task_id')
                if task_id:
                    manager.disconnect(websocket, task_id)
                    await manager.send_personal_message({
                        'type': 'left_task',
                        'task_id': task_id
                    }, websocket)
            
            elif message_type == 'ping':
                await manager.send_personal_message({'type': 'pong'}, websocket)
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ==================== 预览文件服务 ====================

@app.get("/api/preview/{filename}")
async def get_preview(filename: str):
    """获取预览文件"""
    try:
        # 解码文件名（处理URL编码）
        import urllib.parse
        decoded_filename = urllib.parse.unquote(filename)
        file_path = os.path.join(OUTPUT_FOLDER, decoded_filename)
        abs_file_path = os.path.abspath(file_path)
        abs_output_folder = os.path.abspath(OUTPUT_FOLDER)
        
        logger.info(f"[预览API] ========== 请求预览文件 ==========")
        logger.info(f"[预览API] 原始文件名参数: {repr(filename)}")
        logger.info(f"[预览API] 解码后文件名: {repr(decoded_filename)}")
        logger.info(f"[预览API] 输出目录: {OUTPUT_FOLDER}")
        logger.info(f"[预览API] 输出目录绝对路径: {abs_output_folder}")
        logger.info(f"[预览API] 输出目录存在: {os.path.exists(OUTPUT_FOLDER)}")
        logger.info(f"[预览API] 拼接的文件路径: {file_path}")
        logger.info(f"[预览API] 文件绝对路径: {abs_file_path}")
        logger.info(f"[预览API] 文件存在: {os.path.exists(file_path)}")
        
        if os.path.exists(file_path):
            file_size = os.path.getsize(file_path)
            logger.info(f"[预览API] ✓ 文件存在，大小: {file_size} bytes")
        else:
            logger.warning(f"[预览API] ✗ 预览文件不存在: {abs_file_path}")
            # 列出输出目录中的文件（用于调试）
            if os.path.exists(OUTPUT_FOLDER):
                all_files = os.listdir(OUTPUT_FOLDER)
                logger.info(f"[预览API] 输出目录总文件数: {len(all_files)}")
                
                # 查找相似文件
                shot_prefix = decoded_filename.split('_')[0] if '_' in decoded_filename else decoded_filename.split('.')[0]
                similar_files = [f for f in all_files if shot_prefix in f]
                logger.info(f"[预览API] 包含 '{shot_prefix}' 的文件数: {len(similar_files)}")
                logger.info(f"[预览API] 相似文件列表:")
                for f in similar_files[:20]:  # 显示前20个
                    full_path = os.path.join(OUTPUT_FOLDER, f)
                    exists = os.path.exists(full_path)
                    size = os.path.getsize(full_path) if exists else 0
                    logger.info(f"[预览API]   - {f} (存在: {exists}, 大小: {size} bytes)")
                
                # 尝试直接匹配文件名（不区分大小写）
                matching_files = [f for f in all_files if f.lower() == decoded_filename.lower()]
                if matching_files:
                    logger.info(f"[预览API] 找到大小写不同的匹配文件: {matching_files}")
            else:
                logger.error(f"[预览API] 输出目录不存在: {abs_output_folder}")
            
            raise HTTPException(status_code=404, detail=f"文件不存在: {decoded_filename}")
        
        # 检查文件类型
        ext = os.path.splitext(decoded_filename)[1].lower()
        media_type = None
        
        if ext in ['.png', '.jpg', '.jpeg', '.webp']:
            media_type = f"image/{ext[1:]}" if ext != '.jpg' else "image/jpeg"
        elif ext in ['.mp4', '.webm']:
            media_type = f"video/{ext[1:]}"
        
        logger.info(f"返回预览文件: {file_path}, 媒体类型: {media_type}")
        
        from fastapi.responses import FileResponse
        preview_headers = {"Cache-Control": "no-cache, max-age=0"}
        if media_type:
            return FileResponse(file_path, media_type=media_type, headers=preview_headers)
        else:
            return FileResponse(file_path, headers=preview_headers)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取预览文件失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 静态文件服务 ====================

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    """主页面"""
    with open(os.path.join("templates", "index.html"), "r", encoding="utf-8") as f:
        content = f.read()
        # 添加缓存控制头，确保浏览器获取最新版本
        return HTMLResponse(
            content=content,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )


# ==================== 主函数 ====================

@app.on_event("startup")
async def startup_event():
    """启动时设置全局事件循环"""
    set_event_loop(asyncio.get_event_loop())
    logger.info("服务器启动完成，用户数据已加载")


if __name__ == '__main__':
    import uvicorn
    import sys
    
    # 检查端口是否被占用
    port = 5000
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            logger.warning(f"无效的端口号: {sys.argv[1]}，使用默认端口5000")
    
    # 检查端口是否可用
    import socket
    import time
    
    # 尝试多次检查端口（可能有延迟）
    port_available = False
    for attempt in range(3):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        try:
            result = sock.connect_ex(('127.0.0.1', port))
            sock.close()
            if result != 0:  # 连接失败说明端口可用
                port_available = True
                break
        except:
            pass
        finally:
            try:
                sock.close()
            except:
                pass
        
        if attempt < 2:
            time.sleep(0.5)
    
    if not port_available:
        # 尝试强制停止占用端口的进程
        import subprocess
        try:
            result = subprocess.run(['lsof', '-ti', f':{port}'], 
                                   capture_output=True, text=True, timeout=2)
            if result.returncode == 0 and result.stdout.strip():
                pids = result.stdout.strip().split('\n')
                logger.warning(f"发现占用端口 {port} 的进程: {pids}")
                logger.info("尝试停止这些进程...")
                for pid in pids:
                    try:
                        subprocess.run(['kill', '-9', pid], timeout=1)
                        logger.info(f"已停止进程 {pid}")
                    except:
                        pass
                time.sleep(1)
                # 再次检查
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex(('127.0.0.1', port))
                sock.close()
                if result != 0:
                    port_available = True
        except Exception as e:
            logger.debug(f"检查端口占用进程时出错: {e}")
    
    if not port_available:
        logger.error(f"端口 {port} 已被占用！")
        logger.info("请执行以下命令之一：")
        logger.info(f"  1. 杀掉占用端口的进程: lsof -ti:{port} | xargs kill -9")
        logger.info(f"  2. 使用其他端口: python server.py <端口号>")
        logger.info(f"  3. 查找占用进程: lsof -i :{port}")
        sys.exit(1)
    
    logger.info(f"端口 {port} 可用")
    
    logger.info("启动UICS服务器 (FastAPI)...")
    logger.info(f"Excel文件路径: {EXCEL_FILE}")
    logger.info(f"输出目录: {OUTPUT_FOLDER}")
    logger.info(f"监听端口: {port}")
    
    uvicorn.run(app, host='0.0.0.0', port=port, log_level="info")
