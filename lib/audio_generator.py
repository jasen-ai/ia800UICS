# Copyright (c) 2026 jasen chen. All rights reserved.
#
# Licensed under the MIT License (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://opensource.org/licenses/MIT
#
# Project Repository: https://github.com/jasen-ai/ia800UICS
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
音频生成器模块 - 用于根据Excel数据批量生成音频
支持多种生成方式，方便后续扩展
"""
import os
import json
import logging
import uuid
import asyncio
import concurrent.futures
from typing import Dict, List, Optional, Any
from abc import ABC, abstractmethod
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AudioGeneratorBase(ABC):
    """音频生成器基类，定义统一的接口"""
    
    @abstractmethod
    def generate_audio(
        self,
        text: str,
        voice_type: str,
        filename_prefix: Optional[str] = None,
        encoding: str = "wav",
        emotion: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        生成音频
        
        Args:
            text: 要转换的文本
            voice_type: 语音类型/角色
            filename_prefix: 文件名前缀（可选）
            encoding: 音频编码格式（默认: wav）
            emotion: 音色情感（可选）
            **kwargs: 其他参数
            
        Returns:
            生成结果字典，包含 'audio_file' 键（音频文件路径）和 'audio_data' 键（音频字节数据）
        """
        pass
    
    @abstractmethod
    def get_audio(self, filename: str) -> bytes:
        """
        获取生成的音频数据
        
        Args:
            filename: 音频文件名或路径
            
        Returns:
            音频字节数据
        """
        pass
    
    @abstractmethod
    def connect(self):
        """连接音频生成服务"""
        pass
    
    @abstractmethod
    def disconnect(self):
        """断开连接"""
        pass


