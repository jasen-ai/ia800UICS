"""
Excel数据读取器 - 用于读取和解析剧集数据Excel文件
支持读取音频汇总、角色汇总、场景汇总、图像汇总和剪辑汇总工作表
支持从JSON剧本文件导入数据
"""
import pandas as pd
import os
import json
import logging
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from pathlib import Path

# 可选导入图像生成器，如果不存在则跳过图像生成功能
try:
    from image_generator import batch_generate_images_from_excel_data, create_generator
    IMAGE_GENERATOR_AVAILABLE = True
except ImportError:
    IMAGE_GENERATOR_AVAILABLE = False
    batch_generate_images_from_excel_data = None
    create_generator = None

# 可选导入视频生成器，如果不存在则跳过视频生成功能
try:
    from video_generator import batch_generate_videos_from_excel_data, create_video_generator
    VIDEO_GENERATOR_AVAILABLE = True
except ImportError:
    VIDEO_GENERATOR_AVAILABLE = False
    batch_generate_videos_from_excel_data = None
    create_video_generator = None

# 可选导入音频生成器，如果不存在则跳过音频生成功能
try:
    from audio_generator import batch_generate_audio_from_excel_data, create_audio_generator
    AUDIO_GENERATOR_AVAILABLE = True
except ImportError:
    AUDIO_GENERATOR_AVAILABLE = False
    batch_generate_audio_from_excel_data = None
    create_audio_generator = None


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# UICS 模块所在目录，用于默认参考图目录（scenes、characters、output 均在 UICS 下）
UICS_BASE_DIR = os.path.dirname(os.path.abspath(__file__))


@dataclass
class AudioTrack:
    """音频轨道数据"""
    剧集id: str
    分镜号: str
    场景内容: str
    场景图片提示词: str
    剧情角色: Optional[str] = None
    音频角色: Optional[str] = None
    音频情感: Optional[str] = None
    音频id: Optional[str] = None
    音频图片id: Optional[str] = None
    音频内容: Optional[str] = None
    时长: Optional[float] = None
    输出视频id: Optional[str] = None
    备注: Optional[str] = None
    参考样本: Optional[str] = None


@dataclass
class Character:
    """角色数据"""
    角色名: str
    角色id: Optional[Union[int, str]] = None  # 支持数字或字符串如 CHAR-8EBF5C5E
    音频id: Optional[str] = None
    参考音色: Optional[str] = None  # 用于音频生成的参考音频文件路径
    角色描述: Optional[str] = None
    视觉特征: Optional[str] = None
    图像提示词: Optional[str] = None
    出现章节: Optional[str] = None
    出现次数: Optional[int] = None
    出现剧集及分镜号: Optional[str] = None
    备注: Optional[str] = None
    参考图: Optional[str] = None  # 用于图像生成的参考图文件路径


@dataclass
class Scene:
    """场景数据"""
    场景名: str
    剧集id: Optional[str] = None
    分镜号: Optional[str] = None
    场景id: Optional[Union[int, str]] = None  # 支持数字或字符串如 LOC-05DEECE7
    场景类型: Optional[str] = None
    场景描述: Optional[str] = None
    视觉特征: Optional[str] = None
    图像提示词: Optional[str] = None
    位置细节: Optional[str] = None
    出现章节: Optional[str] = None
    出现次数: Optional[int] = None
    出现剧集及分镜号: Optional[str] = None
    备注: Optional[str] = None
    参考图: Optional[str] = None


@dataclass
class ImagePrompt:
    """图像提示词数据（无默认值字段必须在有默认值字段前）"""
    剧集id: str
    分镜号: str
    场景内容: str
    场景名: Optional[str] = None  # 场景内容前的列
    角色: Optional[str] = None  # 场景内容后的列
    镜头类型: Optional[str] = None
    图像提示词: Optional[str] = None
    首帧提示词: Optional[str] = None
    末帧提示词: Optional[str] = None
    视频提示词: Optional[str] = None
    备注: Optional[str] = None  # 视频提示词后的列
    参考图: Optional[str] = None  # 视频提示词后的列


@dataclass
class EditTimeline:
    """剪辑时间线数据"""
    剧集id: str
    分镜号: str
    全局开始时间: float
    全局结束时间: float
    时长: float
    视觉ID: str
    音频ID列表: str


