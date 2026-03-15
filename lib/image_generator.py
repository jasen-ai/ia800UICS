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
图像生成器模块 - 用于根据Excel数据批量生成图像
支持多种生成方式，方便后续扩展
"""
import os
import re
import logging
from typing import Dict, List, Optional, Any
from abc import ABC, abstractmethod

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PromptExpander:
    """提示词扩展器 - 根据角色信息扩展提示词"""
    
    def __init__(
        self,
        characters: Optional[List[Any]] = None,
        audio_tracks: Optional[List[Any]] = None,
        enabled: bool = True,
        separator: str = ", "
    ):
        """
        初始化提示词扩展器
        
        Args:
            characters: 角色列表（Character对象列表）
            audio_tracks: 音频轨道列表（AudioTrack对象列表）
            enabled: 是否启用扩展
            separator: 提示词分隔符
        """
        self.characters = characters or []
        self.audio_tracks = audio_tracks or []
        self.enabled = enabled
        self.separator = separator
        
        # 构建角色名到角色对象的映射
        self.character_map = {}
        for char in self.characters:
            if char.角色名:
                self.character_map[char.角色名] = char
        
        logger.debug(f"提示词扩展器初始化: {len(self.character_map)} 个角色")
    
    def find_characters_in_shot(self, shot_id: str) -> List[str]:
        """
        从音频轨道中查找分镜对应的角色
        
        Args:
            shot_id: 分镜号
            
        Returns:
            找到的角色名列表
        """
        found_characters = []
        
        for track in self.audio_tracks:
            if track.分镜号 == shot_id:
                # 优先使用音频角色，如果没有则使用剧情角色
                char_name = track.音频角色 or track.剧情角色
                if char_name and char_name not in found_characters:
                    # 过滤掉"旁白"
                    if char_name != "旁白":
                        found_characters.append(char_name)
        
        return found_characters
    
    def find_characters_in_prompt(self, prompt: str) -> List[str]:
        """
        从提示词中查找角色名（精确匹配，避免误识别）
        
        Args:
            prompt: 提示词文本
            
        Returns:
            找到的角色名列表
        """
        if not prompt:
            return []
        
        found_characters = []
        
        for char_name in self.character_map.keys():
            # 直接检查角色名是否在提示词中（中文角色名通常作为完整词出现）
            # 使用简单的包含检查，因为中文角色名通常是独立的词
            if char_name in prompt:
                found_characters.append(char_name)
                logger.debug(f"  在提示词中找到角色: {char_name}")
        
        return found_characters
    
    def expand_prompt(
        self,
        prompt: str,
        shot_id: Optional[str] = None,
        characters: Optional[List[str]] = None
    ) -> str:
        """
        扩展提示词，附加角色特征
        
        Args:
            prompt: 原始提示词
            shot_id: 分镜号（已废弃，不再使用音频轨道查找角色）
            characters: 角色名列表（如果为None，则从提示词文本中自动查找）
            
        Returns:
            扩展后的提示词
        """
        if not self.enabled:
            return prompt
        
        if not prompt:
            return prompt
        
        # 如果没有提供角色列表，只从提示词文本中查找（不从音频轨道查找）
        if characters is None:
            # 只从提示词文本中查找角色（提示词直接描述图像内容，最准确）
            # 不从音频轨道查找，避免加错角色提示词
            characters = self.find_characters_in_prompt(prompt)
            
            if characters:
                logger.debug(f"从提示词中找到角色: {characters}")
            else:
                logger.debug(f"提示词中未找到角色，不进行扩展")
        
        if not characters:
            return prompt
        
        # 收集所有角色的图像提示词
        character_features = []
        for char_name in characters:
            if char_name in self.character_map:
                char = self.character_map[char_name]
                # 优先使用图像提示词，如果没有则使用视觉特征
                feature = char.图像提示词 or char.视觉特征
                if feature:
                    character_features.append(feature)
                    logger.debug(f"  找到角色 {char_name} 的特征提示词: {feature[:50]}...")
        
        if not character_features:
            return prompt
        
        # 组合特征提示词
        features_text = self.separator.join(character_features)
        
        # 附加到原始提示词后面
        expanded_prompt = f"{prompt}{self.separator}{features_text}"
        
        logger.debug(f"提示词扩展: {len(prompt)} -> {len(expanded_prompt)} 字符")
        logger.debug(f"  原始: {prompt[:80]}...")
        logger.debug(f"  扩展后: {expanded_prompt[:120]}...")
        
        return expanded_prompt


def _parse_reference_images(ref_str: Optional[str]) -> Optional[List[str]]:
    """
    从图像汇总中的「参考图」字段解析出 1～3 个参考图路径。
    支持逗号分隔；空或无效时返回 None。
    """
    if not ref_str or not str(ref_str).strip():
        return None
    paths = [p.strip() for p in str(ref_str).split(",") if p.strip()]
    if not paths:
        return None
    return paths[:3]


def _find_image_in_dir(directory: str, base_name: str) -> Optional[str]:
    """在目录下查找 base_name 的图片文件，优先 .png，其次 .jpg/.jpeg。"""
    if not directory or not base_name:
        return None
    for ext in (".png", ".jpg", ".jpeg"):
        path = os.path.join(directory, base_name + ext)
        if os.path.isfile(path):
            return path
    return None


def _get_id_from_obj(obj: Any, id_key: str) -> Optional[Any]:
    """从场景/角色对象取 id（支持 dataclass 与 dict）。返回 int 或 str（如 LOC-xxx、CHAR-xxx），用于文件名。"""
    if obj is None:
        return None
    if isinstance(obj, dict):
        val = obj.get(id_key)
    else:
        val = getattr(obj, id_key, None)
    if val is None:
        return None
    if isinstance(val, str) and val.strip():
        return val.strip()
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _find_image_by_bases(directory: str, base_names: List[str]) -> Optional[str]:
    """在目录下依次用多个候选文件名查找图片，返回第一个找到的路径。支持 场景id/场景名、角色id/角色名 两种命名。"""
    if not directory:
        return None
    seen = set()
    for base in base_names:
        if not base or not str(base).strip():
            continue
        key = str(base).strip()
        if key in seen:
            continue
        seen.add(key)
        path = _find_image_in_dir(directory, key)
        if path:
            return path
    return None


def _resolve_reference_images_for_edit(
    image_prompt: Any,
    scenes: Optional[List[Any]] = None,
    characters: Optional[List[Any]] = None,
    scene_image_dir: Optional[str] = None,
    character_image_dir: Optional[str] = None,
    reference_image_dir: Optional[str] = None,
) -> List[str]:
    """
    按「参考图1=场景id图、参考图2(及后续)=角色id图、最后=图像汇总参考图」解析 1～3 张参考图路径。
    文件从本地相应目录读取，生成时会上传至 ComfyUI。支持 .png / .jpg / .jpeg。
    
    - 参考图1: 图像汇总.场景名 -> 场景id -> {scene_image_dir}/{场景id}.png（或 .jpg）
    - 参考图2、3: 图像汇总.角色（支持多角色：逗号、顿号、分号、空格或换行分隔）-> 每个角色查角色id -> {character_image_dir}/{角色id}.png，依次填入，最多 2 张角色图
    - 剩余空位: 图像汇总.参考图（路径或文件名，相对时用 reference_image_dir 拼接）
    
    Returns:
        存在的本地文件路径列表，长度为 1～3；这些路径会在调用工作流前上传至 ComfyUI。
    """
    result: List[str] = []
    scenes = scenes or []
    characters = characters or []

    scene_name = getattr(image_prompt, "场景名", None) if image_prompt else None
    role_name = getattr(image_prompt, "角色", None) if image_prompt else None
    ref3_raw = getattr(image_prompt, "参考图", None) if image_prompt else None
    logger.info(f"  [参考图解析] 图像汇总本行: 场景名={repr(scene_name)}, 角色={repr(role_name)}, 参考图={repr(ref3_raw)}")
    logger.info(f"  [参考图解析] 配置目录: scene_image_dir={repr(scene_image_dir)}, character_image_dir={repr(character_image_dir)}, reference_image_dir={repr(reference_image_dir)}")

    # 参考图1：场景名 -> 场景汇总查场景id，目录下支持 场景id 或 场景名 两种文件名
    if scene_name and str(scene_name).strip() and scene_image_dir:
        scene = next((s for s in scenes if (s.get("场景名") if isinstance(s, dict) else getattr(s, "场景名", None)) == scene_name), None)
        if scene is not None:
            sid = _get_id_from_obj(scene, "场景id")
            name_str = str(scene_name).strip()
            bases = [str(sid)] if sid is not None else []
            if name_str and name_str not in bases:
                bases.append(name_str)
            path = _find_image_by_bases(scene_image_dir, bases)
            if path:
                result.append(path)
                logger.info(f"  [参考图1] 场景名={scene_name} -> 支持 场景id/场景名 文件名 -> 找到: {path}")
            else:
                tried = "、".join(bases) if bases else "(无)"
                logger.info(f"  [参考图1] 场景名={scene_name} -> 已尝试 场景id/场景名 文件名: [{tried}] -> 在目录 {scene_image_dir} 下未找到，跳过")
        else:
            logger.info(f"  [参考图1] 场景名={scene_name} 在场景汇总中未找到匹配项，跳过")
    elif scene_name and str(scene_name).strip():
        logger.info(f"  [参考图1] 场景名={scene_name} 有值但未配置 scene_image_dir，跳过")
    else:
        logger.info(f"  [参考图1] 场景名为空或未配置场景目录，跳过")

    # 参考图2、3：角色（支持多角色：逗号、顿号、分号、空格或换行分隔）-> 每个角色查角色id，依次加入，最多占 2 个空位（总参考图不超过 3 张）
    if role_name is not None and str(role_name).strip() and character_image_dir:
        role_raw = str(role_name).strip()
        role_names = [p.strip() for p in re.split(r"[,，;；\s\r\n]+", role_raw) if p.strip()]
        for rn in role_names:
            if len(result) >= 3:
                break
            char = next((c for c in characters if (c.get("角色名") if isinstance(c, dict) else getattr(c, "角色名", None)) == rn), None)
            if char is not None:
                cid = _get_id_from_obj(char, "角色id")
                bases = [str(cid)] if cid is not None else []
                if rn and rn not in bases:
                    bases.append(rn)
                path = _find_image_by_bases(character_image_dir, bases)
                if path:
                    result.append(path)
                    logger.info(f"  [参考图-角色] 角色={rn} -> 找到: {path}")
                else:
                    tried = "、".join(bases) if bases else "(无)"
                    logger.info(f"  [参考图-角色] 角色={rn} -> 已尝试 [{tried}] 在 {character_image_dir} 下未找到，跳过")
            else:
                logger.info(f"  [参考图-角色] 角色={rn} 在角色汇总中未找到匹配项，跳过")
        if not role_names:
            logger.info(f"  [参考图-角色] 角色列解析后无有效角色名，跳过")
    elif role_name is not None and str(role_name).strip():
        logger.info(f"  [参考图-角色] 角色={repr(role_name)} 有值但未配置 character_image_dir，跳过")
    else:
        logger.info(f"  [参考图-角色] 角色为空或未配置角色目录，跳过")

    # 参考图3：图像汇总.参考图（支持逗号/分号分隔多张；本地路径或相对 reference_image_dir）
    if ref3_raw and str(ref3_raw).strip():
        raw_str = str(ref3_raw).strip()
        parts = re.split(r"[,，;；\s]+", raw_str)
        for raw in parts:
            if len(result) >= 3:
                break
            raw = raw.strip()
            if not raw:
                continue
            if os.path.isabs(raw) and os.path.isfile(raw):
                result.append(raw)
                logger.info(f"  [参考图3] 参考图列={repr(raw)} -> 绝对路径存在: {raw}")
            elif reference_image_dir:
                path = os.path.join(reference_image_dir, raw)
                if os.path.isfile(path):
                    result.append(path)
                    logger.info(f"  [参考图3] 参考图列={repr(raw)} -> 找到: {path}")
                else:
                    base, ext = os.path.splitext(raw)
                    if not ext:
                        path = _find_image_in_dir(reference_image_dir, base)
                        if path:
                            result.append(path)
                            logger.info(f"  [参考图3] 参考图列={repr(raw)} -> 无扩展名，找到: {path}")
                        else:
                            logger.info(f"  [参考图3] 参考图列={repr(raw)} -> 在 {reference_image_dir} 下未找到 {base}.png/.jpg/.jpeg，跳过")
                    else:
                        logger.info(f"  [参考图3] 参考图列={repr(raw)} -> 路径不存在: {path}，跳过")
            else:
                if os.path.isfile(raw):
                    result.append(os.path.abspath(raw))
                    logger.info(f"  [参考图3] 参考图列={repr(raw)} -> 当前目录存在: {os.path.abspath(raw)}")
                else:
                    logger.info(f"  [参考图3] 参考图列={repr(raw)} -> 文件不存在且未配置 reference_image_dir，跳过")
    else:
        logger.info(f"  [参考图3] 参考图列为空，跳过")

    logger.info(f"  [参考图解析] 最终得到 {len(result)} 张参考图: {result}")
    return result


class ImageGeneratorBase(ABC):
    """图像生成器基类，定义统一的接口"""
    
    @abstractmethod
    def generate_image(
        self,
        prompt: str,
        filename_prefix: str,
        style_prefix: Optional[str] = None,
        seed: Optional[int] = None,
        steps: Optional[int] = None,
        cfg: Optional[float] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        reference_images: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        生成单张图像
        
        Args:
            prompt: 图像提示词
            filename_prefix: 文件名前缀
            style_prefix: 风格前缀（可选）
            seed: 随机种子（可选）
            steps: 采样步数（可选）
            cfg: CFG值（可选）
            width: 图像宽度（可选）
            height: 图像高度（可选）
            reference_images: 参考图路径列表，1/2/3 张时使用 Qwen Image Edit 工作流（可选，仅 ComfyUI 支持）
            
        Returns:
            生成结果字典，包含 'images' 键（图像信息列表）
        """
        pass
    
    @abstractmethod
    def get_image(self, filename: str, subfolder: str = "", image_type: str = "output") -> bytes:
        """
        获取生成的图像数据
        
        Args:
            filename: 文件名
            subfolder: 子文件夹
            image_type: 图像类型
            
        Returns:
            图像字节数据
        """
        pass
    
    @abstractmethod
    def connect(self):
        """连接图像生成服务"""
        pass
    
    @abstractmethod
    def disconnect(self):
        """断开连接"""
        pass