class VolcengineAudioGenerator(AudioGeneratorBase):
    """基于火山引擎的音频生成器（使用WebSocket协议）"""
    
    def __init__(
        self,
        appid: str,
        access_token: str,
        endpoint: str = "wss://openspeech.bytedance.com/api/v1/tts/ws_binary",
        output_dir: str = "./output"
    ):
        """
        初始化火山引擎音频生成器
        
        Args:
            appid: 应用ID
            access_token: 访问令牌
            endpoint: WebSocket端点URL
            output_dir: 输出目录
        """
        self.appid = appid
        self.access_token = access_token
        self.endpoint = endpoint
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        
        # WebSocket连接（异步）
        self.websocket = None
        self._connected = False
        
        # 导入volcengine协议
        try:
            import sys
            volcengine_path = Path(__file__).parent / "volcengine" / "protocols"
            if str(volcengine_path) not in sys.path:
                sys.path.insert(0, str(volcengine_path.parent.parent))
            
            from volcengine.protocols import (
                MsgType,
                full_client_request,
                receive_message
            )
            self.MsgType = MsgType
            self.full_client_request = full_client_request
            self.receive_message = receive_message
            self._available = True
        except ImportError as e:
            logger.error(f"无法导入volcengine协议: {e}")
            self._available = False
            self.MsgType = None
            self.full_client_request = None
            self.receive_message = None
    
    def _get_cluster(self, voice_type: str) -> str:
        """根据语音类型确定集群"""
        if voice_type.startswith("S_"):
            return "volcano_icl"
        return "volcano_tts"
    
    async def _async_connect(self):
        """异步连接WebSocket"""
        if not self._available:
            raise ImportError("volcengine协议不可用")
        
        import websockets
        
        headers = {
            "Authorization": f"Bearer;{self.access_token}",
        }
        
        logger.info(f"连接到 {self.endpoint}")
        
        # 兼容不同版本的 websockets 库
        connect_kwargs = {
            "max_size": 10 * 1024 * 1024
        }
        
        # 尝试使用 extra_headers (新版本 websockets >= 10.0)
        try:
            connect_kwargs["extra_headers"] = headers
            self.websocket = await websockets.connect(self.endpoint, **connect_kwargs)
        except TypeError:
            # 回退到 additional_headers (旧版本 websockets < 10.0)
            try:
                connect_kwargs.pop("extra_headers", None)
                connect_kwargs["additional_headers"] = headers
                self.websocket = await websockets.connect(self.endpoint, **connect_kwargs)
            except TypeError as e:
                raise RuntimeError(
                    f"websockets 库版本不兼容。请升级到 >= 10.0 版本：\n"
                    f"pip install --upgrade websockets\n"
                    f"错误详情: {e}"
                )
        
        self._connected = True
        
        # 尝试获取 logid
        try:
            logid = self.websocket.response.headers.get('x-tt-logid', 'N/A')
            logger.info(f"WebSocket连接成功, Logid: {logid}")
        except AttributeError:
            logger.info("WebSocket连接成功")
            
        return self.websocket

    async def _async_disconnect(self):
        """异步断开连接"""
        if self.websocket:
            try:
                await self.websocket.close()
            except Exception as e:
                logger.warning(f"关闭WebSocket时出错: {e}")
            finally:
                self.websocket = None
                self._connected = False
                logger.info("WebSocket连接已关闭")
    
    async def _async_generate_audio(
        self,
        text: str,
        voice_type: str,
        filename_prefix: Optional[str] = None,
        encoding: str = "wav",
        emotion: Optional[str] = None
    ) -> Dict[str, Any]:
        """异步生成音频（包含自动降级重试机制）"""
        
        async def _do_request(use_emotion: bool):
            """执行单次请求"""
            if not self._available:
                raise ImportError("volcengine协议不可用")
            
            # 强制每次重新连接
            await self._async_connect()
            
            try:
                # 确定集群
                cluster = self._get_cluster(voice_type)
                
                # 构建audio对象
                audio_config = {
                    "voice_type": voice_type,
                    "encoding": encoding,
                }
                # 如果提供了emotion参数且use_emotion为True，添加到audio配置中
                if emotion and use_emotion:
                    audio_config["emotion"] = emotion
                
                # 准备请求负载
                request = {
                    "app": {
                        "appid": self.appid,
                        "token": self.access_token,
                        "cluster": cluster,
                    },
                    "user": {
                        "uid": str(uuid.uuid4()),
                    },
                    "audio": audio_config,
                    "request": {
                        "reqid": str(uuid.uuid4()),
                        "text": text,
                        "operation": "submit",
                        "with_timestamp": "1",
                        "extra_param": json.dumps({
                            "disable_markdown_filter": False,
                        }),
                    },
                }
                
                # 发送请求
                await self.full_client_request(self.websocket, json.dumps(request).encode())
                
                # 接收音频数据
                audio_data = bytearray()
                while True:
                    msg = await self.receive_message(self.websocket)
                    
                    if msg.type == self.MsgType.FrontEndResultServer:
                        continue
                    elif msg.type == self.MsgType.AudioOnlyServer:
                        audio_data.extend(msg.payload)
                        if msg.sequence < 0:  # 最后一条消息
                            break
                    elif msg.type == self.MsgType.Error:
                        # 解析错误信息
                        try:
                            error_payload = json.loads(msg.payload.decode('utf-8'))
                            error_msg = error_payload.get('error', 'Unknown error')
                            error_code = msg.error_code
                            raise RuntimeError(f"TTS转换失败 (Code: {error_code}): {error_msg}")
                        except Exception as e:
                            # 如果已经是RuntimeError，直接抛出
                            if isinstance(e, RuntimeError):
                                raise e
                            raise RuntimeError(f"TTS转换失败: {msg}")
                    else:
                        raise RuntimeError(f"TTS转换失败: {msg}")
                
                # 检查是否收到音频数据
                if not audio_data:
                    raise RuntimeError("未收到音频数据")
                
                return audio_data
                
            finally:
                # 无论成功失败，都关闭连接
                await self._async_disconnect()

        # 第一次尝试：带情感参数（如果提供了）
        try:
            audio_data = await _do_request(use_emotion=True)
        except RuntimeError as e:
            # 如果是特定的错误代码（如3031），且使用了情感参数，尝试降级
            error_str = str(e)
            if emotion and ("Code: 3031" in error_str or "Init Engine Instance failed" in error_str):
                logger.warning(f"带情感参数 '{emotion}' 生成失败，尝试使用默认情感重试...")
                try:
                    audio_data = await _do_request(use_emotion=False)
                    logger.info("使用默认情感重试成功")
                except Exception as retry_e:
                    # 重试也失败，抛出原始异常或重试异常
                    logger.error(f"重试失败: {retry_e}")
                    raise e
            else:
                raise e
        
        # 生成文件名
        if filename_prefix:
            filename = f"{filename_prefix}.{encoding}"
        else:
            filename = f"{voice_type}_{uuid.uuid4().hex[:8]}.{encoding}"
        
        # 保存音频文件
        output_path = os.path.join(self.output_dir, filename)
        with open(output_path, "wb") as f:
            f.write(audio_data)
        
        logger.info(f"音频生成成功: {len(audio_data)} 字节, 保存到 {output_path}")
        
        return {
            "audio_file": output_path,
            "audio_data": bytes(audio_data),
            "filename": filename,
            "size": len(audio_data)
        }
    
    def _run_async(self, coro):
        """运行异步协程（兼容已有事件循环）"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果事件循环正在运行，使用线程池执行
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, coro)
                    return future.result()
            else:
                return loop.run_until_complete(coro)
        except RuntimeError:
            # 没有事件循环，直接运行
            return asyncio.run(coro)
    
    def connect(self):
        """连接音频生成服务（同步包装）"""
        # 在 _run_async (asyncio.run) 模式下，预先连接没有意义，
        # 因为每次 run 都会创建新的事件循环，导致旧的连接失效。
        # 这里仅保留接口兼容性。
        pass
    
    def disconnect(self):
        """断开连接（同步包装）"""
        pass
    
    def generate_audio(
        self,
        text: str,
        voice_type: str,
        filename_prefix: Optional[str] = None,
        encoding: str = "wav",
        emotion: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """生成音频（同步包装）"""
        return self._run_async(self._async_generate_audio(
            text=text,
            voice_type=voice_type,
            filename_prefix=filename_prefix,
            encoding=encoding,
            emotion=emotion
        ))
    
    def get_audio(self, filename: str) -> bytes:
        """获取生成的音频数据"""
        # 如果filename是完整路径，直接读取
        if os.path.isabs(filename) or os.path.exists(filename):
            filepath = filename
        else:
            # 否则在输出目录中查找
            filepath = os.path.join(self.output_dir, filename)
        
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"音频文件不存在: {filepath}")
        
        with open(filepath, "rb") as f:
            return f.read()


class ComfyUIAudioGenerator(AudioGeneratorBase):
    """基于ComfyUI的音频生成器（使用Qwen3-TTS语音克隆）"""
    
    def __init__(
        self,
        server_address: str = "127.0.0.1:8188",
        workflow_path: str = "Qwen3-TTSVoiceCloneAPI.json",
        output_dir: str = "./output"
    ):
        """
        初始化ComfyUI音频生成器
        
        Args:
            server_address: ComfyUI服务器地址，格式为 "host:port"
            workflow_path: 工作流JSON文件路径
            output_dir: 输出目录
        """
        self.server_address = server_address
        self.workflow_path = workflow_path
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        
        # 导入Qwen3TTSClient
        try:
            from qwen3_tts_client import Qwen3TTSClient
            self.Qwen3TTSClient = Qwen3TTSClient
            self.client = Qwen3TTSClient(
                server_address=server_address,
                workflow_path=workflow_path,
                output_dir=output_dir
            )
            self._available = True
            logger.info(f"ComfyUI音频生成器初始化成功，服务器: {server_address}")
        except ImportError:
            self.client = None
            self._available = False
            logger.error("Qwen3TTSClient不可用，请确保qwen3_tts_client.py存在")
        except Exception as e:
            self.client = None
            self._available = False
            logger.error(f"初始化ComfyUI音频生成器失败: {e}")
    
    def connect(self):
        """连接ComfyUI服务器"""
        if not self._available:
            raise ImportError("Qwen3TTSClient不可用")
        if self.client:
            self.client.connect()
            logger.debug("ComfyUI客户端已连接")
    
    def disconnect(self):
        """断开连接"""
        if self.client:
            self.client.disconnect()
            logger.debug("ComfyUI客户端已断开")
    
    def generate_audio(
        self,
        text: str,
        voice_type: str,
        filename_prefix: Optional[str] = None,
        encoding: str = "wav",
        emotion: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        生成音频
        
        Args:
            text: 要转换的文本
            voice_type: 语音类型/角色（对于ComfyUI，这是参考音频文件路径）
            filename_prefix: 文件名前缀（可选）
            encoding: 音频编码格式（默认: wav，ComfyUI可能返回其他格式）
            emotion: 音色情感（可选，ComfyUI不支持）
            **kwargs: 其他参数
                - ref_audio_path: 参考音频文件路径（如果voice_type不是文件路径）
                - target_language: 目标语言（默认: "Chinese"）
                - seed: 随机种子（可选）
                - temperature: 温度参数（默认: 0.9）
                - top_p: Top-p采样参数（默认: 1.0）
                - top_k: Top-k采样参数（默认: 50）
                - repetition_penalty: 重复惩罚（默认: 1.05）
                - max_new_tokens: 最大生成token数（默认: 2048）
                - output_mode: 输出模式（默认: "Concatenate (Merge)"）
                - ref_text: 参考文本（可选）
                - instruct: 指令文本（可选）
        
        Returns:
            生成结果字典，包含 'audio_file' 键（音频文件路径）和 'audio_data' 键（音频字节数据）
        """
        if not self._available:
            raise ImportError("Qwen3TTSClient不可用")
        
        # 确定参考音频路径
        ref_audio_path = kwargs.get('ref_audio_path') or voice_type
        
        # 处理路径查找逻辑
        if not os.path.exists(ref_audio_path):
            # 参考音频目录固定为「原 input」：若本模块在 lib 下（如 UICS/lib），则用上一级目录的 input（UICS/input）
            project_root = os.path.dirname(os.path.abspath(__file__))
            if os.path.basename(project_root) == "lib":
                project_root = os.path.dirname(project_root)
            input_dir = os.path.join(project_root, "input")
            
            # 如果路径以 input/ 开头，提取文件名
            if ref_audio_path.startswith("input/"):
                filename = ref_audio_path[6:]  # 移除 "input/" 前缀
                possible_path = os.path.join(input_dir, filename)
            else:
                # 否则尝试在input目录中查找
                possible_path = os.path.join(input_dir, ref_audio_path)
            
            if os.path.exists(possible_path):
                ref_audio_path = possible_path
                logger.debug(f"找到参考音频文件: {ref_audio_path}")
            else:
                # 尝试作为绝对路径
                if os.path.isabs(ref_audio_path) and os.path.exists(ref_audio_path):
                    pass  # 已经是绝对路径且存在
                else:
                    # 列出尝试过的路径，帮助用户调试
                    tried_paths = [
                        ref_audio_path,
                        possible_path,
                        os.path.join(project_root, ref_audio_path)
                    ]
                    
                    # 检查input目录中是否有类似的文件（帮助用户发现拼写错误）
                    similar_files = []
                    if os.path.exists(input_dir):
                        try:
                            import fnmatch
                            ref_filename = os.path.basename(ref_audio_path).lower()
                            for file in os.listdir(input_dir):
                                file_lower = file.lower()
                                # 检查文件名是否相似（包含部分匹配）
                                if (ref_filename in file_lower or 
                                    file_lower in ref_filename or
                                    any(c in file_lower for c in ref_filename if len(ref_filename) > 3)):
                                    similar_files.append(file)
                        except Exception:
                            pass
                    
                    error_msg = (
                        f"参考音频文件不存在: {ref_audio_path}\n"
                        f"已尝试以下路径:\n"
                        + "\n".join(f"  - {path}" for path in tried_paths) + "\n"
                        f"项目根目录: {project_root}\n"
                        f"input目录: {input_dir}"
                    )
                    
                    if similar_files:
                        error_msg += (
                            f"\n\n提示: 在input目录中找到了以下相似的文件名，请检查是否拼写错误:\n"
                            + "\n".join(f"  - {f}" for f in similar_files[:5])
                        )
                    
                    error_msg += "\n请确保文件存在，或使用绝对路径指定完整路径"
                    
                    raise FileNotFoundError(error_msg)
        
        # 获取其他参数
        target_language = kwargs.get('target_language', 'Chinese')
        seed = kwargs.get('seed')
        temperature = kwargs.get('temperature', 0.9)
        top_p = kwargs.get('top_p', 1.0)
        top_k = kwargs.get('top_k', 50)
        repetition_penalty = kwargs.get('repetition_penalty', 1.05)
        max_new_tokens = kwargs.get('max_new_tokens', 2048)
        output_mode = kwargs.get('output_mode', 'Concatenate (Merge)')
        ref_text = kwargs.get('ref_text')
        instruct = kwargs.get('instruct')
        
        logger.info(f"使用ComfyUI生成音频: {text[:50]}...")
        logger.debug(f"  参考音频: {ref_audio_path}")
        logger.debug(f"  目标语言: {target_language}")
        
        # 连接服务器（如果需要）
        try:
            if not hasattr(self.client.client, 'is_running') or not self.client.client.is_running:
                self.connect()
        except AttributeError:
            # 如果is_running属性不存在，直接连接
            self.connect()
        
        # 生成音频
        result = self.client.generate_audio(
            ref_audio_path=ref_audio_path,
            target_text=text,
            target_language=target_language,
            seed=seed,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            repetition_penalty=repetition_penalty,
            max_new_tokens=max_new_tokens,
            output_mode=output_mode,
            filename_prefix=filename_prefix,
            ref_text=ref_text,
            instruct=instruct,
            wait=True
        )
        
        # 处理结果
        if result.get('audio_file'):
            audio_file = result['audio_file']
            # 读取音频数据
            with open(audio_file, 'rb') as f:
                audio_data = f.read()
            
            return {
                "audio_file": audio_file,
                "audio_data": audio_data,
                "filename": os.path.basename(audio_file),
                "size": len(audio_data)
            }
        else:
            raise RuntimeError("ComfyUI未返回音频文件")
    
    def get_audio(self, filename: str) -> bytes:
        """获取生成的音频数据"""
        # 如果filename是完整路径，直接读取
        if os.path.isabs(filename) or os.path.exists(filename):
            filepath = filename
        else:
            # 否则在输出目录中查找
            filepath = os.path.join(self.output_dir, filename)
        
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"音频文件不存在: {filepath}")
        
        with open(filepath, "rb") as f:
            return f.read()