class ExcelDataReader:
    """Excel数据读取器"""
    
    def __init__(self, excel_path: str, debug: bool = True):
        """
        初始化Excel读取器
        
        Args:
            excel_path: Excel文件路径
            debug: 是否打印调试信息
        """
        self.excel_path = Path(excel_path)
        if not self.excel_path.exists():
            raise FileNotFoundError(f"Excel文件不存在: {excel_path}")
        
        self.debug = debug
        self.audio_tracks: List[AudioTrack] = []
        self.characters: List[Character] = []
        self.scenes: List[Scene] = []
        self.image_prompts: List[ImagePrompt] = []
        self.edit_timelines: List[EditTimeline] = []
        
        if self.debug:
            logger.info(f"初始化Excel读取器: {excel_path}")
    
    def read_all(self) -> Dict[str, Any]:
        """
        读取所有工作表数据
        
        Returns:
            包含所有数据的字典
        """
        if self.debug:
            logger.info("开始读取Excel文件...")
        
        try:
            # 读取所有工作表
            excel_file = pd.ExcelFile(self.excel_path)
            
            if self.debug:
                logger.info(f"发现工作表: {excel_file.sheet_names}")
            
            # 读取各个工作表
            self._read_audio_summary(excel_file)
            self._read_character_summary(excel_file)
            self._read_scene_summary(excel_file)
            self._read_image_prompts(excel_file)
            self._read_edit_summary(excel_file)
            
            if self.debug:
                self._print_summary()
            
            return {
                'audio_tracks': self.audio_tracks,
                'characters': self.characters,
                'scenes': self.scenes,
                'image_prompts': self.image_prompts,
                'edit_timelines': self.edit_timelines
            }
            
        except Exception as e:
            logger.error(f"读取Excel文件时出错: {e}")
            raise
    
    def _read_audio_summary(self, excel_file: pd.ExcelFile):
        """读取音频汇总工作表"""
        sheet_name = '音频汇总'
        if sheet_name not in excel_file.sheet_names:
            logger.warning(f"未找到工作表: {sheet_name}")
            return
        
        if self.debug:
            logger.info(f"读取工作表: {sheet_name}")
        
        df = pd.read_excel(excel_file, sheet_name=sheet_name)
        
        if self.debug:
            logger.info(f"  读取到 {len(df)} 行数据")
            logger.debug(f"  列名: {list(df.columns)}")
        
        for idx, row in df.iterrows():
            try:
                audio_track = AudioTrack(
                    剧集id=str(row.get('剧集id', '')),
                    分镜号=str(row.get('分镜号', '')),
                    场景内容=str(row.get('场景内容', '')),
                    场景图片提示词=str(row.get('场景图片提示词', '')),
                    剧情角色=self._safe_str(row.get('剧情角色')),
                    音频角色=self._safe_str(row.get('音频角色')),
                    音频情感=self._safe_str(row.get('音频情感')),
                    音频id=self._safe_str(row.get('音频id')),
                    音频图片id=self._safe_str(row.get('音频图片id')),
                    音频内容=self._safe_str(row.get('音频内容')),
                    时长=self._safe_float(row.get('时长')),
                    输出视频id=self._safe_str(row.get('输出视频id')),
                    备注=self._safe_str(row.get('备注')),
                    参考样本=self._safe_str(row.get('参考样本'))
                )
                self.audio_tracks.append(audio_track)
            except Exception as e:
                logger.warning(f"  解析第 {idx+1} 行数据时出错: {e}")
    
    def _read_character_summary(self, excel_file: pd.ExcelFile):
        """读取角色汇总工作表"""
        sheet_name = '角色汇总'
        if sheet_name not in excel_file.sheet_names:
            logger.warning(f"未找到工作表: {sheet_name}")
            return
        
        if self.debug:
            logger.info(f"读取工作表: {sheet_name}")
        
        df = pd.read_excel(excel_file, sheet_name=sheet_name)
        
        if self.debug:
            logger.info(f"  读取到 {len(df)} 行数据")
        # 便于排查“无角色id”：打印表头及首行解析出的角色id
        if df is not None and len(df) > 0:
            first = df.iloc[0]
            cid = self._get_scene_or_char_id_from_row(first, "角色id", "角色ID", "角色 id", "ID", "id", "编号", "序号")
            logger.info(f"  [角色汇总] 表头: {df.columns.tolist()}, 首行 角色id 解析结果: {cid}")
        
        for idx, row in df.iterrows():
            try:
                character = Character(
                    角色名=str(row.get('角色名', '')),
                    角色id=self._get_scene_or_char_id_from_row(row, '角色id', '角色ID', '角色 id', 'ID', 'id', '编号', '序号'),
                    音频id=self._safe_str(row.get('音频id')),
                    参考音色=self._safe_str(row.get('参考音色')) or self._safe_str(row.get('参考图')),  # 新格式列名为参考音色（音频id后），兼容旧列名参考图
                    角色描述=self._safe_str(row.get('角色描述')),
                    视觉特征=self._safe_str(row.get('视觉特征')),
                    图像提示词=self._safe_str(row.get('图像提示词')),
                    出现章节=self._safe_str(row.get('出现章节')),
                    出现次数=self._safe_int(row.get('出现次数')),
                    出现剧集及分镜号=self._safe_str(row.get('出现剧集及分镜号')),
                    备注=self._safe_str(row.get('备注')),
                    参考图=self._safe_str(row.get('参考图')) or self._safe_str(row.get('参考图.1')) or self._safe_str(row.get('参卡图'))  # 新格式末尾列为参考图，兼容参考图.1、参卡图
                )
                self.characters.append(character)
            except Exception as e:
                logger.warning(f"  解析第 {idx+1} 行数据时出错: {e}")
    
    def _read_scene_summary(self, excel_file: pd.ExcelFile):
        """读取场景汇总工作表"""
        sheet_name = '场景汇总'
        if sheet_name not in excel_file.sheet_names:
            logger.warning(f"未找到工作表: {sheet_name}")
            return
        
        if self.debug:
            logger.info(f"读取工作表: {sheet_name}")
        
        df = pd.read_excel(excel_file, sheet_name=sheet_name)
        
        if self.debug:
            logger.info(f"  读取到 {len(df)} 行数据")
        # 便于排查“无场景id”：打印表头及首行解析出的场景id
        if df is not None and len(df) > 0:
            first = df.iloc[0]
            sid = self._get_scene_or_char_id_from_row(first, "场景id", "场景ID", "场景 id", "ID", "id", "编号", "序号")
            logger.info(f"  [场景汇总] 表头: {df.columns.tolist()}, 首行 场景id 解析结果: {sid}")
        
        for idx, row in df.iterrows():
            try:
                scene = Scene(
                    场景名=str(row.get('场景名', '')),
                    剧集id=self._safe_str(row.get('剧集id')),
                    分镜号=self._safe_str(row.get('分镜号')),
                    场景id=self._get_scene_or_char_id_from_row(row, '场景id', '场景ID', '场景 id', 'ID', 'id', '编号', '序号'),
                    场景类型=self._safe_str(row.get('场景类型')),
                    场景描述=self._safe_str(row.get('场景描述')),
                    视觉特征=self._safe_str(row.get('视觉特征')),
                    图像提示词=self._safe_str(row.get('图像提示词')),
                    位置细节=self._safe_str(row.get('位置细节')),
                    出现章节=self._safe_str(row.get('出现章节')),
                    出现次数=self._safe_int(row.get('出现次数')),
                    出现剧集及分镜号=self._safe_str(row.get('出现剧集及分镜号')),
                    备注=self._safe_str(row.get('备注')),
                    参考图=self._safe_str(row.get('参考图'))
                )
                self.scenes.append(scene)
            except Exception as e:
                logger.warning(f"  解析第 {idx+1} 行数据时出错: {e}")
    
    def _read_image_prompts(self, excel_file: pd.ExcelFile):
        """读取图像汇总工作表（兼容旧名称'图像提示词'）"""
        # 优先使用新名称"图像汇总"，如果不存在则尝试旧名称"图像提示词"
        sheet_name = '图像汇总'
        if sheet_name not in excel_file.sheet_names:
            # 向后兼容：尝试旧名称
            old_sheet_name = '图像提示词'
            if old_sheet_name in excel_file.sheet_names:
                sheet_name = old_sheet_name
                logger.info(f"使用旧工作表名称: {old_sheet_name}（建议更新为'图像汇总'）")
            else:
                logger.warning(f"未找到工作表: {sheet_name} 或 {old_sheet_name}")
                return
        
        if self.debug:
            logger.info(f"读取工作表: {sheet_name}")
        
        df = pd.read_excel(excel_file, sheet_name=sheet_name)
        
        if self.debug:
            logger.info(f"  读取到 {len(df)} 行数据")
        
        for idx, row in df.iterrows():
            try:
                image_prompt = ImagePrompt(
                    剧集id=str(row.get('剧集id', '')),
                    分镜号=str(row.get('分镜号', '')),
                    场景名=self._safe_str(row.get('场景名')),
                    场景内容=str(row.get('场景内容', '')),
                    角色=self._safe_str(row.get('角色')),
                    镜头类型=self._safe_str(row.get('镜头类型')),
                    图像提示词=self._safe_str(row.get('图像提示词')),
                    首帧提示词=self._safe_str(row.get('首帧提示词')),
                    末帧提示词=self._safe_str(row.get('末帧提示词')),
                    视频提示词=self._safe_str(row.get('视频提示词')),
                    备注=self._safe_str(row.get('备注')),
                    参考图=self._safe_str(row.get('参考图'))
                )
                self.image_prompts.append(image_prompt)
            except Exception as e:
                logger.warning(f"  解析第 {idx+1} 行数据时出错: {e}")
    
    def _read_edit_summary(self, excel_file: pd.ExcelFile):
        """读取剪辑汇总工作表"""
        sheet_name = '剪辑汇总'
        if sheet_name not in excel_file.sheet_names:
            logger.warning(f"未找到工作表: {sheet_name}")
            return
        
        if self.debug:
            logger.info(f"读取工作表: {sheet_name}")
        
        df = pd.read_excel(excel_file, sheet_name=sheet_name)
        
        if self.debug:
            logger.info(f"  读取到 {len(df)} 行数据")
        
        for idx, row in df.iterrows():
            try:
                edit_timeline = EditTimeline(
                    剧集id=str(row.get('剧集id', '')),
                    分镜号=str(row.get('分镜号', '')),
                    全局开始时间=float(row.get('全局开始时间(秒)', 0.0)),
                    全局结束时间=float(row.get('全局结束时间(秒)', 0.0)),
                    时长=float(row.get('时长(秒)', 0.0)),
                    视觉ID=str(row.get('视觉ID', '')),
                    音频ID列表=str(row.get('音频ID列表', ''))
                )
                self.edit_timelines.append(edit_timeline)
            except Exception as e:
                logger.warning(f"  解析第 {idx+1} 行数据时出错: {e}")
    
    def _safe_str(self, value: Any) -> Optional[str]:
        """安全转换为字符串"""
        if pd.isna(value) or value is None:
            return None
        return str(value).strip() if str(value).strip() else None
    
    def _safe_int(self, value: Any) -> Optional[int]:
        """安全转换为整数"""
        if pd.isna(value) or value is None:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None
    
    def _get_int_from_row(self, row: Any, *column_names: str) -> Optional[int]:
        """从行中按多个列名依次尝试取整数值（兼容 场景id/场景ID/ID、角色id/角色ID 等）。"""
        for key in column_names:
            val = self._safe_int(row.get(key))
            if val is not None:
                return val
        # 按列名规范化匹配（兼容表头含空格、全角等）
        try:
            wanted_norm = {str(c).strip().lower() for c in column_names if c}
            for key in getattr(row, "index", None) or []:
                if str(key).strip().lower() in wanted_norm:
                    val = self._safe_int(row.get(key))
                    if val is not None:
                        return val
        except Exception:
            pass
        return None
    
    def _get_str_from_row(self, row: Any, *column_names: str) -> Optional[str]:
        """从行中按多个列名依次尝试取非空字符串（用于 场景id/角色id 为 LOC-xxx、CHAR-xxx 等）。"""
        for key in column_names:
            s = self._safe_str(row.get(key))
            if s:
                return s
        try:
            wanted_norm = {str(c).strip().lower() for c in column_names if c}
            for key in getattr(row, "index", None) or []:
                if str(key).strip().lower() in wanted_norm:
                    s = self._safe_str(row.get(key))
                    if s:
                        return s
        except Exception:
            pass
        return None
    
    def _get_scene_or_char_id_from_row(self, row: Any, *column_names: str) -> Optional[Union[int, str]]:
        """先尝试整数，再尝试字符串（兼容 场景id=LOC-xxx、角色id=CHAR-xxx）。"""
        val = self._get_int_from_row(row, *column_names)
        if val is not None:
            return val
        return self._get_str_from_row(row, *column_names)
    
    def _safe_float(self, value: Any) -> Optional[float]:
        """安全转换为浮点数"""
        if pd.isna(value) or value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
    
    def _print_summary(self):
        """打印数据摘要"""
        print("\n" + "="*80)
        print("Excel数据读取摘要")
        print("="*80)
        print(f"音频轨道数量: {len(self.audio_tracks)}")
        print(f"角色数量: {len(self.characters)}")
        print(f"场景数量: {len(self.scenes)}")
        print(f"图像提示词数量: {len(self.image_prompts)}")
        print(f"剪辑时间线数量: {len(self.edit_timelines)}")
        print("="*80)
        
        # 按剧集统计
        if self.audio_tracks:
            episodes = set(track.剧集id for track in self.audio_tracks)
            print(f"\n剧集列表: {sorted(episodes)}")
        
        # 显示前几个示例
        if self.debug:
            print("\n--- 音频轨道示例 (前3条) ---")
            for i, track in enumerate(self.audio_tracks[:3], 1):
                print(f"\n{i}. 剧集: {track.剧集id}, 分镜: {track.分镜号}")
                print(f"   场景内容: {track.场景内容[:50]}..." if len(track.场景内容) > 50 else f"   场景内容: {track.场景内容}")
                if track.音频id:
                    print(f"   音频ID: {track.音频id}, 时长: {track.时长}秒")
            
            if self.characters:
                print("\n--- 角色示例 (前3个) ---")
                for i, char in enumerate(self.characters[:3], 1):
                    print(f"\n{i}. {char.角色名}")
                    if char.出现次数:
                        print(f"   出现次数: {char.出现次数}")
            
            if self.scenes:
                print("\n--- 场景示例 (前3个) ---")
                for i, scene in enumerate(self.scenes[:3], 1):
                    print(f"\n{i}. {scene.场景名}")
                    if scene.出现次数:
                        print(f"   出现次数: {scene.出现次数}")
    
    def get_audio_tracks_by_episode(self, episode_id: str) -> List[AudioTrack]:
        """根据剧集ID获取音频轨道"""
        return [track for track in self.audio_tracks if track.剧集id == episode_id]
    
    def get_audio_tracks_by_shot(self, shot_id: str) -> List[AudioTrack]:
        """根据分镜号获取音频轨道"""
        return [track for track in self.audio_tracks if track.分镜号 == shot_id]
    
    def get_image_prompt_by_shot(self, shot_id: str) -> Optional[ImagePrompt]:
        """根据分镜号获取图像提示词"""
        for prompt in self.image_prompts:
            if prompt.分镜号 == shot_id:
                return prompt
        return None
    
    def get_edit_timeline_by_shot(self, shot_id: str) -> Optional[EditTimeline]:
        """根据分镜号获取剪辑时间线"""
        for timeline in self.edit_timelines:
            if timeline.分镜号 == shot_id:
                return timeline
        return None
    
    def get_character_by_name(self, name: str) -> Optional[Character]:
        """根据角色名获取角色信息"""
        for char in self.characters:
            if char.角色名 == name:
                return char
        return None
    
    def get_scene_by_name(self, name: str) -> Optional[Scene]:
        """根据场景名获取场景信息"""
        for scene in self.scenes:
            if scene.场景名 == name:
                return scene
        return None
    
    def batch_generate_images_from_prompts(
        self,
        output_dir: str = "./output",
        generate_reference: bool = True,
        generate_first_frame: bool = False,
        generate_last_frame: bool = False,
        comfyui_server: str = "127.0.0.1:8188",
        style_prefix: str = None,
        seed: int = None,
        steps: int = None,
        cfg: float = None,
        width: int = None,
        height: int = None,
        episode_filter: Optional[str] = None,
        generator_type: str = "comfyui",
        enable_prompt_expansion: bool = True,
        scene_image_dir: Optional[str] = None,
        character_image_dir: Optional[str] = None,
        reference_image_dir: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        根据图像汇总工作表中的提示词批量生成图像。
        有参考图时使用 act_02_qwen_Image_edit-aigc-3-api 工作流（1～3 张）：
        参考图1=场景名对应场景id的png，参考图2=角色对应角色id的png，参考图3=图像汇总.参考图。

        Args:
            output_dir: 输出目录
            generate_reference: 是否生成参考图（图像提示词）
            scene_image_dir: 场景图目录，下存 {场景id}.png 或 场景名.png，用于参考图1
            character_image_dir: 角色图目录，下存 {角色id}.png 或 角色名.png，用于参考图2
            reference_image_dir: 图像汇总「参考图」列为相对路径时的基准目录（默认用 output_dir）
            ...其余同前
        """
        if not IMAGE_GENERATOR_AVAILABLE:
            raise ImportError("图像生成器模块不可用，请确保image_generator.py存在")

        # 在 UICS 下运行时，参考图目录默认为 UICS 下的 scenes、characters、output
        _scene_dir = scene_image_dir if scene_image_dir is not None else os.path.join(UICS_BASE_DIR, "scenes")
        _char_dir = character_image_dir if character_image_dir is not None else os.path.join(UICS_BASE_DIR, "characters")
        _ref_dir = reference_image_dir or output_dir

        return batch_generate_images_from_excel_data(
            image_prompts=self.image_prompts,
            output_dir=output_dir,
            generate_reference=generate_reference,
            generate_first_frame=generate_first_frame,
            generate_last_frame=generate_last_frame,
            comfyui_server=comfyui_server,
            style_prefix=style_prefix,
            seed=seed,
            steps=steps,
            cfg=cfg,
            width=width,
            height=height,
            episode_filter=episode_filter,
            generator_type=generator_type,
            characters=self.characters,
            audio_tracks=self.audio_tracks,
            enable_prompt_expansion=enable_prompt_expansion,
            scenes=self.scenes,
            scene_image_dir=_scene_dir,
            character_image_dir=_char_dir,
            reference_image_dir=_ref_dir,
        )
    
    def batch_generate_videos_from_prompts(
        self,
        output_dir: str = "./output",
        comfyui_server: str = "127.0.0.1:8188",
        workflow_path: Optional[str] = None,
        episode_filter: Optional[str] = None,
        shot_filter: Optional[str] = None,
        negative_prompt: Optional[str] = None,
        seed: int = None,
        steps: int = None,
        cfg: float = None,
        width: int = None,
        height: int = None,
        length: int = None,
        fps: float = None,
        reference_image_dir: Optional[str] = None,
        generator_type: str = "comfyui",
        enable_prompt_expansion: bool = True,
        sora_api_key: Optional[str] = None,
        sora_host: str = "https://grsai.dakka.com.cn",
        sora_config_path: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        根据图像汇总工作表中的视频提示词批量生成视频
        
        Args:
            output_dir: 输出目录
            comfyui_server: ComfyUI服务器地址（用于comfyui类型）
            workflow_path: 工作流文件路径（可选，用于comfyui类型）
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
            reference_image_dir: 参考图像目录（可选，用于查找对应的参考图）
            generator_type: 生成器类型（默认: "comfyui"，可选: "sora"）
            enable_prompt_expansion: 是否启用提示词扩展（根据角色自动附加角色图像提示词）
            sora_api_key: Sora API密钥（用于sora类型，如果为None则从配置文件读取）
            sora_host: Sora API服务器地址（用于sora类型）
            sora_config_path: Sora配置文件路径（用于sora类型）
            
        Returns:
            生成结果列表
        """
        if not VIDEO_GENERATOR_AVAILABLE:
            raise ImportError("视频生成器模块不可用，请确保video_generator.py存在")
        
        # 委托给视频生成器模块，传入角色数据用于提示词扩展
        return batch_generate_videos_from_excel_data(
            image_prompts=self.image_prompts,
            output_dir=output_dir,
            comfyui_server=comfyui_server,
            workflow_path=workflow_path,
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
            reference_image_dir=reference_image_dir,
            generator_type=generator_type,
            characters=self.characters,
            enable_prompt_expansion=enable_prompt_expansion,
            sora_api_key=sora_api_key,
            sora_host=sora_host,
            sora_config_path=sora_config_path
        )
    
    def batch_generate_audio_from_tracks(
        self,
        output_dir: str = "./output",
        generator_type: str = "volcengine",
        encoding: str = "wav",
        episode_filter: Optional[str] = None,
        shot_filter: Optional[str] = None,
        config_path: Optional[str] = None,
        emotion: Optional[str] = None,
        emotion_map: Optional[Dict[str, str]] = None,
        **generator_kwargs
    ) -> List[Dict[str, Any]]:
        """
        根据音频汇总工作表中的数据批量生成音频
        
        Args:
            output_dir: 输出目录
            generator_type: 生成器类型（默认: "volcengine"）
            encoding: 音频编码格式（默认: "wav"）
            episode_filter: 只处理指定剧集（如: EP01），如果为None则处理所有剧集
            shot_filter: 只处理指定分镜（如: EP01_SQ01），如果为None则处理所有分镜
            config_path: 配置文件路径（可选）
            emotion: 默认音色情感（可选）
            emotion_map: 情感映射字典（可选，key为角色名，value为对应的emotion值）
            **generator_kwargs: 生成器特定参数（如appid, access_token等，优先级高于配置文件）
            
        Returns:
            生成结果列表
        """
        if not AUDIO_GENERATOR_AVAILABLE:
            raise ImportError("音频生成器模块不可用，请确保audio_generator.py存在")
        
        # 委托给音频生成器模块，传入角色数据用于查找角色的音频id
        return batch_generate_audio_from_excel_data(
            audio_tracks=self.audio_tracks,
            characters=self.characters,
            generator_type=generator_type,
            output_dir=output_dir,
            encoding=encoding,
            episode_filter=episode_filter,
            shot_filter=shot_filter,
            config_path=config_path,
            emotion=emotion,
            emotion_map=emotion_map,
            **generator_kwargs
        )


class JSONScriptReader:
    """JSON剧本读取器 - 用于读取和解析JSON格式的剧本文件"""
    
    def __init__(self, json_path: str, debug: bool = True):
        """
        初始化JSON读取器
        
        Args:
            json_path: JSON文件路径
            debug: 是否打印调试信息
        """
        self.json_path = Path(json_path)
        if not self.json_path.exists():
            raise FileNotFoundError(f"JSON文件不存在: {json_path}")
        
        self.debug = debug
        self.audio_tracks: List[AudioTrack] = []
        self.characters: List[Character] = []
        self.scenes: List[Scene] = []
        self.image_prompts: List[ImagePrompt] = []
        self.edit_timelines: List[EditTimeline] = []
        self.story_data: Optional[Dict[str, Any]] = None
        self.scene_items: List[Dict[str, Any]] = []  # 存储所有scene类型的内容项
        
        if self.debug:
            logger.info(f"初始化JSON读取器: {json_path}")
    
    def read_all(self) -> Dict[str, Any]:
        """
        读取JSON剧本文件并转换为Excel数据结构
        
        Returns:
            包含所有数据的字典
        """
        if self.debug:
            logger.info("开始读取JSON剧本文件...")
        
        try:
            # 读取JSON文件
            with open(self.json_path, 'r', encoding='utf-8') as f:
                self.story_data = json.load(f)
            
            if self.debug:
                logger.info(f"故事名称: {self.story_data.get('story_name', '未知')}")
                logger.info(f"总集数: {self.story_data.get('total_episodes', 0)}")
            
            # 解析数据
            self._parse_episodes()
            self._build_characters()
            self._build_scenes()
            self._build_edit_timelines()
            
            if self.debug:
                self._print_summary()
            
            return {
                'audio_tracks': self.audio_tracks,
                'characters': self.characters,
                'scenes': self.scenes,
                'image_prompts': self.image_prompts,
                'edit_timelines': self.edit_timelines
            }
            
        except Exception as e:
            logger.error(f"读取JSON文件时出错: {e}")
            raise
    
    def _parse_episodes(self):
        """解析剧集数据"""
        if not self.story_data or 'episodes' not in self.story_data:
            logger.warning("JSON文件中没有episodes字段")
            return
        
        episodes = self.story_data['episodes']
        shot_counter = {}  # 用于统计每个剧集的分镜数
        
        for episode in episodes:
            ep_id = episode.get('ep_id', 0)
            episode_id = f"EP{ep_id:02d}"
            title = episode.get('title', '')
            content = episode.get('content', [])
            
            if episode_id not in shot_counter:
                shot_counter[episode_id] = 0
            
            current_scene_name = None
            current_scene_description = None
            shot_content_parts = []  # 用于累积分镜内容
            shot_hint = None  # 分镜提示（镜头类型）
            shot_description = None  # 分镜描述
            
            # 遍历内容项，按类型处理
            # 每个内容项索引对应一个分镜编号（0-23）
            for item_idx, item in enumerate(content):
                item_type = item.get('type', '')
                
                if item_type == 'scene':
                    # 场景：记录场景信息，并创建分镜（场景切换也是一个分镜）
                    current_scene_name = item.get('scene_name', '')
                    current_scene_description = item.get('description', '')
                    
                    # 保存scene信息，用于后续构建场景汇总
                    self.scene_items.append({
                        'episode_id': episode_id,
                        'scene_name': current_scene_name,
                        'description': current_scene_description,
                        'shot_id': f"{episode_id}_SQ{item_idx:02d}",
                        'item_idx': item_idx
                    })
                    
                    # 创建场景分镜
                    shot_id = f"{episode_id}_SQ{item_idx:02d}"
                    shot_counter[episode_id] = max(shot_counter[episode_id], item_idx + 1)
                    
                    scene_content = current_scene_description or ''
                    
                    # 创建图像提示词
                    image_prompt = ImagePrompt(
                        剧集id=episode_id,
                        分镜号=shot_id,
                        场景名=current_scene_name,
                        场景内容=scene_content,
                        角色=None,
                        镜头类型=None,
                        图像提示词=current_scene_description or scene_content,
                        视频提示词=current_scene_description or scene_content
                    )
                    self.image_prompts.append(image_prompt)
                    
                    # 创建空的音频轨道
                    audio_track = AudioTrack(
                        剧集id=episode_id,
                        分镜号=shot_id,
                        场景内容=scene_content,
                        场景图片提示词=current_scene_description or scene_content
                    )
                    self.audio_tracks.append(audio_track)
                    
                    # 重置分镜内容
                    shot_content_parts = []
                    shot_hint = None
                    shot_description = None
                
                elif item_type == 'action':
                    # 动作：添加到分镜内容，并创建分镜（每个action也是一个分镜）
                    character = item.get('character', '')
                    action_content = item.get('content', '')
                    if character and action_content:
                        shot_content_parts.append(f"{character}：{action_content}")
                    elif action_content:
                        shot_content_parts.append(action_content)
                    
                    # 创建动作分镜
                    shot_id = f"{episode_id}_SQ{item_idx:02d}"
                    shot_counter[episode_id] = max(shot_counter[episode_id], item_idx + 1)
                    
                    scene_content_parts = []
                    if current_scene_description:
                        scene_content_parts.append(current_scene_description)
                    if shot_content_parts:
                        scene_content_parts.extend(shot_content_parts)
                    
                    scene_content = '，'.join(scene_content_parts) if scene_content_parts else ''
                    
                    # 创建图像提示词
                    image_prompt = ImagePrompt(
                        剧集id=episode_id,
                        分镜号=shot_id,
                        场景名=current_scene_name,
                        场景内容=scene_content,
                        角色=character if character else None,
                        镜头类型=shot_hint,
                        图像提示词=shot_description or current_scene_description or scene_content,
                        视频提示词=shot_description or current_scene_description or scene_content
                    )
                    self.image_prompts.append(image_prompt)
                    
                    # 创建空的音频轨道
                    audio_track = AudioTrack(
                        剧集id=episode_id,
                        分镜号=shot_id,
                        场景内容=scene_content,
                        场景图片提示词=shot_description or current_scene_description or scene_content
                    )
                    self.audio_tracks.append(audio_track)
                    
                    # 重置分镜内容（为下一个storyboard准备）
                    shot_content_parts = []
                
                elif item_type == 'storyboard':
                    # 分镜：每个storyboard对应一个分镜
                    shot_hint = item.get('hint', '')
                    shot_description = item.get('description', '')
                    
                    # 创建分镜（每个storyboard都创建一个分镜）
                    # 分镜编号对应内容项索引（0-23）
                    shot_id = f"{episode_id}_SQ{item_idx:02d}"
                    shot_counter[episode_id] = max(shot_counter[episode_id], item_idx + 1)
                    
                    # 构建场景内容（包含场景描述、累积的动作和分镜描述）
                    scene_content_parts = []
                    if current_scene_description:
                        scene_content_parts.append(current_scene_description)
                    if shot_content_parts:
                        scene_content_parts.extend(shot_content_parts)
                    if shot_description:
                        scene_content_parts.append(shot_description)
                    
                    scene_content = '，'.join(scene_content_parts) if scene_content_parts else shot_description or ''
                    
                    # 创建图像提示词
                    image_prompt = ImagePrompt(
                        剧集id=episode_id,
                        分镜号=shot_id,
                        场景名=current_scene_name,
                        场景内容=scene_content,
                        角色=None,
                        镜头类型=shot_hint,
                        图像提示词=shot_description or current_scene_description or scene_content,
                        视频提示词=shot_description or current_scene_description or scene_content
                    )
                    self.image_prompts.append(image_prompt)
                    
                    # 创建音频轨道（可能为空，如果没有对话）
                    audio_track = AudioTrack(
                        剧集id=episode_id,
                        分镜号=shot_id,
                        场景内容=scene_content,
                        场景图片提示词=shot_description or current_scene_description or scene_content
                    )
                    self.audio_tracks.append(audio_track)
                    
                    # 重置分镜内容（storyboard后开始新的分镜）
                    shot_content_parts = []
                    shot_hint = None
                    shot_description = None
                
                elif item_type == 'dialogue':
                    # 对话：添加到分镜内容，并更新最后一个音频轨道
                    role = item.get('role', '')
                    dialogue_content = item.get('content', '')
                    
                    if dialogue_content:
                        # 添加到分镜内容
                        if role:
                            shot_content_parts.append(f"{role}：{dialogue_content}")
                        else:
                            shot_content_parts.append(dialogue_content)
                        
                        # 对话：如果没有对应的storyboard，创建一个新分镜
                        # 分镜编号对应内容项索引
                        shot_id = f"{episode_id}_SQ{item_idx:02d}"
                        shot_counter[episode_id] = max(shot_counter[episode_id], item_idx + 1)
                        
                        # 检查是否已经存在这个分镜
                        existing_shot = None
                        for track in self.audio_tracks:
                            if track.剧集id == episode_id and track.分镜号 == shot_id:
                                existing_shot = track
                                break
                        
                        if not existing_shot:
                            # 需要创建新分镜
                            scene_content = current_scene_description or ''
                            if shot_content_parts:
                                scene_content += '，' + '，'.join(shot_content_parts) if scene_content else '，'.join(shot_content_parts)
                            
                            audio_track = AudioTrack(
                                剧集id=episode_id,
                                分镜号=shot_id,
                                场景内容=scene_content,
                                场景图片提示词=current_scene_description or scene_content,
                                剧情角色=role,
                                音频角色=role if role else None,
                                音频id=f"{shot_id}_A01",
                                音频图片id=f"{shot_id}_A01",
                                音频内容=dialogue_content,
                                输出视频id=f"{shot_id}_A01"
                            )
                            self.audio_tracks.append(audio_track)
                            
                            # 创建图像提示词
                            image_prompt = ImagePrompt(
                                剧集id=episode_id,
                                分镜号=shot_id,
                                场景名=current_scene_name,
                                场景内容=scene_content,
                                角色=role if role else None,
                                镜头类型=shot_hint,
                                图像提示词=shot_description or current_scene_description or scene_content,
                                视频提示词=shot_description or current_scene_description or scene_content
                            )
                            self.image_prompts.append(image_prompt)
                        else:
                            # 更新已存在的分镜
                            existing_shot.剧情角色 = role
                            existing_shot.音频角色 = role if role else None
                            existing_shot.音频id = f"{shot_id}_A01"
                            existing_shot.音频图片id = existing_shot.音频id
                            existing_shot.音频内容 = dialogue_content
                            existing_shot.输出视频id = existing_shot.音频id
                            
                            # 更新场景内容
                            scene_content = existing_shot.场景内容
                            if shot_content_parts:
                                scene_content += '，' + '，'.join(shot_content_parts) if scene_content else '，'.join(shot_content_parts)
                            existing_shot.场景内容 = scene_content
                            
                            # 更新图像提示词
                            for img_prompt in self.image_prompts:
                                if img_prompt.分镜号 == shot_id:
                                    img_prompt.场景内容 = scene_content
                                    break
                        
                        # 重置分镜内容（对话后通常开始新的分镜）
                        shot_content_parts = []
                        shot_hint = None
                        shot_description = None
            
            # 处理最后一个分镜（如果有未处理的内容且没有对应的storyboard）
            # 注意：如果最后一个内容项是storyboard，分镜已经创建，不需要再处理
            # 只有当最后是action或dialogue但没有storyboard时，才需要创建分镜
            if shot_content_parts and current_scene_name:
                # 检查最后一个内容项是否是storyboard
                last_item_type = content[-1].get('type', '') if content else ''
                if last_item_type != 'storyboard':
                    shot_counter[episode_id] += 1
                    shot_id = f"{episode_id}_SQ{shot_counter[episode_id]:02d}"
                    
                    scene_content = current_scene_description or ''
                    if shot_content_parts:
                        scene_content += '，' + '，'.join(shot_content_parts) if scene_content else '，'.join(shot_content_parts)
                    
                    image_prompt = ImagePrompt(
                        剧集id=episode_id,
                        分镜号=shot_id,
                        场景名=current_scene_name,
                        场景内容=scene_content,
                        角色=None,
                        镜头类型=shot_hint,
                        图像提示词=shot_description or current_scene_description or scene_content,
                        视频提示词=shot_description or current_scene_description or scene_content
                    )
                    self.image_prompts.append(image_prompt)
                    
                    audio_track = AudioTrack(
                        剧集id=episode_id,
                        分镜号=shot_id,
                        场景内容=scene_content,
                        场景图片提示词=shot_description or current_scene_description or scene_content
                    )
                    self.audio_tracks.append(audio_track)
    
    def _build_characters(self):
        """从音频轨道中提取角色信息"""
        character_map = {}  # 角色名 -> 出现次数
        
        for track in self.audio_tracks:
            if track.剧情角色:
                role_name = track.剧情角色
                if role_name not in character_map:
                    character_map[role_name] = {
                        'count': 0,
                        'episodes': set(),
                        'shots': []
                    }
                character_map[role_name]['count'] += 1
                character_map[role_name]['episodes'].add(track.剧集id)
                character_map[role_name]['shots'].append(track.分镜号)
        
        # 创建角色对象
        for role_name, info in character_map.items():
            episodes_str = ','.join(sorted(info['episodes']))
            shots_str = ','.join(info['shots'])
            
            character = Character(
                角色名=role_name,
                出现次数=info['count'],
                出现剧集及分镜号=shots_str
            )
            self.characters.append(character)
    
    def _build_scenes(self):
        """从JSON中的scene类型内容项提取场景信息"""
        scene_map = {}  # 场景名 -> 出现信息
        
        # 从scene_items中提取场景信息
        for scene_item in self.scene_items:
            scene_name = scene_item.get('scene_name', '')
            scene_description = scene_item.get('description', '')
            episode_id = scene_item.get('episode_id', '')
            shot_id = scene_item.get('shot_id', '')
            
            if not scene_name:
                continue
            
            # 如果场景名相同，合并信息（统计出现次数和分镜号）
            if scene_name not in scene_map:
                scene_map[scene_name] = {
                    'count': 0,
                    'episodes': set(),
                    'shots': [],
                    'description': scene_description,  # 使用第一个出现的描述
                    'first_episode_id': episode_id,
                    'first_shot_id': shot_id
                }
            
            scene_map[scene_name]['count'] += 1
            scene_map[scene_name]['episodes'].add(episode_id)
            scene_map[scene_name]['shots'].append(shot_id)
        
        # 创建场景对象
        for scene_name, info in scene_map.items():
            episodes_str = ','.join(sorted(info['episodes']))
            shots_str = ','.join(info['shots'])
            
            scene = Scene(
                场景名=scene_name,
                剧集id=info['first_episode_id'],
                分镜号=info['first_shot_id'],
                场景描述=info['description'],
                出现次数=info['count'],
                出现剧集及分镜号=shots_str
            )
            self.scenes.append(scene)
    
    def _build_edit_timelines(self):
        """构建剪辑时间线"""
        # 按剧集和分镜号分组
        timeline_map = {}  # (剧集id, 分镜号) -> 音频ID列表
        
        for track in self.audio_tracks:
            key = (track.剧集id, track.分镜号)
            if key not in timeline_map:
                timeline_map[key] = []
            if track.音频id:
                timeline_map[key].append(track.音频id)
        
        # 按剧集和分镜顺序构建时间线
        current_time = 0.0
        default_duration = 5.0  # 默认时长5秒
        
        for episode_id in sorted(set(track.剧集id for track in self.audio_tracks)):
            shots = sorted(set(track.分镜号 for track in self.audio_tracks if track.剧集id == episode_id))
            
            for shot_id in shots:
                key = (episode_id, shot_id)
                if key in timeline_map:
                    audio_ids = timeline_map[key]
                    audio_id_str = ','.join(audio_ids)
                    
                    # 计算时长（如果有音频轨道，使用默认时长）
                    duration = default_duration if audio_ids else 3.0
                    
                    timeline = EditTimeline(
                        剧集id=episode_id,
                        分镜号=shot_id,
                        全局开始时间=current_time,
                        全局结束时间=current_time + duration,
                        时长=duration,
                        视觉ID=f"{shot_id}_V",
                        音频ID列表=audio_id_str
                    )
                    self.edit_timelines.append(timeline)
                    current_time += duration
    
    def _print_summary(self):
        """打印数据摘要"""
        print("\n" + "="*80)
        print("JSON剧本数据读取摘要")
        print("="*80)
        print(f"音频轨道数量: {len(self.audio_tracks)}")
        print(f"角色数量: {len(self.characters)}")
        print(f"场景数量: {len(self.scenes)}")
        print(f"图像提示词数量: {len(self.image_prompts)}")
        print(f"剪辑时间线数量: {len(self.edit_timelines)}")
        print("="*80)
        
        # 按剧集统计
        if self.audio_tracks:
            episodes = set(track.剧集id for track in self.audio_tracks)
            print(f"\n剧集列表: {sorted(episodes)}")
        
        # 显示前几个示例
        if self.debug:
            print("\n--- 音频轨道示例 (前3条) ---")
            for i, track in enumerate(self.audio_tracks[:3], 1):
                print(f"\n{i}. 剧集: {track.剧集id}, 分镜: {track.分镜号}")
                print(f"   场景内容: {track.场景内容[:50]}..." if len(track.场景内容) > 50 else f"   场景内容: {track.场景内容}")
                if track.音频id:
                    print(f"   音频ID: {track.音频id}, 角色: {track.音频角色}")
            
            if self.characters:
                print("\n--- 角色示例 (前3个) ---")
                for i, char in enumerate(self.characters[:3], 1):
                    print(f"\n{i}. {char.角色名}")
                    if char.出现次数:
                        print(f"   出现次数: {char.出现次数}")
            
            if self.scenes:
                print("\n--- 场景示例 (前3个) ---")
                for i, scene in enumerate(self.scenes[:3], 1):
                    print(f"\n{i}. {scene.场景名}")
                    if scene.出现次数:
                        print(f"   出现次数: {scene.出现次数}")
    
    # 复用ExcelDataReader的查询方法
    def get_audio_tracks_by_episode(self, episode_id: str) -> List[AudioTrack]:
        """根据剧集ID获取音频轨道"""
        return [track for track in self.audio_tracks if track.剧集id == episode_id]
    
    def get_audio_tracks_by_shot(self, shot_id: str) -> List[AudioTrack]:
        """根据分镜号获取音频轨道"""
        return [track for track in self.audio_tracks if track.分镜号 == shot_id]
    
    def get_image_prompt_by_shot(self, shot_id: str) -> Optional[ImagePrompt]:
        """根据分镜号获取图像提示词"""
        for prompt in self.image_prompts:
            if prompt.分镜号 == shot_id:
                return prompt
        return None
    
    def get_edit_timeline_by_shot(self, shot_id: str) -> Optional[EditTimeline]:
        """根据分镜号获取剪辑时间线"""
        for timeline in self.edit_timelines:
            if timeline.分镜号 == shot_id:
                return timeline
        return None
    
    def get_character_by_name(self, name: str) -> Optional[Character]:
        """根据角色名获取角色信息"""
        for char in self.characters:
            if char.角色名 == name:
                return char
        return None
    
    def get_scene_by_name(self, name: str) -> Optional[Scene]:
        """根据场景名获取场景信息"""
        for scene in self.scenes:
            if scene.场景名 == name:
                return scene
        return None
    
    # 复用ExcelDataReader的批量生成方法
    def batch_generate_images_from_prompts(self, *args, **kwargs):
        """批量生成图像（委托给ExcelDataReader的方法）"""
        # 创建一个临时的ExcelDataReader实例来复用方法
        # 由于方法需要访问self的属性，我们需要手动设置
        class TempReader:
            def __init__(self, json_reader):
                self.image_prompts = json_reader.image_prompts
                self.characters = json_reader.characters
                self.audio_tracks = json_reader.audio_tracks
        
        temp_reader = TempReader(self)
        # 直接调用模块级别的函数
        if not IMAGE_GENERATOR_AVAILABLE:
            raise ImportError("图像生成器模块不可用，请确保image_generator.py存在")
        
        return batch_generate_images_from_excel_data(
            image_prompts=self.image_prompts,
            characters=self.characters,
            audio_tracks=self.audio_tracks,
            scenes=self.scenes,
            *args, **kwargs
        )
    
    def batch_generate_videos_from_prompts(self, *args, **kwargs):
        """批量生成视频（委托给ExcelDataReader的方法）"""
        if not VIDEO_GENERATOR_AVAILABLE:
            raise ImportError("视频生成器模块不可用，请确保video_generator.py存在")
        
        return batch_generate_videos_from_excel_data(
            image_prompts=self.image_prompts,
            characters=self.characters,
            *args, **kwargs
        )
    
    def batch_generate_audio_from_tracks(self, *args, **kwargs):
        """批量生成音频（委托给ExcelDataReader的方法）"""
        if not AUDIO_GENERATOR_AVAILABLE:
            raise ImportError("音频生成器模块不可用，请确保audio_generator.py存在")
        
        return batch_generate_audio_from_excel_data(
            audio_tracks=self.audio_tracks,
            characters=self.characters,
            *args, **kwargs
        )
    
    def export_to_excel(self, output_path: str):
        """
        将JSON导入的数据导出为Excel文件
        
        Args:
            output_path: 输出Excel文件路径
        """
        if self.debug:
            logger.info(f"开始导出Excel文件: {output_path}")
        
        try:
            with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
                # 1. 音频汇总工作表
                audio_data = []
                for track in self.audio_tracks:
                    audio_data.append({
                        '剧集id': track.剧集id,
                        '分镜号': track.分镜号,
                        '场景内容': track.场景内容,
                        '场景图片提示词': track.场景图片提示词 or '',
                        '剧情角色': track.剧情角色 or '',
                        '音频角色': track.音频角色 or '',
                        '音频情感': track.音频情感 or '',
                        '音频id': track.音频id or '',
                        '音频图片id': track.音频图片id or '',
                        '音频内容': track.音频内容 or '',
                        '时长': track.时长 if track.时长 is not None else '',
                        '输出视频id': track.输出视频id or '',
                        '备注': track.备注 or '',
                        '参考样本': track.参考样本 or ''
                    })
                df_audio = pd.DataFrame(audio_data)
                df_audio.to_excel(writer, sheet_name='音频汇总', index=False)
                
                # 2. 角色汇总工作表
                character_data = []
                for char in self.characters:
                    character_data.append({
                        '角色名': char.角色名,
                        '角色id': char.角色id if char.角色id is not None else '',
                        '音频id': char.音频id or '',
                        '参考音色': char.参考音色 or '',
                        '角色描述': char.角色描述 or '',
                        '视觉特征': char.视觉特征 or '',
                        '图像提示词': char.图像提示词 or '',
                        '出现章节': char.出现章节 or '',
                        '出现次数': char.出现次数 if char.出现次数 is not None else '',
                        '出现剧集及分镜号': char.出现剧集及分镜号 or '',
                        '备注': char.备注 or '',
                        '参考图': char.参考图 or ''
                    })
                df_character = pd.DataFrame(character_data)
                df_character.to_excel(writer, sheet_name='角色汇总', index=False)
                
                # 3. 场景汇总工作表
                scene_data = []
                for scene in self.scenes:
                    scene_data.append({
                        '场景名': scene.场景名,
                        '剧集id': scene.剧集id or '',
                        '分镜号': scene.分镜号 or '',
                        '场景id': scene.场景id if scene.场景id is not None else '',
                        '场景类型': scene.场景类型 or '',
                        '场景描述': scene.场景描述 or '',
                        '视觉特征': scene.视觉特征 or '',
                        '图像提示词': scene.图像提示词 or '',
                        '位置细节': scene.位置细节 or '',
                        '出现章节': scene.出现章节 or '',
                        '出现次数': scene.出现次数 if scene.出现次数 is not None else '',
                        '出现剧集及分镜号': scene.出现剧集及分镜号 or '',
                        '备注': scene.备注 or '',
                        '参考图': scene.参考图 or ''
                    })
                df_scene = pd.DataFrame(scene_data)
                df_scene.to_excel(writer, sheet_name='场景汇总', index=False)
                
                # 4. 图像汇总工作表（兼容旧名称'图像提示词'）
                # 创建分镜号到场景名的映射
                # 方法：按剧集和分镜号索引排序，找到每个分镜号之前最近的一个scene
                shot_to_scene_map = {}  # 分镜号 -> 场景名
                
                # 按剧集分组处理
                for episode_id in sorted(set(prompt.剧集id for prompt in self.image_prompts)):
                    # 获取该剧集的所有分镜号，按索引排序
                    episode_shots = sorted(
                        [prompt.分镜号 for prompt in self.image_prompts if prompt.剧集id == episode_id],
                        key=lambda x: int(x.split('_SQ')[1]) if '_SQ' in x else 0
                    )
                    
                    # 获取该剧集的所有scene，按索引排序
                    episode_scenes = sorted(
                        [item for item in self.scene_items if item.get('episode_id') == episode_id],
                        key=lambda x: x.get('item_idx', 0)
                    )
                    
                    # 为每个分镜找到对应的场景（找到该分镜之前最近的一个scene）
                    for shot_id in episode_shots:
                        try:
                            sq_idx = int(shot_id.split('_SQ')[1])
                            # 找到分镜号小于等于当前分镜号的最后一个scene
                            current_scene_name = ''
                            for scene_item in episode_scenes:
                                scene_shot_id = scene_item.get('shot_id', '')
                                if scene_shot_id:
                                    scene_sq_idx = int(scene_shot_id.split('_SQ')[1])
                                    if scene_sq_idx <= sq_idx:
                                        current_scene_name = scene_item.get('scene_name', '')
                                    else:
                                        break
                            if current_scene_name:
                                shot_to_scene_map[shot_id] = current_scene_name
                        except (ValueError, IndexError):
                            pass
                
                image_data = []
                for prompt in self.image_prompts:
                    # 获取场景名
                    scene_name = shot_to_scene_map.get(prompt.分镜号, '')
                    
                    image_data.append({
                        '剧集id': prompt.剧集id,
                        '分镜号': prompt.分镜号,
                        '场景名': (prompt.场景名 if prompt.场景名 is not None else scene_name),
                        '场景内容': prompt.场景内容,
                        '角色': prompt.角色 or '',
                        '镜头类型': prompt.镜头类型 or '',
                        '图像提示词': prompt.图像提示词 or '',
                        '首帧提示词': prompt.首帧提示词 or '',
                        '末帧提示词': prompt.末帧提示词 or '',
                        '视频提示词': prompt.视频提示词 or '',
                        '备注': prompt.备注 or '',
                        '参考图': prompt.参考图 or ''
                    })
                df_image = pd.DataFrame(image_data)
                df_image.to_excel(writer, sheet_name='图像汇总', index=False)
                
                # 5. 剪辑汇总工作表
                edit_data = []
                for timeline in self.edit_timelines:
                    edit_data.append({
                        '剧集id': timeline.剧集id,
                        '分镜号': timeline.分镜号,
                        '全局开始时间(秒)': timeline.全局开始时间,
                        '全局结束时间(秒)': timeline.全局结束时间,
                        '时长(秒)': timeline.时长,
                        '视觉ID': timeline.视觉ID,
                        '音频ID列表': timeline.音频ID列表
                    })
                df_edit = pd.DataFrame(edit_data)
                df_edit.to_excel(writer, sheet_name='剪辑汇总', index=False)
            
            if self.debug:
                logger.info(f"✓ Excel文件导出完成: {output_path}")
                print(f"\n✓ Excel文件已导出: {output_path}")
                print(f"  - 音频汇总: {len(audio_data)} 行")
                print(f"  - 角色汇总: {len(character_data)} 行")
                print(f"  - 场景汇总: {len(scene_data)} 行")
                print(f"  - 图像汇总: {len(image_data)} 行")
                print(f"  - 剪辑汇总: {len(edit_data)} 行")
        
        except Exception as e:
            logger.error(f"导出Excel文件时出错: {e}")
            raise


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='读取Excel或JSON剧本数据文件，支持批量生成图像和视频')
    parser.add_argument('--excel', type=str, default=None,
                       help='Excel文件路径 (默认: all_episodes.xlsx，如果指定--json则忽略)')
    parser.add_argument('--json', type=str, default=None,
                       help='JSON剧本文件路径 (如果指定，将使用JSON导入而不是Excel)')
    parser.add_argument('--export-excel', type=str, default=None,
                       help='导出Excel文件路径 (仅在使用--json时有效，将JSON导入的数据导出为Excel)')
    parser.add_argument('--debug', action='store_true', default=True,
                       help='打印调试信息 (默认: True)')
    parser.add_argument('--no-debug', dest='debug', action='store_false',
                       help='不打印调试信息')
    
    # 批量生成图像相关参数
    parser.add_argument('--generate-images', action='store_true',
                       help='批量生成图像')
    parser.add_argument('--output-dir', type=str, default='./output',
                       help='图像输出目录 (默认: ./output)')
    parser.add_argument('--generate-reference', action='store_true', default=True,
                       help='生成参考图（图像提示词）(默认: True)')
    parser.add_argument('--no-reference', dest='generate_reference', action='store_false',
                       help='不生成参考图')
    parser.add_argument('--generate-first-frame', action='store_true',
                       help='生成首帧（首帧提示词）')
    parser.add_argument('--generate-last-frame', action='store_true',
                       help='生成末帧（末帧提示词）')
    parser.add_argument('--episode', type=str, default=None,
                       help='只处理指定剧集（如: EP01），如果未指定则处理所有剧集')
    parser.add_argument('--comfyui-server', type=str, default='127.0.0.1:8188',
                       help='ComfyUI服务器地址 (默认: 127.0.0.1:8188)')
    parser.add_argument('--style-prefix', type=str, default=None,
                       help='风格前缀（可选，默认: "Pixel art style,"）')
    parser.add_argument('--seed', type=int, default=None,
                       help='随机种子（可选）')
    parser.add_argument('--steps', type=int, default=None,
                       help='采样步数（可选）')
    parser.add_argument('--cfg', type=float, default=None,
                       help='CFG值（可选）')
    parser.add_argument('--width', type=int, default=None,
                       help='图像宽度（可选）')
    parser.add_argument('--height', type=int, default=None,
                       help='图像高度（可选）')
    parser.add_argument('--no-prompt-expansion', dest='enable_prompt_expansion', action='store_false',
                       help='禁用提示词扩展（默认启用，会根据角色自动附加角色图像提示词）')
    parser.add_argument('--enable-prompt-expansion', dest='enable_prompt_expansion', action='store_true', default=True,
                       help='启用提示词扩展（默认启用）')
    parser.add_argument('--scene-image-dir', type=str, default=None,
                       help='场景图目录，下存 {场景id}.png 或 场景名.png，用于参考图1（有参考图时用 Image Edit 工作流）')
    parser.add_argument('--character-image-dir', type=str, default=None,
                       help='角色图目录，下存 {角色id}.png 或 角色名.png，用于参考图2')
    
    # 批量生成视频相关参数
    parser.add_argument('--generate-videos', action='store_true',
                       help='批量生成视频（使用图像汇总表中的视频提示词）')
    parser.add_argument('--video-output-dir', type=str, default='./output',
                       help='视频输出目录 (默认: ./output)')
    parser.add_argument('--video-input-image-dir', type=str, default=None,
                       help='图生视频的输入图片所在目录（本地），下存 {分镜号}_ref.png 等；未指定时用 --reference-image-dir 或 --video-output-dir')
    parser.add_argument('--video-workflow', type=str, default=None,
                       help='视频生成工作流JSON路径（可选，默认 act_video_wan2_2_14B_i2v-aigc-api.json，仅用于comfyui）')
    parser.add_argument('--video-generator-type', type=str, default='comfyui', choices=['comfyui', 'sora'],
                       help='视频生成器类型（默认: comfyui，可选: sora）')
    parser.add_argument('--shot', type=str, default=None,
                       help='只处理指定分镜（如: EP01_SQ01），如果未指定则处理所有分镜')
    parser.add_argument('--negative-prompt', type=str, default=None,
                       help='负提示词（可选）')
    parser.add_argument('--video-length', type=int, default=None,
                       help='视频长度/帧数（可选）')
    parser.add_argument('--fps', type=float, default=None,
                       help='视频帧率（可选）')
    parser.add_argument('--reference-image-dir', type=str, default=None,
                       help='参考图像目录（可选，用于查找对应的参考图）')
    parser.add_argument('--no-video-prompt-expansion', dest='enable_video_prompt_expansion', action='store_false',
                       help='禁用视频提示词扩展（默认启用）')
    parser.add_argument('--enable-video-prompt-expansion', dest='enable_video_prompt_expansion', action='store_true', default=True,
                       help='启用视频提示词扩展（默认启用）')
    # Sora相关参数
    parser.add_argument('--sora-api-key', type=str, default=None,
                       help='Sora API密钥（用于sora类型，如果未指定则从配置文件读取）')
    parser.add_argument('--sora-host', type=str, default='https://grsai.dakka.com.cn',
                       help='Sora API服务器地址（用于sora类型，默认: https://grsai.dakka.com.cn）')
    parser.add_argument('--sora-config-path', type=str, default=None,
                       help='Sora配置文件路径（用于sora类型，可选）')
    
    # 批量生成音频相关参数
    parser.add_argument('--generate-audio', action='store_true',
                       help='批量生成音频（使用音频汇总表中的数据）')
    parser.add_argument('--audio-output-dir', type=str, default='./output',
                       help='音频输出目录 (默认: ./output)')
    parser.add_argument('--audio-generator-type', type=str, default='volcengine', choices=['volcengine'],
                       help='音频生成器类型（默认: volcengine）')
    parser.add_argument('--audio-config-path', type=str, default=None,
                       help='音频生成器配置文件路径（可选）')
    parser.add_argument('--audio-encoding', type=str, default='wav',
                       help='音频编码格式（默认: wav）')
    parser.add_argument('--audio-emotion', type=str, default=None,
                       help='默认音色情感（可选）')
    parser.add_argument('--appid', type=str, default=None,
                       help='应用ID（volcengine需要，优先级高于配置文件）')
    parser.add_argument('--access-token', type=str, default=None,
                       help='访问令牌（volcengine需要，优先级高于配置文件）')
    parser.add_argument('--endpoint', type=str, default=None,
                       help='WebSocket端点URL（优先级高于配置文件）')
    
    args = parser.parse_args()
    
    try:
        # 根据参数选择读取器类型
        if args.json:
            # 使用JSON导入
            reader = JSONScriptReader(args.json, debug=args.debug)
            data = reader.read_all()
            print("\n✓ JSON剧本文件读取完成!")
            
            # 如果指定了导出Excel，则导出；否则自动生成文件名
            if args.export_excel:
                export_path = args.export_excel
            else:
                # 自动生成Excel文件名：基于JSON文件名
                json_path = Path(args.json)
                export_path = json_path.with_suffix('.xlsx')
                if args.debug:
                    logger.info(f"未指定导出路径，自动生成: {export_path}")
            
            # 导出Excel文件
            reader.export_to_excel(str(export_path))
        else:
            # 使用Excel导入（默认）
            excel_path = args.excel or 'all_episodes.xlsx'
            reader = ExcelDataReader(excel_path, debug=args.debug)
            data = reader.read_all()
            print("\n✓ Excel文件读取完成!")
        
        # 如果需要生成图像
        if args.generate_images:
            if not IMAGE_GENERATOR_AVAILABLE:
                logger.error("图像生成器模块不可用，无法生成图像。请确保image_generator.py存在")
                return reader, data
            
            print("\n开始批量生成图像...")
            results = reader.batch_generate_images_from_prompts(
                output_dir=args.output_dir,
                generate_reference=args.generate_reference,
                generate_first_frame=args.generate_first_frame,
                generate_last_frame=args.generate_last_frame,
                comfyui_server=args.comfyui_server,
                style_prefix=args.style_prefix,
                seed=args.seed,
                steps=args.steps,
                cfg=args.cfg,
                width=args.width,
                height=args.height,
                episode_filter=args.episode,
                enable_prompt_expansion=args.enable_prompt_expansion,
                scene_image_dir=getattr(args, 'scene_image_dir', None),
                character_image_dir=getattr(args, 'character_image_dir', None),
                reference_image_dir=getattr(args, 'reference_image_dir', None),
            )
            
            print(f"\n✓ 图像生成完成! 共处理 {len(results)} 个分镜")
        
        # 如果需要生成视频
        if args.generate_videos:
            if not VIDEO_GENERATOR_AVAILABLE:
                logger.error("视频生成器模块不可用，无法生成视频。请确保video_generator.py存在")
                return reader, data
            
            print("\n开始批量生成视频...")
            video_ref_dir = getattr(args, 'video_input_image_dir', None) or args.reference_image_dir or args.video_output_dir
            video_results = reader.batch_generate_videos_from_prompts(
                output_dir=args.video_output_dir,
                comfyui_server=args.comfyui_server,
                workflow_path=args.video_workflow,
                episode_filter=args.episode,
                shot_filter=args.shot,
                negative_prompt=args.negative_prompt,
                seed=args.seed,
                steps=args.steps,
                cfg=args.cfg,
                width=args.width,
                height=args.height,
                length=args.video_length,
                fps=args.fps,
                reference_image_dir=video_ref_dir,
                generator_type=args.video_generator_type,
                enable_prompt_expansion=args.enable_video_prompt_expansion,
                sora_api_key=args.sora_api_key,
                sora_host=args.sora_host,
                sora_config_path=args.sora_config_path
            )
            
            print(f"\n✓ 视频生成完成! 共处理 {len(video_results)} 个分镜")
        
        # 如果需要生成音频
        if args.generate_audio:
            if not AUDIO_GENERATOR_AVAILABLE:
                logger.error("音频生成器模块不可用，无法生成音频。请确保audio_generator.py存在")
                return reader, data
            
            print("\n开始批量生成音频...")
            audio_results = reader.batch_generate_audio_from_tracks(
                output_dir=args.audio_output_dir,
                generator_type=args.audio_generator_type,
                encoding=args.audio_encoding,
                episode_filter=args.episode,
                shot_filter=args.shot,
                config_path=args.audio_config_path,
                emotion=args.audio_emotion,
                appid=args.appid,
                access_token=args.access_token,
                endpoint=args.endpoint
            )
            
            successful = sum(1 for r in audio_results if r.get('success', True) and 'error' not in r)
            print(f"\n✓ 音频生成完成! 共处理 {len(audio_results)} 个音频轨道，成功 {successful} 个")
        
        # 返回数据供后续使用
        return reader, data
        
    except Exception as e:
        logger.error(f"处理失败: {e}")
        import traceback
        traceback.print_exc()
        return None, None


if __name__ == "__main__":
    main()