class ComfyUIImageGenerator(ImageGeneratorBase):
    """基于ComfyUI的图像生成器（使用ZImageClient）"""
    
    def __init__(
        self,
        server_address: str = "127.0.0.1:8188",
        txt2img_workflow_path: Optional[str] = None,
    ):
        """
        初始化ComfyUI图像生成器
        
        Args:
            server_address: ComfyUI服务器地址
            txt2img_workflow_path: 文生图工作流 JSON 路径（可选，默认 z_image_workflow.json）
        """
        try:
            from z_image_client import ZImageClient
            self.client = ZImageClient(
                server_address=server_address,
                workflow_path=txt2img_workflow_path,
            )
            self._available = True
        except ImportError:
            self.client = None
            self._available = False
            logger.error("ZImageClient不可用，请确保z_image_client.py存在")
    
    def connect(self):
        """连接ComfyUI服务器"""
        if not self._available:
            raise ImportError("ZImageClient不可用")
        self.client.connect()
    
    def disconnect(self):
        """断开连接"""
        if self.client:
            self.client.disconnect()
    
    def generate_image(
        self,
        prompt: str,
        filename_prefix: str,
        style_prefix: Optional[str] = None,
        seed: Optional[int] = None,
        steps: Optional[int] = None,
        cfg: Optional[float] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        reference_images: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """生成图像。若提供 1/2/3 张 reference_images，则使用 act_02_qwen_Image_edit-aigc-3-api 工作流。"""
        if not self._available:
            raise ImportError("ZImageClient不可用")
        
        logger.info(f"  [ComfyUI] generate_image 收到 reference_images: len={len(reference_images) if reference_images else 0}, value={reference_images}")
        if reference_images and 1 <= len(reference_images) <= 3:
            logger.info(f"  [ComfyUI] 条件满足，走 有参考图 分支 -> act_02_qwen_Image_edit-aigc-3-api.json")
            full_prompt = f"{style_prefix}, {prompt}" if style_prefix else prompt
            return self.client.generate_image_edit(
                prompt=full_prompt,
                reference_images=reference_images,
                filename_prefix=filename_prefix,
                seed=seed,
                steps=steps,
                cfg=cfg,
                wait=True,
            )
        
        logger.info(f"  [ComfyUI] 走 无参考图 分支 -> 默认文生图 z_image_workflow.json (reference_images 为空或数量不在 1~3)")
        return self.client.generate_image(
            prompt=prompt,
            style_prefix=style_prefix,
            seed=seed,
            steps=steps,
            cfg=cfg,
            width=width,
            height=height,
            filename_prefix=filename_prefix,
            wait=True
        )
    
    def get_image(self, filename: str, subfolder: str = "", image_type: str = "output") -> bytes:
        """获取生成的图像数据"""
        if not self._available:
            raise ImportError("ZImageClient不可用")
        return self.client.get_image(filename, subfolder, image_type)


class NanoBananaImageGenerator(ImageGeneratorBase):
    """基于Nano Banana的图像生成器"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        host: Optional[str] = None,
        config_path: Optional[str] = None,
        model: str = "nano-banana-fast",
        aspect_ratio: str = "auto",
        image_size: str = "1K"
    ):
        """
        初始化Nano Banana图像生成器
        
        Args:
            api_key: API密钥（可选，从配置文件读取）
            host: API服务器地址（可选，从配置文件读取）
            config_path: 配置文件路径（可选）
            model: 模型名称（默认: "nano-banana-fast"）
            aspect_ratio: 输出图像比例（默认: "auto"）
            image_size: 输出图像大小（默认: "1K"）
        """
        try:
            from nanobanana_client import NanoBananaClient, get_api_key
            self.NanoBananaClient = NanoBananaClient
            self.get_api_key = get_api_key
            
            # 获取API密钥
            try:
                api_key = api_key or get_api_key(None, config_path)
            except ValueError as e:
                logger.error(f"无法获取Nano Banana API密钥: {e}")
                self.client = None
                self._available = False
                return
            
            # 创建客户端
            self.client = NanoBananaClient(
                api_key=api_key,
                host=host,
                config_path=config_path
            )
            self.model = model
            self.aspect_ratio = aspect_ratio
            self.image_size = image_size
            self._available = True
            self._generated_images = {}  # 存储生成的图像数据，key为filename_prefix
            logger.info(f"Nano Banana图像生成器初始化成功，模型: {model}")
        except ImportError:
            self.client = None
            self._available = False
            logger.error("NanoBananaClient不可用，请确保nanobanana_client.py存在")
        except Exception as e:
            self.client = None
            self._available = False
            logger.error(f"初始化Nano Banana图像生成器失败: {e}")
    
    def connect(self):
        """连接Nano Banana服务（无需实际连接，仅验证可用性）"""
        if not self._available:
            raise ImportError("NanoBananaClient不可用")
        logger.debug("Nano Banana客户端已就绪")
    
    def disconnect(self):
        """断开连接（无需实际操作）"""
        self._generated_images.clear()
        logger.debug("Nano Banana客户端已断开")
    
    def generate_image(
        self,
        prompt: str,
        filename_prefix: str,
        style_prefix: Optional[str] = None,
        seed: Optional[int] = None,
        steps: Optional[int] = None,
        cfg: Optional[float] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        reference_images: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        生成图像。reference_images 支持 1～3 张参考图，走 Nano Banana 图生图。
        
        Args:
            prompt: 图像提示词
            filename_prefix: 文件名前缀
            style_prefix: 风格前缀（可选，会添加到prompt前面）
            seed: 随机种子（可选，Nano Banana不支持）
            steps: 采样步数（可选，Nano Banana不支持）
            cfg: CFG值（可选，Nano Banana不支持）
            width: 图像宽度（可选，Nano Banana不支持，使用aspect_ratio和image_size）
            height: 图像高度（可选，Nano Banana不支持，使用aspect_ratio和image_size）
            reference_images: 参考图列表（可选，1～3 张，本地路径或 URL）
        
        Returns:
            生成结果字典，包含 'images' 键（图像信息列表）
        """
        if not self._available:
            raise ImportError("NanoBananaClient不可用")
        
        # 组合提示词（如果有风格前缀）
        full_prompt = prompt
        if style_prefix:
            full_prompt = f"{style_prefix}, {prompt}"
        
        refs = None
        if reference_images:
            refs = list(reference_images)[:3]
            logger.info(f"使用Nano Banana 图生图: {full_prompt[:100]}...，参考图 {len(refs)} 张: {refs}")
        else:
            logger.info(f"使用Nano Banana 文生图: {full_prompt[:100]}...")
        
        # 调用Nano Banana API生成图像（如提供参考图则走图生图）
        result = self.client.generate_image(
            prompt=full_prompt,
            model=self.model,
            reference_images=refs,
            aspect_ratio=self.aspect_ratio,
            image_size=self.image_size,
            stream=True  # 使用流式响应
        )
        
        # 检查生成结果
        if result.get('status') != 'succeeded':
            error_msg = result.get('failure_reason') or result.get('error') or 'Unknown error'
            raise RuntimeError(f"Nano Banana生成失败: {error_msg}")
        
        # 获取生成的图像URL
        results = result.get('results', [])
        if not results:
            raise RuntimeError("Nano Banana未返回图像结果")
        
        # 下载图像并保存到内存
        import urllib.request
        import time
        
        images_info = []
        for idx, res in enumerate(results):
            image_url = res.get('url')
            if not image_url:
                logger.warning(f"结果 {idx} 没有URL，跳过")
                continue
            
            try:
                # 下载图像
                logger.debug(f"正在下载图像: {image_url}")
                with urllib.request.urlopen(image_url) as img_response:
                    image_data = img_response.read()
                
                # 生成文件名（使用filename_prefix和时间戳）
                timestamp = int(time.time())
                filename = f"{filename_prefix}_{timestamp}_{idx + 1}.png"
                
                # 存储图像数据
                self._generated_images[filename] = image_data
                
                # 创建图像信息（兼容ComfyUI格式）
                images_info.append({
                    'filename': filename,
                    'subfolder': '',
                    'type': 'output'
                })
                
                logger.info(f"  ✓ 图像已下载: {filename} ({len(image_data)} bytes)")
                
            except Exception as e:
                logger.error(f"下载图像失败: {e}")
                raise
        
        # 返回兼容格式的结果
        return {
            'images': {f'output_{i}': info for i, info in enumerate(images_info)}
        }
    
    def get_image(self, filename: str, subfolder: str = "", image_type: str = "output") -> bytes:
        """
        获取生成的图像数据
        
        Args:
            filename: 文件名
            subfolder: 子文件夹（Nano Banana不使用）
            image_type: 图像类型（Nano Banana不使用）
        
        Returns:
            图像字节数据
        """
        if not self._available:
            raise ImportError("NanoBananaClient不可用")
        
        if filename not in self._generated_images:
            raise FileNotFoundError(f"图像文件不存在: {filename}")
        
        return self._generated_images[filename]


class BatchImageGenerator:
    """批量图像生成器"""
    
    def __init__(
        self,
        generator: ImageGeneratorBase,
        output_dir: str = "./output",
        characters: Optional[List[Any]] = None,
        audio_tracks: Optional[List[Any]] = None,
        enable_prompt_expansion: bool = True,
        scenes: Optional[List[Any]] = None,
        scene_image_dir: Optional[str] = None,
        character_image_dir: Optional[str] = None,
        reference_image_dir: Optional[str] = None,
    ):
        """
        初始化批量图像生成器
        
        Args:
            generator: 图像生成器实例
            output_dir: 输出目录
            characters: 角色列表（用于提示词扩展）
            audio_tracks: 音频轨道列表（用于查找分镜对应的角色）
            enable_prompt_expansion: 是否启用提示词扩展
            scenes: 场景列表（用于按场景名解析参考图1：场景id.png）
            scene_image_dir: 场景图目录，下存 {场景id}.png
            character_image_dir: 角色图目录，下存 {角色id}.png
            reference_image_dir: 图像汇总「参考图」字段为相对路径时的基准目录
        """
        self.generator = generator
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        self.characters = characters or []
        self.scenes = scenes or []
        self.scene_image_dir = scene_image_dir
        self.character_image_dir = character_image_dir
        self.reference_image_dir = reference_image_dir or output_dir
        
        # 初始化提示词扩展器
        # 注意：不再使用音频轨道查找角色，只从提示词文本中识别角色，避免加错角色提示词
        self.prompt_expander = None
        if enable_prompt_expansion and characters:
            self.prompt_expander = PromptExpander(
                characters=characters,
                audio_tracks=[],  # 不使用音频轨道，只从提示词文本中识别角色
                enabled=True
            )
            logger.info(f"启用提示词扩展功能: {len(characters)} 个角色（仅从提示词文本中识别角色，不使用音频轨道）")
        else:
            logger.info("提示词扩展功能未启用")
    
    def generate_from_prompts(
        self,
        image_prompts: List[Any],  # List[ImagePrompt]
        generate_reference: bool = True,
        generate_first_frame: bool = False,
        generate_last_frame: bool = False,
        style_prefix: Optional[str] = None,
        seed: Optional[int] = None,
        steps: Optional[int] = None,
        cfg: Optional[float] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        episode_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        根据图像提示词列表批量生成图像
        
        Args:
            image_prompts: 图像提示词列表（ImagePrompt对象列表）
            generate_reference: 是否生成参考图（图像提示词）
            generate_first_frame: 是否生成首帧（首帧提示词）
            generate_last_frame: 是否生成末帧（末帧提示词）
            style_prefix: 风格前缀（可选）
            seed: 随机种子（可选）
            steps: 采样步数（可选）
            cfg: CFG值（可选）
            width: 图像宽度（可选）
            height: 图像高度（可选）
            episode_filter: 只处理指定剧集（如: EP01），如果为None则处理所有剧集
            
        Returns:
            生成结果列表
        """
        if not any([generate_reference, generate_first_frame, generate_last_frame]):
            logger.warning("未选择任何提示词类型，跳过图像生成")
            return []
        
        # 过滤图像提示词
        prompts_to_process = image_prompts
        if episode_filter:
            prompts_to_process = [p for p in prompts_to_process if p.剧集id == episode_filter]
            logger.info(f"过滤剧集 {episode_filter}: 找到 {len(prompts_to_process)} 个分镜")
        
        if not prompts_to_process:
            logger.warning("没有找到需要处理的图像提示词")
            return []
        
        # 连接生成器
        self.generator.connect()
        
        try:
            results = []
            total = len(prompts_to_process)
            shot_ids = [getattr(p, '分镜号', None) for p in prompts_to_process]
            logger.info(f"开始批量生成图像，共 {total} 个分镜")
            logger.info(f"分镜列表: {shot_ids}")
            logger.info(f"生成类型: 参考图={generate_reference}, 首帧={generate_first_frame}, 末帧={generate_last_frame}")
            
            for idx, image_prompt in enumerate(prompts_to_process, 1):
                result = {
                    '分镜号': image_prompt.分镜号,
                    '剧集id': image_prompt.剧集id,
                    '参考图': None,
                    '首帧': None,
                    '末帧': None,
                    'success': True,
                    'errors': []
                }
                
                try:
                    logger.info(f"\n[{idx}/{total}] 处理分镜: {image_prompt.分镜号}")
                    logger.debug(f"  场景内容: {image_prompt.场景内容[:50]}..." if len(image_prompt.场景内容) > 50 else f"  场景内容: {image_prompt.场景内容}")
                    
                    # 参考图解析：供「参考图」「首帧」「末帧」共用，使同一提示词下走相同工作流（有参考图=图编辑，无=文生图），生成一致
                    reference_images = None
                    if (generate_reference and image_prompt.图像提示词
                            or generate_first_frame and image_prompt.首帧提示词
                            or generate_last_frame and image_prompt.末帧提示词):
                        reference_images = _resolve_reference_images_for_edit(
                            image_prompt,
                            scenes=self.scenes,
                            characters=self.characters,
                            scene_image_dir=self.scene_image_dir,
                            character_image_dir=self.character_image_dir,
                            reference_image_dir=self.reference_image_dir,
                        )
                        if not reference_images and getattr(image_prompt, "参考图", None):
                            reference_images = _parse_reference_images(image_prompt.参考图)
                            if reference_images:
                                logger.info(f"  [参考图/首帧/末帧] 从「参考图」列逗号分隔解析得到: {reference_images}")
                    
                    # 生成参考图（图像提示词）；有参考图时用 act_02_qwen_Image_edit-aigc-3-api（1～3 张）
                    # 参考图1=场景id.png，参考图2=角色id.png，参考图3=图像汇总.参考图
                    if generate_reference and image_prompt.图像提示词:
                        expanded_prompt = self._expand_prompt_if_needed(
                            image_prompt.图像提示词,
                            image_prompt.分镜号
                        )
                        if reference_images:
                            logger.info(f"  [参考图] 共 {len(reference_images)} 张，将走 有参考图 工作流，并自本地上传至 ComfyUI: {reference_images}")
                            logger.info(f"  [工作流] 使用: act_02_qwen_Image_edit-aigc-3-api.json")
                        else:
                            logger.info(f"  [参考图] 无可用参考图，将走 默认文生图（无参考图）")
                            logger.info(f"  [工作流] 使用: 默认文生图 (z_image_workflow.json)")
                        result['参考图'] = self._generate_single_image(
                            expanded_prompt,
                            f"{image_prompt.分镜号}_ref",
                            "参考图",
                            style_prefix, seed, steps, cfg, width, height,
                            result,
                            reference_images=reference_images if reference_images else None,
                        )
                    
                    # 生成首帧：与参考图使用同一 reference_images，使「首帧提示词」与「图像提示词」相同时生成一致
                    if generate_first_frame and image_prompt.首帧提示词:
                        expanded_prompt = self._expand_prompt_if_needed(
                            image_prompt.首帧提示词,
                            image_prompt.分镜号
                        )
                        result['首帧'] = self._generate_single_image(
                            expanded_prompt,
                            f"{image_prompt.分镜号}_first",
                            "首帧",
                            style_prefix, seed, steps, cfg, width, height,
                            result,
                            reference_images=reference_images if reference_images else None,
                        )
                    
                    # 生成末帧：与参考图使用同一 reference_images，使「末帧提示词」与「图像提示词」相同时生成一致
                    if generate_last_frame and image_prompt.末帧提示词:
                        expanded_prompt = self._expand_prompt_if_needed(
                            image_prompt.末帧提示词,
                            image_prompt.分镜号
                        )
                        result['末帧'] = self._generate_single_image(
                            expanded_prompt,
                            f"{image_prompt.分镜号}_last",
                            "末帧",
                            style_prefix, seed, steps, cfg, width, height,
                            result,
                            reference_images=reference_images if reference_images else None,
                        )
                    
                    logger.info(f"  ✓ 完成: {image_prompt.分镜号}")
                    
                except Exception as e:
                    error_msg = f"处理分镜 {image_prompt.分镜号} 时出错: {e}"
                    logger.error(f"  ✗ {error_msg}")
                    result['errors'].append(error_msg)
                    result['success'] = False
                    import traceback
                    traceback.print_exc()
                
                results.append(result)
            
            # 统计结果
            successful = sum(1 for r in results if r['success'])
            failed = len(results) - successful
            logger.info("\n" + "="*80)
            logger.info("批量生成图像完成!")
            logger.info(f"总计: {len(results)} 个分镜")
            logger.info(f"成功: {successful} 个")
            logger.info(f"失败: {failed} 个")
            
            if failed > 0:
                logger.info("\n失败的分镜:")
                for r in results:
                    if not r['success']:
                        logger.info(f"  - {r['分镜号']}: {', '.join(r['errors'])}")
            
            return results
            
        finally:
            self.generator.disconnect()
    
    def _expand_prompt_if_needed(self, prompt: str, shot_id: str) -> str:
        """
        如果需要，扩展提示词
        
        Args:
            prompt: 原始提示词
            shot_id: 分镜号
            
        Returns:
            扩展后的提示词
        """
        if not self.prompt_expander:
            return prompt
        
        try:
            return self.prompt_expander.expand_prompt(prompt, shot_id=shot_id)
        except Exception as e:
            logger.warning(f"扩展提示词时出错: {e}，使用原始提示词")
            return prompt
    
    def _generate_single_image(
        self,
        prompt: str,
        filename_prefix: str,
        image_type_name: str,
        style_prefix: Optional[str],
        seed: Optional[int],
        steps: Optional[int],
        cfg: Optional[float],
        width: Optional[int],
        height: Optional[int],
        result: Dict[str, Any],
        reference_images: Optional[List[str]] = None,
    ) -> Optional[str]:
        """
        生成单张图像
        
        Args:
            prompt: 提示词
            filename_prefix: 文件名前缀
            image_type_name: 图像类型名称（用于日志）
            style_prefix: 风格前缀
            seed: 随机种子
            steps: 采样步数
            cfg: CFG值
            width: 图像宽度
            height: 图像高度
            result: 结果字典（用于记录错误）
            reference_images: 参考图路径列表，1/2/3 张时使用 Qwen Image Edit 工作流（可选）
            
        Returns:
            生成的图像文件路径，如果失败返回None
        """
        logger.info(f"  生成{image_type_name}..." + (f"（{len(reference_images)} 张参考图）" if reference_images else ""))
        try:
            gen_result = self.generator.generate_image(
                prompt=prompt,
                filename_prefix=filename_prefix,
                style_prefix=style_prefix,
                seed=seed,
                steps=steps,
                cfg=cfg,
                width=width,
                height=height,
                reference_images=reference_images,
            )
            
            # 保存图片（文件名与以前一致：{filename_prefix}_{5位数字}.png，如 EP01_SQ01_ref_00018.png）
            if gen_result.get('images'):
                if not hasattr(self, '_ref_save_counter'):
                    self._ref_save_counter = 0
                for node_id, image_info in gen_result['images'].items():
                    image_data = self.generator.get_image(
                        image_info['filename'],
                        image_info.get('subfolder', ''),
                        image_info.get('type', 'output')
                    )
                    self._ref_save_counter += 1
                    output_filename = f"{filename_prefix}_{self._ref_save_counter:05d}.png"
                    output_path = os.path.join(self.output_dir, output_filename)
                    with open(output_path, 'wb') as f:
                        f.write(image_data)
                    logger.info(f"    ✓ 保存{image_type_name}: {output_path}")
                    return output_path
            else:
                error_msg = f"生成{image_type_name}失败: 未返回图像"
                logger.warning(f"    ⚠ {error_msg}")
                result['errors'].append(error_msg)
                result['success'] = False
                return None
                
        except Exception as e:
            error_msg = f"生成{image_type_name}失败: {e}"
            logger.error(f"    ✗ {error_msg}")
            result['errors'].append(error_msg)
            result['success'] = False
            return None


def create_generator(
    generator_type: str = "comfyui",
    server_address: str = "127.0.0.1:8188",
    **kwargs
) -> ImageGeneratorBase:
    """
    工厂函数：创建图像生成器
    
    Args:
        generator_type: 生成器类型 ("comfyui", "nanobanana", 或其他)
        server_address: 服务器地址（用于comfyui类型）
        **kwargs: 其他参数（用于扩展）
            - api_key: Nano Banana API密钥（用于nanobanana类型）
            - host: Nano Banana API服务器地址（用于nanobanana类型）
            - config_path: Nano Banana配置文件路径（用于nanobanana类型）
            - model: Nano Banana模型名称（用于nanobanana类型，默认: "nano-banana-fast"）
            - aspect_ratio: Nano Banana图像比例（用于nanobanana类型，默认: "auto"）
            - image_size: Nano Banana图像大小（用于nanobanana类型，默认: "1K"）
        
    Returns:
        图像生成器实例
    """
    generator_type_lower = generator_type.lower()
    
    if generator_type_lower == "comfyui":
        wf = kwargs.get("txt2img_workflow_path")
        return ComfyUIImageGenerator(
            server_address=server_address,
            txt2img_workflow_path=wf,
        )
    elif generator_type_lower == "nanobanana":
        return NanoBananaImageGenerator(
            api_key=kwargs.get('api_key'),
            host=kwargs.get('host'),
            config_path=kwargs.get('config_path'),
            model=kwargs.get('model', 'nano-banana-fast'),
            aspect_ratio=kwargs.get('aspect_ratio', 'auto'),
            image_size=kwargs.get('image_size', '1K')
        )
    else:
        raise ValueError(f"不支持的生成器类型: {generator_type}")


# 为了向后兼容，提供便捷函数
def batch_generate_images_from_excel_data(
    image_prompts: List[Any],
    output_dir: str = "./output",
    generate_reference: bool = True,
    generate_first_frame: bool = False,
    generate_last_frame: bool = False,
    comfyui_server: str = "127.0.0.1:8188",
    style_prefix: Optional[str] = None,
    seed: Optional[int] = None,
    steps: Optional[int] = None,
    cfg: Optional[float] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
    episode_filter: Optional[str] = None,
    generator_type: str = "comfyui",
    provider_profile: Optional[str] = None,
    txt2img_workflow_path: Optional[str] = None,
    characters: Optional[List[Any]] = None,
    audio_tracks: Optional[List[Any]] = None,
    enable_prompt_expansion: bool = True,
    scenes: Optional[List[Any]] = None,
    scene_image_dir: Optional[str] = None,
    character_image_dir: Optional[str] = None,
    reference_image_dir: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    便捷函数：从Excel数据批量生成图像。
    有参考图时使用 act_02_qwen_Image_edit-aigc-3-api 工作流（1～3 张）：
    参考图1=场景id.png，参考图2=角色id.png，参考图3=图像汇总.参考图。
    
    Args:
        image_prompts: 图像提示词列表
        output_dir: 输出目录
        generate_reference: 是否生成参考图
        generate_first_frame: 是否生成首帧
        generate_last_frame: 是否生成末帧
        comfyui_server: ComfyUI服务器地址
        style_prefix: 风格前缀
        seed: 随机种子
        steps: 采样步数
        cfg: CFG值
        width: 图像宽度
        height: 图像高度
        episode_filter: 剧集过滤
        generator_type: 生成器类型
        characters: 角色列表（用于提示词扩展与参考图2=角色id.png）
        audio_tracks: 音频轨道列表（用于查找分镜对应的角色）
        enable_prompt_expansion: 是否启用提示词扩展
        scenes: 场景列表（用于参考图1=场景id.png）
        scene_image_dir: 场景图目录，下存 {场景id}.png
        character_image_dir: 角色图目录，下存 {角色id}.png
        reference_image_dir: 图像汇总「参考图」为相对路径时的基准目录
        provider_profile: 可选，generation_framework 中的图像 profile_id（如 comfyui.z_image_qwen）
        txt2img_workflow_path: 可选，ComfyUI 文生图工作流 JSON 绝对或相对 lib 的路径
        
    Returns:
        生成结果列表
    """
    try:
        from generation_framework import (
            create_image_generator_by_profile,
            resolve_image_profile_id,
        )

        pid = resolve_image_profile_id(provider_profile, generator_type)
        gen_kw: Dict[str, Any] = {}
        if txt2img_workflow_path:
            gen_kw["txt2img_workflow_path"] = txt2img_workflow_path
        generator = create_image_generator_by_profile(pid, comfyui_server, **gen_kw)
    except ImportError:
        generator = create_generator(
            generator_type,
            comfyui_server,
            txt2img_workflow_path=txt2img_workflow_path,
        )
    except ValueError as e:
        logger.warning("%s，回退 create_generator", e)
        generator = create_generator(
            generator_type,
            comfyui_server,
            txt2img_workflow_path=txt2img_workflow_path,
        )
    batch_generator = BatchImageGenerator(
        generator,
        output_dir,
        characters=characters,
        audio_tracks=audio_tracks,
        enable_prompt_expansion=enable_prompt_expansion,
        scenes=scenes,
        scene_image_dir=scene_image_dir,
        character_image_dir=character_image_dir,
        reference_image_dir=reference_image_dir,
    )
    return batch_generator.generate_from_prompts(
        image_prompts=image_prompts,
        generate_reference=generate_reference,
        generate_first_frame=generate_first_frame,
        generate_last_frame=generate_last_frame,
        style_prefix=style_prefix,
        seed=seed,
        steps=steps,
        cfg=cfg,
        width=width,
        height=height,
        episode_filter=episode_filter
    )