class BatchAudioGenerator:
    """批量音频生成器"""
    
    def __init__(
        self,
        generator: AudioGeneratorBase,
        output_dir: str = "./output"
    ):
        """
        初始化批量音频生成器
        
        Args:
            generator: 音频生成器实例
            output_dir: 输出目录
        """
        self.generator = generator
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
    
    def generate_from_audio_tracks(
        self,
        audio_tracks: List[Any],  # List[AudioTrack]
        encoding: str = "wav",
        episode_filter: Optional[str] = None,
        shot_filter: Optional[str] = None,
        characters: Optional[List[Any]] = None,  # List[Character]
        emotion: Optional[str] = None,
        emotion_map: Optional[Dict[str, str]] = None
    ) -> List[Dict[str, Any]]:
        """
        根据音频轨道列表批量生成音频
        
        Args:
            audio_tracks: 音频轨道列表（AudioTrack对象列表）
            encoding: 音频编码格式（默认: wav）
            episode_filter: 剧集ID过滤器（可选，只生成指定剧集的音频）
            shot_filter: 分镜号过滤器（可选，只生成指定分镜的音频）
            characters: 角色列表（可选，用于查找角色的音频id）
            emotion: 默认音色情感（可选，如果track中没有指定emotion则使用此值）
            emotion_map: 情感映射字典（可选，key为角色名，value为对应的emotion值）
            
        Returns:
            生成结果列表，每个元素包含音频信息
        """
        results = []
        
        # 构建角色名到角色的映射（用于快速查找）
        character_map = {}
        if characters:
            for char in characters:
                if hasattr(char, '角色名') and char.角色名:
                    character_map[char.角色名] = char
        
        # 过滤音频轨道
        tracks_to_process = []
        for track in audio_tracks:
            if episode_filter and track.剧集id != episode_filter:
                continue
            if shot_filter and track.分镜号 != shot_filter:
                continue
            tracks_to_process.append(track)
        
        if not tracks_to_process:
            logger.warning("没有找到符合条件的音频轨道")
            return results
        
        logger.info(f"过滤后找到 {len(tracks_to_process)} 个音频轨道")
        
        # 连接生成器
        self.generator.connect()
        
        try:
            for i, track in enumerate(tracks_to_process, 1):
                # 检查必要字段
                if not track.音频id or not track.音频内容:
                    logger.warning(f"跳过音频生成 [{i}/{len(tracks_to_process)}]: {track.分镜号} - 缺少音频ID或内容")
                    continue
                
                # 确定语音类型（根据生成器类型不同处理）
                voice_type = None
                character_name = track.音频角色 or track.剧情角色
                
                # 检查生成器类型
                is_comfyui = isinstance(self.generator, ComfyUIAudioGenerator)
                
                if is_comfyui:
                    # ComfyUI模式：voice_type应该是参考音频文件路径
                    # 优先使用角色的参考音色，其次使用参考样本，最后使用角色名
                    if character_name and character_map and character_name in character_map:
                        char = character_map[character_name]
                        # 检查角色的参考音色字段（用于音频生成）
                        if hasattr(char, '参考音色') and char.参考音色:
                            voice_type = char.参考音色
                            logger.debug(f"  使用角色 {character_name} 的参考音色: {voice_type}")
                        elif hasattr(char, '参考图') and char.参考图:
                            # 向后兼容：如果参考音色不存在，尝试使用参考图
                            voice_type = char.参考图
                            logger.debug(f"  使用角色 {character_name} 的参考图（向后兼容）: {voice_type}")
                        elif hasattr(track, '参考样本') and track.参考样本:
                            voice_type = track.参考样本
                            logger.debug(f"  使用音频轨道的参考样本: {voice_type}")
                        else:
                            # 尝试使用角色名作为文件名查找
                            voice_type = character_name
                            logger.warning(f"  角色 {character_name} 没有参考音色，尝试使用角色名: {voice_type}")
                    elif hasattr(track, '参考样本') and track.参考样本:
                        voice_type = track.参考样本
                        logger.debug(f"  使用音频轨道的参考样本: {voice_type}")
                    elif character_name:
                        voice_type = character_name
                        logger.warning(f"  使用角色名作为参考音频: {voice_type}")
                    else:
                        raise ValueError(f"ComfyUI模式需要参考音频文件，但分镜 {track.分镜号} 没有提供参考音频路径")
                else:
                    # Volcengine模式：voice_type是语音ID
                    if character_name and character_map and character_name in character_map:
                        # 从角色汇总表中查找角色的音频id
                        char = character_map[character_name]
                        if hasattr(char, '音频id') and char.音频id:
                            voice_type = char.音频id
                            logger.debug(f"  使用角色 {character_name} 的音频id: {voice_type}")
                        else:
                            logger.warning(f"  角色 {character_name} 没有音频id，使用角色名作为voice_type")
                            voice_type = character_name
                    elif character_name:
                        # 如果角色不在角色汇总表中，直接使用角色名
                        voice_type = character_name
                    else:
                        voice_type = "default"
                
                # 确定emotion（仅volcengine支持，ComfyUI不支持）
                track_emotion = None
                if not is_comfyui:
                    # 优先级：track.音频情感 > emotion_map > 默认emotion
                    if hasattr(track, '音频情感') and track.音频情感:
                        track_emotion = track.音频情感
                    elif emotion_map and voice_type in emotion_map:
                        track_emotion = emotion_map[voice_type]
                    else:
                        track_emotion = emotion
                
                logger.info(f"生成音频 [{i}/{len(tracks_to_process)}]: {track.音频id}")
                logger.debug(f"  内容: {track.音频内容[:50]}...")
                logger.debug(f"  角色: {character_name or 'N/A'}")
                logger.debug(f"  语音类型: {voice_type}")
                if track_emotion and not is_comfyui:
                    logger.info(f"  使用情感: {track_emotion}")
                logger.debug(f"  分镜号: {track.分镜号}")
                
                # 增加重试机制
                max_retries = 3
                retry_delay = 2  # 初始重试延迟（秒）
                
                for attempt in range(max_retries):
                    try:
                        # 生成音频
                        generate_kwargs = {
                            "text": track.音频内容,
                            "voice_type": voice_type,
                            "filename_prefix": track.音频id,
                            "encoding": encoding
                        }
                        
                        # 仅volcengine支持emotion参数
                        if not is_comfyui and track_emotion:
                            generate_kwargs["emotion"] = track_emotion
                        
                        # ComfyUI需要ref_audio_path参数
                        if is_comfyui:
                            generate_kwargs["ref_audio_path"] = voice_type
                        
                        result = self.generator.generate_audio(**generate_kwargs)
                        
                        # 添加额外信息
                        result["track"] = track
                        result["shot_id"] = track.分镜号
                        result["episode_id"] = track.剧集id
                        
                        result["success"] = True
                        results.append(result)
                        logger.info(f"✓ 音频生成成功: {result['filename']}")
                        break  # 成功则跳出重试循环
                        
                    except Exception as e:
                        if attempt < max_retries - 1:
                            wait_time = retry_delay * (2 ** attempt)  # 指数退避
                            logger.warning(f"音频生成失败，正在重试 ({attempt + 1}/{max_retries})，等待 {wait_time} 秒... 错误: {e}")
                            import time
                            time.sleep(wait_time)
                        else:
                            logger.error(f"✗ 音频生成失败 [{i}/{len(tracks_to_process)}]: {track.音频id} - {e}")
                            results.append({
                                "track": track,
                                "shot_id": track.分镜号,
                                "episode_id": track.剧集id,
                                "error": str(e),
                                "success": False
                            })
                
                # 批次间增加短暂延时，避免请求过快
                import time
                time.sleep(0.5)
                
        finally:
            # 断开连接（实际上在 generate_audio 内部已经断开，这里为了保险）
            self.generator.disconnect()
        
        successful = sum(1 for r in results if r.get('success', True) and 'error' not in r)
        logger.info(f"批量音频生成完成: {successful}/{len(tracks_to_process)} 成功")
        return results


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """
    加载配置文件
    
    Args:
        config_path: 配置文件路径（可选）。如果为None，尝试从默认位置加载
        
    Returns:
        配置字典
    """
    # 默认配置文件路径
    default_config_paths = [
        os.path.join(os.path.dirname(__file__), "audio_generator_config.json"),
        os.path.join(os.path.expanduser("~"), ".audio_generator_config.json"),
        "audio_generator_config.json"
    ]
    
    # 如果指定了配置文件路径，优先使用
    if config_path:
        config_paths = [config_path] + default_config_paths
    else:
        config_paths = default_config_paths
    
    # 尝试加载配置文件
    for path in config_paths:
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    logger.info(f"已加载配置文件: {path}")
                    return config
            except Exception as e:
                logger.warning(f"无法读取配置文件 {path}: {e}")
                continue
    
    # 如果所有配置文件都不存在，返回空字典
    return {}


