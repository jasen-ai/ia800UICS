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
视频生成器模块 - 用于根据Excel数据批量生成视频
支持提示词扩展功能
"""
import glob
import os
import logging
from typing import Dict, List, Optional, Any
from abc import ABC, abstractmethod

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class VideoGeneratorBase(ABC):
    """视频生成器基类，定义统一的接口"""
    
    @abstractmethod
    def generate_video(
        self,
        prompt: str,
        image_path: Optional[str] = None,
        filename_prefix: str = None,
        negative_prompt: Optional[str] = None,
        seed: Optional[int] = None,
        steps: Optional[int] = None,
        cfg: Optional[float] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        length: Optional[int] = None,
        fps: Optional[float] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        生成视频
        
        Args:
            prompt: 视频提示词
            image_path: 参考图像路径（可选）
            filename_prefix: 文件名前缀
            negative_prompt: 负提示词（可选）
            seed: 随机种子（可选）
            steps: 采样步数（可选）
            cfg: CFG值（可选）
            width: 视频宽度（可选）
            height: 视频高度（可选）
            length: 视频长度/帧数（可选）
            fps: 帧率（可选）
            **kwargs: 其他参数
            
        Returns:
            生成结果字典，包含 'videos' 键（视频信息列表）
        """
        pass
    
    @abstractmethod
    def get_video(self, filename: str, subfolder: str = "", video_type: str = "output") -> bytes:
        """
        获取生成的视频数据
        
        Args:
            filename: 文件名
            subfolder: 子文件夹
            video_type: 视频类型
            
        Returns:
            视频字节数据
        """
        pass
    
    @abstractmethod
    def connect(self):
        """连接视频生成服务"""
        pass
    
    @abstractmethod
    def disconnect(self):
        """断开连接"""
        pass