def get_config_value(
    key: str,
    value: Optional[str] = None,
    config_path: Optional[str] = None,
    possible_keys: Optional[List[str]] = None
) -> Optional[str]:
    """
    获取配置值（优先使用参数，其次从配置文件读取）
    
    Args:
        key: 配置键名
        value: 直接提供的值（可选）
        config_path: 配置文件路径（可选）
        possible_keys: 可能的键名列表（用于兼容不同的命名方式）
        
    Returns:
        配置值，如果找不到返回None
    """
    # 如果直接提供了值，优先使用
    if value:
        return value
    
    # 尝试从配置文件读取
    config = load_config(config_path)
    
    # 构建可能的键名列表
    if possible_keys is None:
        possible_keys = [
            key,
            key.lower(),
            key.upper(),
            key.replace('_', ''),
            key.replace('_', '-')
        ]
    
    # 尝试多个可能的键名
    for k in possible_keys:
        if k in config:
            return config[k]
    
    # 如果都找不到，返回None
    return None


def create_audio_generator(
    generator_type: str = "volcengine",
    config_path: Optional[str] = None,
    **kwargs
) -> AudioGeneratorBase:
    """
    创建音频生成器实例
    
    Args:
        generator_type: 生成器类型（"volcengine" 或 "comfyui"）
        config_path: 配置文件路径（可选）
        **kwargs: 生成器特定参数（优先级高于配置文件）
            - 对于volcengine: appid, access_token, endpoint
            - 对于comfyui: server_address, workflow_path
        
    Returns:
        音频生成器实例
    """
    generator_type_lower = generator_type.lower()
    
    if generator_type_lower == "volcengine":
        # 优先使用kwargs中的值，其次从配置文件读取
        appid = kwargs.get("appid") or get_config_value(
            "appid",
            config_path=config_path,
            possible_keys=["appid", "app_id", "APPID", "APP_ID"]
        )
        access_token = kwargs.get("access_token") or get_config_value(
            "access_token",
            config_path=config_path,
            possible_keys=["access_token", "accessToken", "ACCESS_TOKEN", "token", "TOKEN"]
        )
        endpoint = kwargs.get("endpoint") or get_config_value(
            "endpoint",
            config_path=config_path,
            possible_keys=["endpoint", "ENDPOINT", "ws_endpoint", "wsEndpoint"]
        ) or "wss://openspeech.bytedance.com/api/v1/tts/ws_binary"
        output_dir = kwargs.get("output_dir", "./output")
        
        if not appid or not access_token:
            raise ValueError(
                "volcengine生成器需要appid和access_token参数。\n"
                "请使用以下方式之一提供：\n"
                "1. 使用 --appid 和 --access_token 参数\n"
                "2. 在配置文件中设置 appid 和 access_token 字段\n"
                f"   配置文件路径: {os.path.join(os.path.dirname(__file__), 'audio_generator_config.json')}\n"
                "   配置文件格式: {\"appid\": \"YOUR_APPID\", \"access_token\": \"YOUR_ACCESS_TOKEN\"}"
            )
        
        return VolcengineAudioGenerator(
            appid=appid,
            access_token=access_token,
            endpoint=endpoint,
            output_dir=output_dir
        )
    elif generator_type_lower == "comfyui":
        # 优先使用kwargs中的值，其次从配置文件读取
        server_address = kwargs.get("server_address") or kwargs.get("comfyui_server") or get_config_value(
            "server_address",
            config_path=config_path,
            possible_keys=["server_address", "serverAddress", "SERVER_ADDRESS", "comfyui_server", "comfyuiServer"]
        ) or "127.0.0.1:8188"
        
        workflow_path = kwargs.get("workflow_path") or get_config_value(
            "workflow_path",
            config_path=config_path,
            possible_keys=["workflow_path", "workflowPath", "WORKFLOW_PATH"]
        ) or "Qwen3-TTSVoiceCloneAPI.json"
        
        # 如果workflow_path是相对路径，尝试在项目根目录查找
        if not os.path.isabs(workflow_path) and not os.path.exists(workflow_path):
            project_root = os.path.dirname(__file__)
            possible_path = os.path.join(project_root, workflow_path)
            if os.path.exists(possible_path):
                workflow_path = possible_path
        
        output_dir = kwargs.get("output_dir", "./output")
        
        return ComfyUIAudioGenerator(
            server_address=server_address,
            workflow_path=workflow_path,
            output_dir=output_dir
        )
    else:
        raise ValueError(f"不支持的生成器类型: {generator_type}，支持的类型: volcengine, comfyui")


def batch_generate_audio_from_excel_data(
    audio_tracks: List[Any],  # List[AudioTrack]
    characters: Optional[List[Any]] = None,  # List[Character]
    generator_type: str = "volcengine",
    output_dir: str = "./output",
    encoding: str = "wav",
    episode_filter: Optional[str] = None,
    shot_filter: Optional[str] = None,
    config_path: Optional[str] = None,
    emotion: Optional[str] = None,
    emotion_map: Optional[Dict[str, str]] = None,
    provider_profile: Optional[str] = None,
    **generator_kwargs
) -> List[Dict[str, Any]]:
    """
    从Excel数据批量生成音频
    
    Args:
        audio_tracks: 音频轨道列表（AudioTrack对象列表）
        characters: 角色列表（可选，用于查找角色的音频id）
        generator_type: 生成器类型（"volcengine" 或 "comfyui"）
        provider_profile: 可选，generation_framework 音频 profile_id（如 volcengine.default、comfyui.default）
        output_dir: 输出目录
        encoding: 音频编码格式
        episode_filter: 剧集ID过滤器（可选）
        shot_filter: 分镜号过滤器（可选）
        config_path: 配置文件路径（可选）
        emotion: 默认音色情感（可选，仅volcengine支持）
        emotion_map: 情感映射字典（可选，key为角色名，value为对应的emotion值，仅volcengine支持）
        **generator_kwargs: 生成器特定参数（优先级高于配置文件）
            - 对于volcengine: appid, access_token, endpoint
            - 对于comfyui: server_address, workflow_path
        
    Returns:
        生成结果列表
    """
    # 创建生成器（优先走 generation_framework）
    try:
        from generation_framework import (
            create_audio_generator_by_profile,
            resolve_audio_profile_id,
        )

        pid = resolve_audio_profile_id(provider_profile, generator_type)
        generator = create_audio_generator_by_profile(
            pid,
            comfyui_server=generator_kwargs.get("comfyui_server", generator_kwargs.get("server_address", "127.0.0.1:8188")),
            config_path=config_path,
            workflow_path=generator_kwargs.get("workflow_path"),
            output_dir=output_dir,
            **{k: v for k, v in generator_kwargs.items() if k not in ("comfyui_server", "server_address", "workflow_path")}
        )
    except ImportError:
        generator = create_audio_generator(
            generator_type=generator_type,
            config_path=config_path,
            output_dir=output_dir,
            **generator_kwargs
        )
    except ValueError as e:
        logger.warning("%s，回退 create_audio_generator", e)
        generator = create_audio_generator(
            generator_type=generator_type,
            config_path=config_path,
            output_dir=output_dir,
            **generator_kwargs
        )
    
    # 创建批量生成器
    batch_generator = BatchAudioGenerator(
        generator=generator,
        output_dir=output_dir
    )
    
    # 批量生成
    results = batch_generator.generate_from_audio_tracks(
        audio_tracks=audio_tracks,
        encoding=encoding,
        episode_filter=episode_filter,
        shot_filter=shot_filter,
        characters=characters,
        emotion=emotion,
        emotion_map=emotion_map
    )
    
    return results