class SoraVideoGenerator(VideoGeneratorBase):
    """基于Sora的视频生成器（使用sora_video_client）"""
    
    def __init__(self, api_key: str = None, host: str = "https://grsai.dakka.com.cn", config_path: Optional[str] = None):
        """
        初始化Sora视频生成器
        
        Args:
            api_key: API密钥（可选，如果为None则从配置文件读取）
            host: API服务器地址（默认: https://grsai.dakka.com.cn）
            config_path: 配置文件路径（可选）
        """
        try:
            from sora_video_client import SoraVideoClient, get_api_key
            self._available = True
            
            # 获取API密钥
            try:
                if api_key is None:
                    api_key = get_api_key(config_path=config_path)
                self.client = SoraVideoClient(api_key=api_key, host=host)
            except ValueError as e:
                logger.error(f"无法获取API密钥: {e}")
                self.client = None
                self._available = False
        except ImportError:
            self.client = None
            self._available = False
            logger.error("SoraVideoClient不可用，请确保sora_video_client.py存在")
    
    def connect(self):
        """连接（Sora API不需要显式连接）"""
        if not self._available:
            raise ImportError("SoraVideoClient不可用")
        pass
    
    def disconnect(self):
        """断开连接（Sora API不需要显式断开）"""
        pass
    
    def generate_video(
        self,
        prompt: str,
        image_path: Optional[str] = None,
        filename_prefix: str = None,
        negative_prompt: Optional[str] = None,
        seed: Optional[int] = None,
        steps: Optional[int] = None,
        cfg: Optional[float] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        length: Optional[int] = None,
        fps: Optional[float] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """生成视频"""
        if not self._available:
            raise ImportError("SoraVideoClient不可用")
        
        # Sora API参数映射
        model = kwargs.get('model', 'sora-2')
        aspect_ratio = kwargs.get('aspect_ratio', '16:9')
        duration = kwargs.get('duration', 10)  # 秒
        size = kwargs.get('size', 'small')
        # 默认使用流式响应，以便实时获取进度和结果
        stream = kwargs.get('stream', True)  # 默认启用流式响应
        webhook = kwargs.get('webhook', None)
        shut_progress = kwargs.get('shut_progress', False)
        
        # 根据width和height计算aspect_ratio（如果提供）
        if width and height:
            ratio = width / height
            if abs(ratio - 16/9) < abs(ratio - 9/16):
                aspect_ratio = '16:9'
            else:
                aspect_ratio = '9:16'
        
        # 调用Sora API
        # 启用debug模式以便在出错时获取详细的错误信息
        debug_mode = kwargs.get('debug', False)  # 默认不启用，避免过多输出
        try:
            result = self.client.generate_video(
                prompt=prompt,
                model=model,
                image_file=image_path,
                aspect_ratio=aspect_ratio,
                duration=duration,
                size=size,
                stream=stream,
                webhook=webhook,
                shut_progress=shut_progress,
                debug=debug_mode
            )
        except Exception as e:
            # 捕获并重新抛出，添加更多上下文信息
            error_msg = str(e)
            logger.error(f"Sora API调用失败: {error_msg}")
            if "JSON" in error_msg or "Expecting value" in error_msg:
                logger.error("提示: API返回了非JSON响应，可能是:")
                logger.error("  1. 服务器返回了空响应或HTML错误页面")
                logger.error("  2. 网络连接问题导致响应不完整")
                logger.error("  3. API密钥无效或服务器拒绝请求")
                logger.error("建议: 运行 python test_sora_api.py 进行诊断")
            raise
        
        # 转换为统一格式
        # Sora API返回的格式可能不同，需要适配
        return {
            'videos': [result] if result else [],
            'sora_result': result  # 保留原始结果
        }
    
    def get_video(self, filename: str, subfolder: str = "", video_type: str = "output") -> bytes:
        """获取生成的视频数据"""
        if not self._available:
            raise ImportError("SoraVideoClient不可用")
        # Sora API的视频通常通过URL下载
        # 如果filename是URL，则下载；否则尝试从本地文件读取
        import urllib.request
        if filename.startswith('http://') or filename.startswith('https://'):
            try:
                response = urllib.request.urlopen(filename)
                return response.read()
            except Exception as e:
                logger.error(f"下载视频失败: {e}")
                raise
        else:
            # 尝试从本地文件读取
            if os.path.exists(filename):
                with open(filename, 'rb') as f:
                    return f.read()
            else:
                raise FileNotFoundError(f"视频文件不存在: {filename}")


# ComfyUI 批量生成视频默认使用 Wan2.2 图生视频工作流（--generate-videos 时生效）
DEFAULT_COMFYUI_VIDEO_WORKFLOW = "act_video_wan2_2_14B_i2v-aigc-api.json"
# 有首帧+末帧时使用首末双图生视频工作流
DEFAULT_COMFYUI_VIDEO_WORKFLOW_I2VSE = "act_video_wan2_2_14B_i2vse-aigc-api.json"
# 数字人：图+音频生成视频工作流（--generate-digital-human-videos 时使用）
DEFAULT_COMFYUI_VIDEO_WORKFLOW_S2V = "act_video_wan2_2_14B_s2v-aigc-api.json"
# 数字人 s2v 工作流执行较慢，默认等待 30 分钟
COMFYUI_S2V_WAIT_TIMEOUT_SECONDS = 1800


def _get_first_last_image_node_ids(workflow: dict) -> tuple:
    """从 WanFirstLastFrameToVideo 节点解析首帧、末帧对应的 LoadImage 节点 ID。返回 (start_node_id, end_node_id)。"""
    for nid, nd in workflow.items():
        if not isinstance(nd, dict) or nd.get("class_type") != "WanFirstLastFrameToVideo":
            continue
        inputs = nd.get("inputs") or {}
        start_ref = inputs.get("start_image")
        end_ref = inputs.get("end_image")
        start_id = str(start_ref[0]) if isinstance(start_ref, list) and len(start_ref) >= 1 else None
        end_id = str(end_ref[0]) if isinstance(end_ref, list) and len(end_ref) >= 1 else None
        return start_id, end_id
    return None, None


class ComfyUIVideoGenerator(VideoGeneratorBase):
    """基于ComfyUI的视频生成器（默认使用 act_video_wan2_2_14B_i2v 图生视频工作流；有末帧时用 i2vse 工作流）"""
    
    def __init__(self, server_address: str = "127.0.0.1:8188", workflow_path: str = None):
        """
        初始化ComfyUI视频生成器
        
        Args:
            server_address: ComfyUI服务器地址
            workflow_path: 工作流JSON文件路径（可选，默认使用 act_video_wan2_2_14B_i2v-aigc-api.json 图生视频）
        """
        try:
            from comfyui_client import ComfyUIClient
            self.client = ComfyUIClient(server_address=server_address)
            self._available = True
            
            if workflow_path is None:
                workflow_path = os.path.join(
                    os.path.dirname(__file__),
                    DEFAULT_COMFYUI_VIDEO_WORKFLOW
                )
            self.workflow_path = workflow_path
            base_dir = os.path.dirname(workflow_path)
            self.workflow_i2vse_path = os.path.join(base_dir, DEFAULT_COMFYUI_VIDEO_WORKFLOW_I2VSE)
            self.workflow_s2v_path = os.path.join(base_dir, DEFAULT_COMFYUI_VIDEO_WORKFLOW_S2V)
            self.default_workflow = None
            self._workflow_i2vse = None
            self._workflow_s2v = None
        except ImportError:
            self.client = None
            self._available = False
            logger.error("ComfyUIClient不可用，请确保comfyui_client.py存在")
    
    def connect(self):
        """连接ComfyUI服务器"""
        if not self._available:
            raise ImportError("ComfyUIClient不可用")
        self.client.connect()
    
    def disconnect(self):
        """断开连接"""
        if self.client:
            self.client.disconnect()
    
    def load_default_workflow(self) -> dict:
        """加载默认工作流"""
        if self.default_workflow is None:
            if os.path.exists(self.workflow_path):
                self.default_workflow = self.client.load_workflow(self.workflow_path)
            else:
                raise FileNotFoundError(f"工作流文件不存在: {self.workflow_path}")
        return self.default_workflow.copy()

    def load_i2vse_workflow(self) -> dict:
        """加载首末双图生视频工作流（i2vse）"""
        if self._workflow_i2vse is None:
            if os.path.exists(self.workflow_i2vse_path):
                self._workflow_i2vse = self.client.load_workflow(self.workflow_i2vse_path)
            else:
                raise FileNotFoundError(f"i2vse 工作流文件不存在: {self.workflow_i2vse_path}")
        return self._workflow_i2vse.copy()

    def load_s2v_workflow(self) -> dict:
        """加载图+音频生视频工作流（s2v，数字人）"""
        if self._workflow_s2v is None:
            if os.path.exists(self.workflow_s2v_path):
                self._workflow_s2v = self.client.load_workflow(self.workflow_s2v_path)
            else:
                raise FileNotFoundError(f"s2v 工作流文件不存在: {self.workflow_s2v_path}")
        return self._workflow_s2v.copy()

    def generate_video(
        self,
        prompt: str,
        image_path: Optional[str] = None,
        end_image_path: Optional[str] = None,
        audio_path: Optional[str] = None,
        filename_prefix: str = None,
        negative_prompt: Optional[str] = None,
        seed: Optional[int] = None,
        steps: Optional[int] = None,
        cfg: Optional[float] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        length: Optional[int] = None,
        fps: Optional[float] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """生成视频。提供 audio_path 时使用 s2v 工作流（图+音频→数字人视频）；有首末帧用 i2vse；否则 i2v。"""
        if not self._available:
            raise ImportError("ComfyUIClient不可用")

        use_s2v = bool(audio_path and os.path.isfile(audio_path) and image_path and os.path.isfile(image_path))
        use_i2vse = bool(
            not use_s2v and image_path and end_image_path
            and os.path.isfile(image_path) and os.path.isfile(end_image_path)
        )
        if use_s2v:
            workflow = self.load_s2v_workflow()
            logger.info(f"[图生视频] 使用工作流: {DEFAULT_COMFYUI_VIDEO_WORKFLOW_S2V} (图+音频 s2v 数字人)")
        elif use_i2vse:
            workflow = self.load_i2vse_workflow()
            logger.info(f"[图生视频] 使用工作流: {DEFAULT_COMFYUI_VIDEO_WORKFLOW_I2VSE} (首末双图 i2vse)")
        else:
            workflow = self.load_default_workflow()
            logger.info(f"[图生视频] 使用工作流: {os.path.basename(self.workflow_path)} (单图 i2v)")
        
        # 更新提示词：按工作流中的正/负节点写入，避免与模板默认（如 "white dragon warrior"）混淆
        clip_nodes = self.client.find_nodes_by_class_type(workflow, 'CLIPTextEncode')
        if clip_nodes:
            positive_node_id = None
            negative_node_id = None
            for nid in clip_nodes:
                meta = (workflow.get(nid) or {}).get('_meta') or {}
                title = (meta.get('title') or '').lower()
                if 'positive' in title or '正' in title:
                    positive_node_id = nid
                elif 'negative' in title or '负' in title:
                    negative_node_id = nid
            # 若未从 title 区分，按常见顺序：本工作流模板中先出现负向(89)再正向(93)
            if positive_node_id is None and negative_node_id is None and len(clip_nodes) >= 2:
                negative_node_id = clip_nodes[0]
                positive_node_id = clip_nodes[1]
            elif positive_node_id is None and len(clip_nodes) >= 1:
                positive_node_id = clip_nodes[0]
            elif negative_node_id is None and len(clip_nodes) >= 2:
                negative_node_id = clip_nodes[1] if clip_nodes[0] == positive_node_id else clip_nodes[0]
            if prompt and positive_node_id:
                self.client.update_workflow_input(workflow, positive_node_id, 'text', prompt)
            # 负向：未传时显式清空，避免保留模板中的负向或其它默认文案
            if negative_node_id:
                self.client.update_workflow_input(workflow, negative_node_id, 'text', negative_prompt or '')
        
        # 更新音频（仅 s2v）：上传并设置 LoadAudio
        if use_s2v and audio_path and os.path.isfile(audio_path):
            try:
                upload_result = self.client.upload_file(audio_path, subfolder="input")
                audio_name = upload_result.get("name", os.path.basename(audio_path)) if isinstance(upload_result, dict) else upload_result
                load_audio_nodes = self.client.find_nodes_by_class_type(workflow, "LoadAudio")
                for node_id in load_audio_nodes:
                    self.client.update_workflow_input(workflow, node_id, "audio", audio_name)
                logger.info(f"本地音频已上传至 ComfyUI: {audio_name}")
            except Exception as e:
                logger.warning(f"上传音频失败: {e}")

        # 更新图像：s2v/i2vse 填首帧（及末帧），否则单图填所有 LoadImage
        if use_i2vse:
            start_id, end_id = _get_first_last_image_node_ids(workflow)
            if start_id and end_id:
                for path, node_id, label in [(image_path, start_id, "首帧"), (end_image_path, end_id, "末帧")]:
                    if os.path.isfile(path):
                        try:
                            upload_result = self.client.upload_file(path, subfolder="input")
                            name = upload_result.get("name", os.path.basename(path)) if isinstance(upload_result, dict) else upload_result
                            self.client.update_workflow_input(workflow, node_id, 'image', name)
                            logger.info(f"本地{label}图片已上传至 ComfyUI: {name}")
                        except Exception as e:
                            logger.warning(f"上传{label}图片失败: {e}")
            else:
                logger.warning("i2vse 工作流中未找到首/末帧节点，回退单图")
                use_i2vse = False
                image_path = image_path if os.path.isfile(image_path) else None
        if image_path and (not use_i2vse or use_s2v):
            if os.path.isfile(image_path):
                try:
                    upload_result = self.client.upload_file(image_path, subfolder="input")
                    image_path = upload_result.get("name", os.path.basename(image_path)) if isinstance(upload_result, dict) else upload_result
                    logger.info(f"本地输入图片已上传至 ComfyUI: {image_path}")
                except Exception as e:
                    logger.warning(f"上传本地图片失败: {e}，尝试使用文件名")
                    image_path = os.path.basename(image_path)
            elif os.path.exists(image_path):
                logger.warning(f"输入路径不是文件或不存在: {image_path}，使用 basename")
                image_path = os.path.basename(image_path)
            else:
                image_path = os.path.basename(image_path) if image_path else None

            if image_path:
                image_nodes = self.client.find_nodes_by_class_type(workflow, "LoadImage")
                if image_nodes:
                    for node_id in image_nodes:
                        self.client.update_workflow_input(workflow, node_id, "image", image_path)
            # s2v 时还需填 WanSoundImageToVideo 的 width/height（已在后面统一处理）
        
        # 更新采样器参数：支持 KSampler 或 Wan2.2 i2v 的 KSamplerAdvanced（noise_seed）
        if seed is not None or steps is not None or cfg is not None:
            sampler_nodes = self.client.find_nodes_by_class_type(workflow, 'KSampler')
            for node_id in sampler_nodes:
                if seed is not None:
                    self.client.update_workflow_input(workflow, node_id, 'seed', seed)
                if steps is not None:
                    self.client.update_workflow_input(workflow, node_id, 'steps', steps)
                if cfg is not None:
                    self.client.update_workflow_input(workflow, node_id, 'cfg', cfg)
            adv_nodes = self.client.find_nodes_by_class_type(workflow, 'KSamplerAdvanced')
            for node_id in adv_nodes:
                nd = workflow.get(node_id) or {}
                if (nd.get('inputs') or {}).get('noise_seed') is not None and seed is not None:
                    self.client.update_workflow_input(workflow, node_id, 'noise_seed', seed)
                if steps is not None:
                    self.client.update_workflow_input(workflow, node_id, 'steps', steps)
                if cfg is not None:
                    self.client.update_workflow_input(workflow, node_id, 'cfg', cfg)
        
        # 更新视频尺寸/长度：支持 Wan22ImageToVideoLatent 或 Wan2.2 i2v 的 WanImageToVideo
        if width is not None or height is not None or length is not None:
            latent_nodes = self.client.find_nodes_by_class_type(workflow, 'Wan22ImageToVideoLatent')
            for node_id in latent_nodes:
                if width is not None:
                    self.client.update_workflow_input(workflow, node_id, 'width', width)
                if height is not None:
                    self.client.update_workflow_input(workflow, node_id, 'height', height)
                if length is not None:
                    self.client.update_workflow_input(workflow, node_id, 'length', length)
            wan_i2v_nodes = self.client.find_nodes_by_class_type(workflow, 'WanImageToVideo')
            for node_id in wan_i2v_nodes:
                if width is not None:
                    self.client.update_workflow_input(workflow, node_id, 'width', width)
                if height is not None:
                    self.client.update_workflow_input(workflow, node_id, 'height', height)
                if length is not None:
                    self.client.update_workflow_input(workflow, node_id, 'length', length)
            wan_fl_nodes = self.client.find_nodes_by_class_type(workflow, 'WanFirstLastFrameToVideo')
            for node_id in wan_fl_nodes:
                if width is not None:
                    self.client.update_workflow_input(workflow, node_id, 'width', width)
                if height is not None:
                    self.client.update_workflow_input(workflow, node_id, 'height', height)
                if length is not None:
                    self.client.update_workflow_input(workflow, node_id, 'length', length)
            wan_s2v_nodes = self.client.find_nodes_by_class_type(workflow, 'WanSoundImageToVideo')
            for node_id in wan_s2v_nodes:
                if width is not None:
                    self.client.update_workflow_input(workflow, node_id, 'width', width)
                if height is not None:
                    self.client.update_workflow_input(workflow, node_id, 'height', height)
        
        # 更新帧率：支持 SaveAnimatedWEBP/SaveWEBM 或 Wan2.2 i2v 的 CreateVideo
        if fps is not None:
            webp_nodes = self.client.find_nodes_by_class_type(workflow, 'SaveAnimatedWEBP')
            for node_id in webp_nodes:
                self.client.update_workflow_input(workflow, node_id, 'fps', fps)
            webm_nodes = self.client.find_nodes_by_class_type(workflow, 'SaveWEBM')
            for node_id in webm_nodes:
                self.client.update_workflow_input(workflow, node_id, 'fps', fps)
            create_video_nodes = self.client.find_nodes_by_class_type(workflow, 'CreateVideo')
            for node_id in create_video_nodes:
                self.client.update_workflow_input(workflow, node_id, 'fps', fps)
        
        # 更新文件名前缀：支持 SaveAnimatedWEBP/SaveWEBM 或 Wan2.2 i2v 的 SaveVideo
        if filename_prefix:
            webp_nodes = self.client.find_nodes_by_class_type(workflow, 'SaveAnimatedWEBP')
            for node_id in webp_nodes:
                self.client.update_workflow_input(workflow, node_id, 'filename_prefix', filename_prefix)
            webm_nodes = self.client.find_nodes_by_class_type(workflow, 'SaveWEBM')
            for node_id in webm_nodes:
                self.client.update_workflow_input(workflow, node_id, 'filename_prefix', filename_prefix)
            save_video_nodes = self.client.find_nodes_by_class_type(workflow, 'SaveVideo')
            for node_id in save_video_nodes:
                self.client.update_workflow_input(workflow, node_id, 'filename_prefix', filename_prefix)
        
        # 执行工作流（s2v 数字人耗时长，使用更长超时）
        wait_timeout = kwargs.get("wait_timeout")
        if wait_timeout is None and use_s2v:
            wait_timeout = COMFYUI_S2V_WAIT_TIMEOUT_SECONDS
        return self.client.execute_workflow(workflow, wait=True, wait_timeout=wait_timeout)
    
    def get_video(self, filename: str, subfolder: str = "", video_type: str = "output") -> bytes:
        """获取生成的视频数据"""
        if not self._available:
            raise ImportError("ComfyUIClient不可用")
        # ComfyUI的视频通常作为图像序列或动画文件保存，使用get_image方法获取
        return self.client.get_image(filename, subfolder, video_type)


class BatchVideoGenerator:
    """批量视频生成器"""
    
    def __init__(
        self,
        generator: VideoGeneratorBase,
        output_dir: str = "./output",
        characters: Optional[List[Any]] = None,
        enable_prompt_expansion: bool = True
    ):
        """
        初始化批量视频生成器
        
        Args:
            generator: 视频生成器实例
            output_dir: 输出目录
            characters: 角色列表（用于提示词扩展）
            enable_prompt_expansion: 是否启用提示词扩展。扩展会将角色汇总中的「图像提示词/视觉特征」追加到视频提示词后，可能引入额外元素（如龙等）；若需与 ComfyUI 界面相同效果，建议关闭。
        """
        self.generator = generator
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        
        # 初始化提示词扩展器（复用image_generator中的PromptExpander）
        self.prompt_expander = None
        if enable_prompt_expansion and characters:
            try:
                from image_generator import PromptExpander
                self.prompt_expander = PromptExpander(
                    characters=characters,
                    audio_tracks=[],  # 不使用音频轨道，只从提示词文本中识别角色
                    enabled=True
                )
                logger.info(f"启用视频提示词扩展功能: {len(characters)} 个角色（仅从提示词文本中识别角色）")
            except ImportError:
                logger.warning("无法导入PromptExpander，提示词扩展功能不可用")
        else:
            logger.info("视频提示词扩展功能未启用")
    
    def generate_from_prompts(
        self,
        image_prompts: List[Any],  # List[ImagePrompt]
        episode_filter: Optional[str] = None,
        shot_filter: Optional[str] = None,
        negative_prompt: Optional[str] = None,
        seed: Optional[int] = None,
        steps: Optional[int] = None,
        cfg: Optional[float] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        length: Optional[int] = None,
        fps: Optional[float] = None,
        reference_image_dir: Optional[str] = None,
        reference_audio_dir: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        根据图像汇总表中的视频提示词批量生成视频
        
        Args:
            image_prompts: 图像提示词列表（ImagePrompt对象列表）
            episode_filter: 只处理指定剧集（如: EP01），如果为None则处理所有剧集
            shot_filter: 只处理指定分镜（如: EP01_SQ01），如果为None则处理所有分镜
            negative_prompt: 负提示词（可选）
            seed: 随机种子（可选）
            steps: 采样步数（可选）
            cfg: CFG值（可选）
            width: 视频宽度（可选）
            height: 视频高度（可选）
            length: 视频长度/帧数（可选）
            fps: 帧率（可选）
            reference_image_dir: 输入图片目录（本地），下存 {分镜号}_ref.png 等；未指定时用输出目录
            reference_audio_dir: 输入音频目录（数字人 s2v），下存 {分镜号}.wav / .mp3 等；指定时按图+音频生成视频
            
        Returns:
            生成结果列表
        """
        # 过滤图像提示词
        prompts_to_process = image_prompts
        
        # 先按分镜过滤（优先级更高）
        if shot_filter:
            prompts_to_process = [p for p in prompts_to_process if p.分镜号 == shot_filter]
            logger.info(f"过滤分镜 {shot_filter}: 找到 {len(prompts_to_process)} 个分镜")
        # 再按剧集过滤
        elif episode_filter:
            prompts_to_process = [p for p in prompts_to_process if p.剧集id == episode_filter]
            logger.info(f"过滤剧集 {episode_filter}: 找到 {len(prompts_to_process)} 个分镜")
        
        # 过滤出有视频提示词的分镜
        prompts_to_process = [p for p in prompts_to_process if p.视频提示词]
        
        if not prompts_to_process:
            logger.warning("没有找到需要处理的视频提示词")
            return []
        
        # 输入图片文件本地目录（用于查找 {分镜号}_ref.png 等）；未指定时用输出目录
        ref_image_dir = reference_image_dir or self.output_dir
        logger.info(f"输入图片目录（本地）: {ref_image_dir}")
        if reference_audio_dir:
            logger.info(f"数字人模式：输入音频目录: {reference_audio_dir}")
        
        # 连接生成器
        self.generator.connect()
        
        try:
            results = []
            total = len(prompts_to_process)
            
            logger.info(f"开始批量生成视频，共 {total} 个分镜")
            
            for idx, image_prompt in enumerate(prompts_to_process, 1):
                result = {
                    '分镜号': image_prompt.分镜号,
                    '剧集id': image_prompt.剧集id,
                    '视频': None,
                    'success': True,
                    'errors': []
                }
                
                try:
                    logger.info(f"\n[{idx}/{total}] 处理分镜: {image_prompt.分镜号}")
                    logger.debug(f"  场景内容: {image_prompt.场景内容[:50]}..." if len(image_prompt.场景内容) > 50 else f"  场景内容: {image_prompt.场景内容}")
                    
                    # 扩展视频提示词（如果启用）
                    video_prompt = image_prompt.视频提示词
                    if self.prompt_expander:
                        video_prompt = self.prompt_expander.expand_prompt(video_prompt)
                        logger.debug(f"  提示词已扩展: {len(image_prompt.视频提示词)} -> {len(video_prompt)} 字符")
                    
                    # 查找参考图像：在本地输入图片目录下查找 {分镜号}_ref.*
                    reference_image = None
                    ref_image_name = f"{image_prompt.分镜号}_ref"
                    for ext in ['.png', '.jpg', '.jpeg', '.webp']:
                        ref_path = os.path.join(ref_image_dir, f"{ref_image_name}{ext}")
                        if os.path.exists(ref_path):
                            reference_image = ref_path
                            logger.debug(f"  找到参考图像: {reference_image}")
                            break
                    # 若未找到精确匹配，尝试前缀匹配（如 EP01_SQ01_ref_00018.png）
                    if reference_image is None and os.path.isdir(ref_image_dir):
                        for ext in ['png', 'jpg', 'jpeg', 'webp']:
                            pattern = os.path.join(ref_image_dir, f"{ref_image_name}_*.{ext}")
                            matches = glob.glob(pattern)
                            if matches:
                                reference_image = matches[0]
                                logger.debug(f"  找到参考图像(前缀匹配): {reference_image}")
                                break
                    
                    # 查找末帧图片：有则与首帧一起用 i2vse 工作流（首末双图生视频）
                    last_frame_image = None
                    last_image_name = f"{image_prompt.分镜号}_last"
                    for ext in ['.png', '.jpg', '.jpeg', '.webp']:
                        last_path = os.path.join(ref_image_dir, f"{last_image_name}{ext}")
                        if os.path.exists(last_path):
                            last_frame_image = last_path
                            logger.debug(f"  找到末帧图像: {last_frame_image}")
                            break
                    if last_frame_image is None and os.path.isdir(ref_image_dir):
                        for ext in ['png', 'jpg', 'jpeg', 'webp']:
                            pattern = os.path.join(ref_image_dir, f"{last_image_name}_*.{ext}")
                            matches = glob.glob(pattern)
                            if matches:
                                matches.sort(key=lambda x: os.path.getmtime(x), reverse=True)
                                last_frame_image = matches[0]
                                logger.debug(f"  找到末帧图像(前缀匹配): {last_frame_image}")
                                break
                    if reference_image and last_frame_image:
                        logger.info(f"  使用首帧+末帧，i2vse 工作流生成视频")
                    
                    # 数字人 s2v：在音频目录下查找当前分镜的音频文件
                    audio_path = None
                    if reference_audio_dir and os.path.isdir(reference_audio_dir):
                        shot_id = image_prompt.分镜号
                        for ext in (".wav", ".mp3", ".flac", ".m4a", ".ogg"):
                            p = os.path.join(reference_audio_dir, f"{shot_id}{ext}")
                            if os.path.isfile(p):
                                audio_path = p
                                logger.info(f"  使用音频: {audio_path}")
                                break
                        if not audio_path:
                            for ext in ("wav", "mp3", "flac", "m4a", "ogg"):
                                pattern = os.path.join(reference_audio_dir, f"{shot_id}_*.{ext}")
                                matches = glob.glob(pattern)
                                if matches:
                                    audio_path = matches[0]
                                    logger.info(f"  使用音频(前缀匹配): {audio_path}")
                                    break
                    
                    # 生成视频
                    logger.info(f"  生成视频...")
                    gen_result = self.generator.generate_video(
                        prompt=video_prompt,
                        image_path=reference_image,
                        end_image_path=last_frame_image,
                        audio_path=audio_path,
                        filename_prefix=f"{image_prompt.分镜号}_video",
                        negative_prompt=negative_prompt,
                        seed=seed,
                        steps=steps,
                        cfg=cfg,
                        width=width,
                        height=height,
                        length=length,
                        fps=fps
                    )
                    
                    # 保存视频（根据生成器类型处理）
                    if isinstance(self.generator, SoraVideoGenerator):
                        # Sora API返回格式处理
                        sora_result = gen_result.get('sora_result', {})
                        if sora_result:
                            # 检查状态
                            status = sora_result.get('status', '')
                            if status == 'succeeded':
                                # Sora API返回格式: {"results": [{"url": "...", "pid": "...", ...}], ...}
                                # 获取视频URL（从sora_results数组中获取第一个结果的url）
                                video_url = None
                                sora_results = sora_result.get('results', [])  # 重命名避免与外层results冲突
                                if sora_results and len(sora_results) > 0:
                                    video_url = sora_results[0].get('url')
                                    result['pid'] = sora_results[0].get('pid')  # 保存视频ID
                                
                                # 如果sora_results中没有，尝试直接从sora_result获取（兼容其他格式）
                                if not video_url:
                                    video_url = sora_result.get('video_url') or sora_result.get('url')
                                
                                if video_url:
                                    try:
                                        # 下载视频
                                        import urllib.request
                                        logger.info(f"    正在下载视频: {video_url[:60]}...")
                                        video_data = urllib.request.urlopen(video_url).read()
                                        # 保存视频
                                        output_filename = f"{image_prompt.分镜号}_video.mp4"
                                        output_path = os.path.join(self.output_dir, output_filename)
                                        with open(output_path, 'wb') as f:
                                            f.write(video_data)
                                        result['视频'] = output_path
                                        result['success'] = True  # 确保设置成功标志
                                        logger.info(f"    ✓ 保存视频: {output_path}")
                                    except Exception as e:
                                        error_msg = f"下载视频失败: {e}"
                                        logger.error(f"    ✗ {error_msg}")
                                        result['errors'].append(error_msg)
                                        result['success'] = False
                                else:
                                    error_msg = "生成视频成功但未返回视频URL"
                                    logger.warning(f"    ⚠ {error_msg}")
                                    result['errors'].append(error_msg)
                                    result['success'] = False
                            elif status == 'failed':
                                error_msg = f"生成视频失败: {sora_result.get('error', sora_result.get('failure_reason', 'Unknown error'))}"
                                logger.error(f"    ✗ {error_msg}")
                                result['errors'].append(error_msg)
                                result['success'] = False
                            elif status == 'running':
                                # 处理中状态
                                task_id = sora_result.get('id')
                                progress = sora_result.get('progress', 0)
                                if task_id:
                                    logger.info(f"    任务ID: {task_id}，状态: {status}，进度: {progress}%")
                                    result['task_id'] = task_id
                                    result['status'] = status
                                    result['progress'] = progress
                                    # 对于运行中的任务，标记为未完成但不算失败
                                    result['success'] = False
                                    result['errors'].append(f"任务仍在处理中（进度: {progress}%）")
                            else:
                                # 其他状态
                                task_id = sora_result.get('id')
                                if task_id:
                                    logger.info(f"    任务ID: {task_id}，状态: {status}")
                                    result['task_id'] = task_id
                                    result['status'] = status
                                    result['success'] = False
                                    result['errors'].append(f"未知状态: {status}")
                        else:
                            error_msg = "生成视频失败: 未返回结果"
                            logger.warning(f"    ⚠ {error_msg}")
                            result['errors'].append(error_msg)
                            result['success'] = False
                    else:
                        # ComfyUI 视频：保存时把末尾 _.mp4 规范为 .mp4
                        def _norm_video_filename(name: str) -> str:
                            for suffix in ('_.mp4', '_.webm', '_.webp'):
                                if name.endswith(suffix):
                                    return name[:-len(suffix)] + suffix[1:]
                            return name
                        saved = False
                        for key in ('videos', 'images'):
                            items = gen_result.get(key) or {}
                            for node_id, video_info in items.items():
                                orig_name = video_info['filename']
                                save_name = _norm_video_filename(orig_name)
                                video_data = self.generator.get_video(
                                    orig_name,
                                    video_info.get('subfolder', ''),
                                    video_info.get('type', 'output')
                                )
                                output_path = os.path.join(self.output_dir, save_name)
                                with open(output_path, 'wb') as f:
                                    f.write(video_data)
                                result['视频'] = output_path
                                result['success'] = True
                                logger.info(f"    ✓ 保存视频: {output_path}")
                                saved = True
                                break
                            if saved:
                                break
                        if not saved:
                            error_msg = "生成视频失败: 未返回视频文件"
                            logger.warning(f"    ⚠ {error_msg}")
                            result['errors'].append(error_msg)
                            result['success'] = False
                    
                    logger.info(f"  ✓ 完成: {image_prompt.分镜号}")
                    
                except Exception as e:
                    error_msg = f"处理分镜 {image_prompt.分镜号} 时出错: {e}"
                    logger.error(f"  ✗ {error_msg}")
                    # 确保result字典存在且包含所有必需的键
                    if 'errors' not in result:
                        result['errors'] = []
                    result['errors'].append(error_msg)
                    result['success'] = False
                    import traceback
                    traceback.print_exc()
                
                # 确保result字典包含所有必需的键（防御性编程）
                if 'success' not in result:
                    result['success'] = False
                if 'errors' not in result:
                    result['errors'] = []
                
                results.append(result)
            
            # 统计结果（使用get方法避免KeyError）
            successful = sum(1 for r in results if r.get('success', False))
            failed = len(results) - successful
            logger.info("\n" + "="*80)
            logger.info("批量生成视频完成!")
            logger.info(f"总计: {len(results)} 个分镜")
            logger.info(f"成功: {successful} 个")
            logger.info(f"失败: {failed} 个")
            
            if failed > 0:
                logger.info("\n失败的分镜:")
                for r in results:
                    if not r.get('success', False):
                        errors = r.get('errors', [])
                        shot_id = r.get('分镜号', '未知')
                        logger.info(f"  - {shot_id}: {', '.join(errors) if errors else '未知错误'}")
            
            return results
            
        finally:
            self.generator.disconnect()


def create_video_generator(
    generator_type: str = "comfyui",
    server_address: str = "127.0.0.1:8188",
    workflow_path: Optional[str] = None,
    api_key: Optional[str] = None,
    host: str = "https://grsai.dakka.com.cn",
    config_path: Optional[str] = None,
    **kwargs
) -> VideoGeneratorBase:
    """
    工厂函数：创建视频生成器
    
    Args:
        generator_type: 生成器类型 ("comfyui", "sora", 或其他)
        server_address: 服务器地址（用于comfyui类型）
        workflow_path: 工作流文件路径（可选，用于comfyui类型）
        api_key: Sora API密钥（用于sora类型，如果为None则从配置文件读取）
        host: Sora API服务器地址（用于sora类型）
        config_path: Sora配置文件路径（用于sora类型）
        **kwargs: 其他参数（用于扩展）
        
    Returns:
        视频生成器实例
    """
    if generator_type.lower() == "comfyui":
        return ComfyUIVideoGenerator(server_address=server_address, workflow_path=workflow_path)
    elif generator_type.lower() == "sora":
        return SoraVideoGenerator(api_key=api_key, host=host, config_path=config_path)
    else:
        raise ValueError(f"不支持的生成器类型: {generator_type}")


# 便捷函数
def batch_generate_videos_from_excel_data(
    image_prompts: List[Any],
    output_dir: str = "./output",
    comfyui_server: str = "127.0.0.1:8188",
    workflow_path: Optional[str] = None,
    episode_filter: Optional[str] = None,
    shot_filter: Optional[str] = None,
    negative_prompt: Optional[str] = None,
    seed: Optional[int] = None,
    steps: Optional[int] = None,
    cfg: Optional[float] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
    length: Optional[int] = None,
    fps: Optional[float] = None,
    reference_image_dir: Optional[str] = None,
    reference_audio_dir: Optional[str] = None,
    generator_type: str = "comfyui",
    characters: Optional[List[Any]] = None,
    enable_prompt_expansion: bool = True,
    sora_api_key: Optional[str] = None,
    sora_host: str = "https://grsai.dakka.com.cn",
    sora_config_path: Optional[str] = None,
    provider_profile: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    便捷函数：从Excel数据批量生成视频
    
    Args:
        image_prompts: 图像提示词列表
        output_dir: 输出目录
        comfyui_server: ComfyUI服务器地址（用于comfyui类型）
        workflow_path: 工作流文件路径（可选，用于comfyui类型）
        episode_filter: 剧集过滤
        shot_filter: 分镜过滤
        negative_prompt: 负提示词
        seed: 随机种子
        steps: 采样步数
        cfg: CFG值
        width: 视频宽度
        height: 视频高度
        length: 视频长度/帧数
        fps: 帧率
        reference_image_dir: 参考图像目录
        reference_audio_dir: 参考音频目录（数字人 s2v）；指定时每分镜在该目录下找 {分镜号}.wav 等，按图+音频生成视频
        generator_type: 生成器类型（"comfyui" 或 "sora"）
        characters: 角色列表（用于提示词扩展）
        enable_prompt_expansion: 是否启用提示词扩展
        sora_api_key: Sora API密钥（用于sora类型）
        sora_host: Sora API服务器地址（用于sora类型）
        sora_config_path: Sora配置文件路径（用于sora类型）
        provider_profile: 可选，generation_framework 视频 profile_id（如 comfyui.default、sora.default）
        
    Returns:
        生成结果列表
    """
    try:
        from generation_framework import (
            create_video_generator_by_profile,
            resolve_video_profile_id,
        )

        pid = resolve_video_profile_id(provider_profile, generator_type)
        generator = create_video_generator_by_profile(
            pid,
            comfyui_server,
            workflow_path=workflow_path,
            api_key=sora_api_key,
            sora_host=sora_host,
            sora_config_path=sora_config_path,
        )
    except ImportError:
        if generator_type.lower() == "sora":
            generator = create_video_generator(
                generator_type=generator_type,
                api_key=sora_api_key,
                host=sora_host,
                config_path=sora_config_path,
            )
        else:
            generator = create_video_generator(
                generator_type=generator_type,
                server_address=comfyui_server,
                workflow_path=workflow_path,
            )
    except ValueError as e:
        logger.warning("%s，回退 create_video_generator", e)
        if generator_type.lower() == "sora":
            generator = create_video_generator(
                "sora",
                server_address=comfyui_server,
                api_key=sora_api_key,
                host=sora_host,
                config_path=sora_config_path,
            )
        else:
            generator = create_video_generator(
                "comfyui",
                server_address=comfyui_server,
                workflow_path=workflow_path,
            )
    
    # 创建批量生成器（支持提示词扩展）
    batch_generator = BatchVideoGenerator(
        generator,
        output_dir,
        characters=characters,
        enable_prompt_expansion=enable_prompt_expansion
    )
    
    # 输入图片在本地：未指定目录时使用输出目录，用于查找 {分镜号}_ref.png 等
    input_image_dir = reference_image_dir if reference_image_dir is not None else output_dir
    return batch_generator.generate_from_prompts(
        image_prompts=image_prompts,
        episode_filter=episode_filter,
        shot_filter=shot_filter,
        negative_prompt=negative_prompt,
        seed=seed,
        steps=steps,
        cfg=cfg,
        width=width,
        height=height,
        length=length,
        fps=fps,
        reference_image_dir=input_image_dir,
        reference_audio_dir=reference_audio_dir
    )