if __name__ == "__main__":
    import argparse
    import sys
    
    parser = argparse.ArgumentParser(description="音频生成器客户端")
    parser.add_argument("--generator", type=str, default="volcengine", help="生成器类型")
    parser.add_argument("--config", type=str, help="配置文件路径（可选）")
    parser.add_argument("--appid", type=str, help="应用ID（volcengine需要，优先级高于配置文件）")
    parser.add_argument("--access_token", type=str, help="访问令牌（volcengine需要，优先级高于配置文件）")
    parser.add_argument("--endpoint", type=str, help="WebSocket端点URL（优先级高于配置文件）")
    parser.add_argument("--text", type=str, help="要转换的文本")
    parser.add_argument("--voice_type", type=str, help="语音类型")
    parser.add_argument("--emotion", type=str, 
                       help="音色情感（可选）。中文音色支持：happy, sad, angry, surprised, fear, hate, excited, coldness, neutral, depressed, lovey-dovey, shy, comfort, tension, tender, storytelling, radio, magnetic, advertising, vocal-fry, asmr, news, entertainment, dialect。英文音色支持：neutral, happy, angry, sad, excited, chat, asmr, warm, affectionate, authoritative")
    parser.add_argument("--encoding", type=str, default="wav", help="音频编码格式")
    parser.add_argument("--output_dir", type=str, default="./output", help="输出目录")
    parser.add_argument("--excel", type=str, help="Excel文件路径（批量生成）")
    parser.add_argument("--episode_filter", type=str, help="剧集ID过滤器")
    
    args = parser.parse_args()
    
    if args.excel:
        # 批量生成模式
        # 导入Excel读取器
        try:
            from excel_reader import ExcelDataReader
        except ImportError:
            print("错误: 无法导入ExcelDataReader，请确保excel_reader.py存在")
            sys.exit(1)
        
        # 读取Excel数据
        logger.info(f"读取Excel文件: {args.excel}")
        reader = ExcelDataReader(args.excel)
        data = reader.read_all()
        
        results = batch_generate_audio_from_excel_data(
            audio_tracks=reader.audio_tracks,
            characters=reader.characters,
            generator_type=args.generator,
            config_path=args.config,
            output_dir=args.output_dir,
            encoding=args.encoding,
            episode_filter=args.episode_filter,
            emotion=args.emotion,
            appid=args.appid,
            access_token=args.access_token,
            endpoint=args.endpoint
        )
        print(f"\n批量生成完成: {len(results)} 个音频文件")
    elif args.text and args.voice_type:
        # 单次生成模式
        generator = create_audio_generator(
            generator_type=args.generator,
            config_path=args.config,
            appid=args.appid,
            access_token=args.access_token,
            endpoint=args.endpoint,
            output_dir=args.output_dir
        )
        
        generator.connect()
        try:
            result = generator.generate_audio(
                text=args.text,
                voice_type=args.voice_type,
                encoding=args.encoding,
                emotion=args.emotion
            )
            print(f"\n音频生成成功: {result['audio_file']}")
            print(f"文件大小: {result['size']} 字节")
        finally:
            generator.disconnect()
    else:
        parser.print_help()
        print("\n错误: 请提供 --excel 或 --text 和 --voice_type 参数")
        print("\n提示: 使用 --emotion 参数指定音色情感（注意是双横线 --emotion，不是 -emotion）")
        print("示例: python audio_generator.py --text '你好' --voice_type zh_male_aojiaobazong_emo_v2_mars_bigtts --emotion excited")

