"""
自动剪辑程序 - 根据Excel剪辑汇总数据创建剪辑项目
支持导出到剪映、FCPXML、EDL等格式，以及直接导出影片
"""
import os
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime
import subprocess
import shutil

from excel_reader import ExcelDataReader, EditTimeline, AudioTrack

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class ClipSegment:
    """剪辑片段数据"""
    分镜号: str
    视觉ID: str
    音频ID列表: List[str]
    开始时间: float  # 全局开始时间（秒）
    结束时间: float  # 全局结束时间（秒）
    时长: float  # 片段时长（秒）
    视频文件路径: Optional[str] = None
    音频文件路径列表: List[str] = None
    
    def __post_init__(self):
        if self.音频文件路径列表 is None:
            self.音频文件路径列表 = []


class VideoEditor:
    """自动剪辑器"""
    
    def __init__(
        self,
        excel_path: str,
        video_dir: str = "./output",
        audio_dir: Optional[str] = None,
        output_dir: str = "./edit_output"
    ):
        """
        初始化自动剪辑器
        
        Args:
            excel_path: Excel文件路径
            video_dir: 视频文件目录（默认: ./output）
            audio_dir: 音频文件目录（如果为None，则使用video_dir）
            output_dir: 输出目录（默认: ./edit_output）
        """
        self.excel_path = Path(excel_path)
        self.video_dir = Path(video_dir)
        self.audio_dir = Path(audio_dir) if audio_dir else self.video_dir
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 读取Excel数据
        logger.info(f"读取Excel文件: {excel_path}")
        self.reader = ExcelDataReader(str(excel_path), debug=False)
        self.data = self.reader.read_all()
        
        # 构建剪辑片段列表
        self.clip_segments: List[ClipSegment] = []
        self._build_clip_segments()
        
        logger.info(f"初始化完成，共 {len(self.clip_segments)} 个剪辑片段")
    
    def _build_clip_segments(self):
        """构建剪辑片段列表"""
        for timeline in self.reader.edit_timelines:
            # 解析音频ID列表
            audio_ids = []
            if timeline.音频ID列表:
                audio_ids = [aid.strip() for aid in timeline.音频ID列表.split(',') if aid.strip()]
            
            # 查找视频文件
            video_path = self._find_video_file(timeline.视觉ID, timeline.分镜号)
            
            # 查找音频文件
            audio_paths = []
            for audio_id in audio_ids:
                audio_path = self._find_audio_file(audio_id)
                if audio_path:
                    audio_paths.append(audio_path)
            
            segment = ClipSegment(
                分镜号=timeline.分镜号,
                视觉ID=timeline.视觉ID,
                音频ID列表=audio_ids,
                开始时间=timeline.全局开始时间,
                结束时间=timeline.全局结束时间,
                时长=timeline.时长,
                视频文件路径=video_path,
                音频文件路径列表=audio_paths
            )
            self.clip_segments.append(segment)
    
    def _find_video_file(self, visual_id: str, shot_id: str) -> Optional[str]:
        """查找视频文件"""
        # 尝试多种可能的文件名格式
        possible_names = [
            f"{shot_id}_video.mp4",
            f"{visual_id}.mp4",
            f"{shot_id}.mp4",
            f"{visual_id}_video.mp4",
            f"{shot_id}.mov",
            f"{visual_id}.mov",
        ]
        
        # 首先尝试精确匹配
        for name in possible_names:
            path = self.video_dir / name
            if path.exists():
                return str(path.absolute())
        
        # 如果精确匹配失败,尝试模糊匹配(查找包含shot_id的文件)
        for ext in ['.mp4', '.mov', '.avi', '.mkv']:
            pattern = f"{shot_id}*{ext}"
            matches = list(self.video_dir.glob(pattern))
            if matches:
                return str(matches[0].absolute())
        
        logger.warning(f"未找到视频文件: {visual_id} ({shot_id})")
        return None
    
    def _find_audio_file(self, audio_id: str) -> Optional[str]:
        """查找音频文件"""
        # 尝试多种可能的文件名格式
        possible_extensions = ['.mp3', '.wav', '.flac', '.m4a', '.aac', '.ogg']
        possible_names = [f"{audio_id}{ext}" for ext in possible_extensions]
        
        # 首先尝试精确匹配
        for name in possible_names:
            path = self.audio_dir / name
            if path.exists():
                return str(path.absolute())
        
        # 如果精确匹配失败,尝试模糊匹配(查找包含audio_id的文件)
        for ext in possible_extensions:
            pattern = f"{audio_id}*{ext}"
            matches = list(self.audio_dir.glob(pattern))
            if matches:
                return str(matches[0].absolute())
        
        logger.warning(f"未找到音频文件: {audio_id}")
        return None
    
    def export_to_jianying(self, episode_id: Optional[str] = None) -> str:
        """
        导出为剪映草稿格式
        
        Args:
            episode_id: 只导出指定剧集，如果为None则导出所有剧集
            
        Returns:
            输出文件路径
        """
        logger.info("开始生成剪映草稿...")
        
        # 过滤片段
        segments = self.clip_segments
        if episode_id:
            segments = [s for s in segments if self._get_episode_id(s.分镜号) == episode_id]
        
        # 创建剪映草稿目录
        draft_name = f"draft_{episode_id or 'all'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        draft_dir = self.output_dir / draft_name
        draft_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成draft_content.json
        draft_content = self._generate_jianying_draft_content(segments)
        draft_content_path = draft_dir / "draft_content.json"
        with open(draft_content_path, 'w', encoding='utf-8') as f:
            json.dump(draft_content, f, ensure_ascii=False, indent=2)
        
        # 生成draft_meta_info.json
        draft_meta = self._generate_jianying_draft_meta(episode_id)
        draft_meta_path = draft_dir / "draft_meta_info.json"
        with open(draft_meta_path, 'w', encoding='utf-8') as f:
            json.dump(draft_meta, f, ensure_ascii=False, indent=2)
        
        logger.info(f"剪映草稿已生成: {draft_dir}")
        return str(draft_dir)
    
    def _generate_jianying_draft_content(self, segments: List[ClipSegment]) -> Dict:
        """生成剪映draft_content.json内容
        
        注意: 剪映的实际草稿格式比较复杂且可能随版本变化。
        这里生成的是简化版本,主要用于参考。实际使用时可能需要手动调整。
        建议使用FCPXML格式,剪映也支持导入FCPXML格式。
        """
        # 剪映草稿的基本结构(简化版)
        materials = {
            "videos": [],
            "audios": []
        }
        
        tracks = []
        video_track = {
            "id": "video_track_1",
            "type": "video",
            "segments": []
        }
        audio_track = {
            "id": "audio_track_1",
            "type": "audio",
            "segments": []
        }
        
        video_material_id = 1
        audio_material_id = 1
        video_segment_id = 1
        audio_segment_id = 1
        
        current_video_time = 0.0
        current_audio_time = 0.0
        
        for segment in segments:
            # 添加视频片段
            if segment.视频文件路径:
                # 使用相对路径(相对于草稿目录)
                video_path = Path(segment.视频文件路径)
                relative_path = video_path.name  # 简化:只使用文件名
                
                video_material = {
                    "id": f"video_{video_material_id}",
                    "name": segment.分镜号,
                    "path": relative_path,
                    "absolute_path": segment.视频文件路径,  # 保留绝对路径作为参考
                    "type": "video",
                    "duration": segment.时长
                }
                materials["videos"].append(video_material)
                
                video_segment = {
                    "id": f"video_segment_{video_segment_id}",
                    "material_id": f"video_{video_material_id}",
                    "target_timerange": {
                        "start": current_video_time,
                        "duration": segment.时长
                    },
                    "source_timerange": {
                        "start": 0.0,
                        "duration": segment.时长
                    }
                }
                video_track["segments"].append(video_segment)
                video_material_id += 1
                video_segment_id += 1
                current_video_time += segment.时长
            
            # 添加音频片段
            for audio_path in segment.音频文件路径列表:
                audio_path_obj = Path(audio_path)
                relative_audio_path = audio_path_obj.name
                
                audio_material = {
                    "id": f"audio_{audio_material_id}",
                    "name": f"{segment.分镜号}_audio",
                    "path": relative_audio_path,
                    "absolute_path": audio_path,  # 保留绝对路径作为参考
                    "type": "audio"
                }
                materials["audios"].append(audio_material)
                
                # 获取音频时长
                audio_duration = self._get_audio_duration(audio_path) or segment.时长
                
                audio_segment = {
                    "id": f"audio_segment_{audio_segment_id}",
                    "material_id": f"audio_{audio_material_id}",
                    "target_timerange": {
                        "start": current_audio_time,
                        "duration": audio_duration
                    },
                    "source_timerange": {
                        "start": 0.0,
                        "duration": audio_duration
                    }
                }
                audio_track["segments"].append(audio_segment)
                audio_material_id += 1
                audio_segment_id += 1
                current_audio_time += audio_duration
        
        tracks.append(video_track)
        if audio_track["segments"]:  # 只有当有音频片段时才添加音频轨道
            tracks.append(audio_track)
        
        # 计算总时长
        total_duration = max([s.结束时间 for s in segments]) if segments else 0.0
        
        draft_content = {
            "version": "1.0.0",
            "materials": materials,
            "tracks": tracks,
            "canvas_config": {
                "width": 1920,
                "height": 1080,
                "fps": 25
            },
            "total_duration": total_duration,
            "note": "此文件为自动生成的剪映草稿格式(简化版)。实际剪映草稿格式可能更复杂,建议使用FCPXML格式导入。"
        }
        
        return draft_content
    
    def _generate_jianying_draft_meta(self, episode_id: Optional[str]) -> Dict:
        """生成剪映draft_meta_info.json内容"""
        return {
            "draft_id": f"draft_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "draft_name": f"自动剪辑_{episode_id or '全部剧集'}",
            "create_time": datetime.now().isoformat(),
            "update_time": datetime.now().isoformat(),
            "version": "1.0.0"
        }
    
    def export_to_fcpxml(self, episode_id: Optional[str] = None) -> str:
        """
        导出为FCPXML格式（Final Cut Pro XML，支持剪映、Premiere等）
        
        Args:
            episode_id: 只导出指定剧集，如果为None则导出所有剧集
            
        Returns:
            输出文件路径
        """
        logger.info("开始生成FCPXML文件...")
        
        # 过滤片段
        segments = self.clip_segments
        if episode_id:
            segments = [s for s in segments if self._get_episode_id(s.分镜号) == episode_id]
        
        # 生成XML内容
        xml_content = self._generate_fcpxml(segments)
        
        # 保存文件
        filename = f"edit_{episode_id or 'all'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.fcpxml"
        output_path = self.output_dir / filename
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(xml_content)
        
        logger.info(f"FCPXML文件已生成: {output_path}")
        return str(output_path)
    
    def _generate_fcpxml(self, segments: List[ClipSegment]) -> str:
        """生成FCPXML内容"""
        # 计算总时长
        total_duration = max([s.结束时间 for s in segments]) if segments else 0.0
        
        # 转换为帧数（假设25fps）
        fps = 25
        total_frames = int(total_duration * fps)
        
        xml_lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<!DOCTYPE fcpxml>',
            '<fcpxml version="1.9">',
            '  <resources>',
            '    <format id="r1" name="FFVideoFormat1080p25" frameDuration="100/2500s" width="1920" height="1080" colorSpace="1-1-1 (Rec. 709)"/>',
            '    <effect id="r2" name="Custom" effectID="Custom"/>',
        ]
        
        # 添加资源
        video_resources = []
        audio_resources = []
        for i, segment in enumerate(segments):
            if segment.视频文件路径:
                resource_id = f"r{3 + i * 2}"
                xml_lines.append(f'    <asset id="{resource_id}" name="{segment.分镜号}" src="file://{segment.视频文件路径}" start="0s" duration="{segment.时长}s" hasVideo="1" hasAudio="0" format="r1"/>')
                video_resources.append((resource_id, segment))
            
            for j, audio_path in enumerate(segment.音频文件路径列表):
                resource_id = f"r{3 + i * 2 + j + 1}"
                audio_duration = self._get_audio_duration(audio_path)
                xml_lines.append(f'    <asset id="{resource_id}" name="{segment.分镜号}_audio{j+1}" src="file://{audio_path}" start="0s" duration="{audio_duration}s" hasVideo="0" hasAudio="1" format="r1"/>')
                audio_resources.append((resource_id, segment, audio_path))
        
        xml_lines.extend([
            '  </resources>',
            '  <library>',
            '    <event name="自动剪辑">',
            '      <project name="自动剪辑项目">',
            '        <sequence format="r1" tcStart="0s" tcFormat="NDF" audioLayout="stereo" audioRate="48k">',
            '          <spine>',
        ])
        
        # 添加视频轨道
        current_time = 0.0
        for resource_id, segment in video_resources:
            start_frame = int(current_time * fps)
            duration_frames = int(segment.时长 * fps)
            xml_lines.extend([
                f'            <video ref="r1" offset="{start_frame}/25s" name="{segment.分镜号}" start="0s" duration="{segment.时长}s">',
                f'              <video ref="{resource_id}" offset="0s" name="{segment.分镜号}" start="0s" duration="{segment.时长}s"/>',
                '            </video>',
            ])
            current_time += segment.时长
        
        xml_lines.extend([
            '          </spine>',
            '          <audio>',
        ])
        
        # 添加音频轨道
        current_time = 0.0
        for resource_id, segment, audio_path in audio_resources:
            audio_duration = self._get_audio_duration(audio_path)
            start_frame = int(current_time * fps)
            xml_lines.extend([
                f'            <audio ref="{resource_id}" offset="{start_frame}/25s" name="{segment.分镜号}" start="0s" duration="{audio_duration}s"/>',
            ])
            current_time += audio_duration
        
        xml_lines.extend([
            '          </audio>',
            '        </sequence>',
            '      </project>',
            '    </event>',
            '  </library>',
            '</fcpxml>',
        ])
        
        return '\n'.join(xml_lines)
    
    def export_to_edl(self, episode_id: Optional[str] = None) -> str:
        """
        导出为EDL格式（Edit Decision List，通用剪辑软件格式）
        
        Args:
            episode_id: 只导出指定剧集，如果为None则导出所有剧集
            
        Returns:
            输出文件路径
        """
        logger.info("开始生成EDL文件...")
        
        # 过滤片段
        segments = self.clip_segments
        if episode_id:
            segments = [s for s in segments if self._get_episode_id(s.分镜号) == episode_id]
        
        # 生成EDL内容
        edl_lines = [
            "TITLE: 自动剪辑项目",
            f"FCM: NON-DROP FRAME",
            "",
        ]
        
        reel_number = 1
        for i, segment in enumerate(segments, 1):
            # EDL格式：序号 源卷 源入点 源出点 目标入点 目标出点
            # 时间格式：HH:MM:SS:FF (小时:分钟:秒:帧)
            fps = 25
            
            if segment.视频文件路径:
                source_in = self._timecode(0.0, fps)
                source_out = self._timecode(segment.时长, fps)
                target_in = self._timecode(segment.开始时间, fps)
                target_out = self._timecode(segment.结束时间, fps)
                
                edl_lines.append(f"{i:03d}  {reel_number:03d}  V  C        {source_in} {source_out} {target_in} {target_out}")
                edl_lines.append(f"* FROM CLIP NAME: {segment.分镜号}")
                edl_lines.append(f"* FILE: {segment.视频文件路径}")
                reel_number += 1
            
            for audio_path in segment.音频文件路径列表:
                audio_duration = self._get_audio_duration(audio_path)
                source_in = self._timecode(0.0, fps)
                source_out = self._timecode(audio_duration, fps)
                target_in = self._timecode(segment.开始时间, fps)
                target_out = self._timecode(segment.开始时间 + audio_duration, fps)
                
                edl_lines.append(f"{i:03d}  {reel_number:03d}  A  C        {source_in} {source_out} {target_in} {target_out}")
                edl_lines.append(f"* FROM CLIP NAME: {segment.分镜号}_audio")
                edl_lines.append(f"* FILE: {audio_path}")
                reel_number += 1
        
        edl_content = '\n'.join(edl_lines)
        
        # 保存文件
        filename = f"edit_{episode_id or 'all'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.edl"
        output_path = self.output_dir / filename
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(edl_content)
        
        logger.info(f"EDL文件已生成: {output_path}")
        return str(output_path)
    
    def export_to_mlt(self, episode_id: Optional[str] = None) -> str:
        """
        导出为MLT格式（Media Lovin' Toolkit，支持Kdenlive、Shotcut等）
        
        Args:
            episode_id: 只导出指定剧集，如果为None则导出所有剧集
            
        Returns:
            输出文件路径
        """
        logger.info("开始生成MLT文件...")
        
        # 过滤片段
        segments = self.clip_segments
        if episode_id:
            segments = [s for s in segments if self._get_episode_id(s.分镜号) == episode_id]
        
        # 生成MLT内容
        mlt_content = self._generate_mlt(segments)
        
        # 保存文件
        filename = f"edit_{episode_id or 'all'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mlt"
        output_path = self.output_dir / filename
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(mlt_content)
        
        logger.info(f"MLT文件已生成: {output_path}")
        
        # 验证生成的MLT文件
        try:
            from validate_mlt import MLTValidator
            validator = MLTValidator(str(output_path))
            is_valid, errors, warnings, info = validator.validate()
            
            if errors:
                logger.warning(f"MLT文件验证发现 {len(errors)} 个错误")
                for error in errors:
                    logger.warning(f"  - {error}")
            if warnings:
                logger.info(f"MLT文件验证发现 {len(warnings)} 个警告")
            if is_valid and not errors:
                logger.info("✓ MLT文件验证通过")
        except ImportError:
            logger.debug("validate_mlt模块不可用，跳过验证")
        except Exception as e:
            logger.warning(f"MLT文件验证失败: {e}")
        
        return str(output_path)
    
    def _generate_mlt(self, segments: List[ClipSegment]) -> str:
        """生成MLT XML内容"""
        fps = 25
        width = 1920
        height = 1080
        
        # 计算总时长
        # 使用所有片段的结束时间的最大值，或者累加所有片段时长
        if segments:
            # 方法1: 使用最大结束时间
            max_end_time = max([s.结束时间 for s in segments])
            # 方法2: 累加所有视频片段时长（更准确，因为视频是连续concat的）
            total_video_duration = sum([s.时长 for s in segments if s.视频文件路径])
            # 使用两者中较大的值
            total_duration = max(max_end_time, total_video_duration)
        else:
            total_duration = 0.0
        total_frames = int(total_duration * fps)
        
        xml_lines = [
            '<?xml version="1.0" encoding="utf-8"?>',
            '<mlt LC_NUMERIC="C" version="7.0.0" title="自动剪辑项目" producer="main_bin">',
            f'  <profile description="HD 1080p 25 fps" width="{width}" height="{height}" ',
            f'           progressive="1" sample_aspect_num="1" sample_aspect_den="1" ',
            f'           display_aspect_num="16" display_aspect_den="9" frame_rate_num="{fps}" ',
            f'           frame_rate_den="1" colorspace="709"/>',
            '',
        ]
        
        # 生成producer（媒体资源）
        # 重要: 为每个segment创建独立的producer和entry，确保在剪辑软件中可以单独调整
        producer_id = 0
        video_producers = []  # (producer_id, segment, has_video_file)
        audio_producers = []  # (producer_id, segment, audio_path)
        
        for segment in segments:
            # 为每个segment创建独立的视频producer
            # 关键：每个片段必须有独立的producer，这样在Shotcut中才能单独编辑
            producer_id += 1
            segment_frames = int(segment.时长 * fps)
            
            if segment.视频文件路径 and Path(segment.视频文件路径).exists():
                # 有视频文件，创建正常的producer
                file_path = Path(segment.视频文件路径).resolve().as_uri()
                video_duration = self._get_video_duration(segment.视频文件路径) or segment.时长
                video_frames = int(video_duration * fps)
                
                # 为每个片段创建独立的producer，使用唯一的ID
                producer_name = f"producer_{segment.分镜号.replace('/', '_')}"
                xml_lines.append(f'  <producer id="{producer_name}" in="0" out="{max(0, video_frames-1)}">')
                xml_lines.append(f'    <property name="resource">{file_path}</property>')
                xml_lines.append(f'    <property name="mlt_service">avformat</property>')
                xml_lines.append(f'    <property name="seekable">1</property>')
                xml_lines.append(f'    <property name="audio_index">1</property>')
                xml_lines.append(f'    <property name="video_index">0</property>')
                xml_lines.append(f'    <property name="length">{video_frames}</property>')
                xml_lines.append(f'    <property name="shot_id">{segment.分镜号}</property>')
                xml_lines.append(f'  </producer>')
                video_producers.append((producer_name, segment, True))
            else:
                # 没有视频文件，创建color producer作为占位符
                # 使用独立的producer ID，确保每个片段都可以单独编辑
                producer_name = f"producer_{segment.分镜号.replace('/', '_').replace('_', '_')}"
                xml_lines.append(f'  <producer id="{producer_name}" in="0" out="{max(0, segment_frames-1)}">')
                xml_lines.append(f'    <property name="resource">color:#000000</property>')
                xml_lines.append(f'    <property name="mlt_service">color</property>')
                xml_lines.append(f'    <property name="length">{segment_frames}</property>')
                xml_lines.append(f'    <property name="shot_id">{segment.分镜号}</property>')
                xml_lines.append(f'    <property name="missing_video">1</property>')
                # 添加更多属性以便在Shotcut中识别
                xml_lines.append(f'    <property name="kdenlive:id">{segment.分镜号}</property>')
                xml_lines.append(f'  </producer>')
                video_producers.append((producer_name, segment, False))
                logger.warning(f"片段 {segment.分镜号} 没有找到视频文件，创建color producer占位符")
            
            for audio_path in segment.音频文件路径列表:
                producer_id += 1
                file_path = Path(audio_path).resolve().as_uri()
                audio_duration = self._get_audio_duration(audio_path) or segment.时长
                audio_frames = int(audio_duration * fps)
                
                # 为每个音频文件创建独立的producer
                xml_lines.append(f'  <producer id="producer{producer_id}" in="0" out="{max(0, audio_frames-1)}">')
                xml_lines.append(f'    <property name="resource">{file_path}</property>')
                xml_lines.append(f'    <property name="mlt_service">avformat</property>')
                xml_lines.append(f'    <property name="seekable">1</property>')
                xml_lines.append(f'    <property name="audio_index">0</property>')
                xml_lines.append(f'    <property name="video_index">-1</property>')
                xml_lines.append(f'    <property name="length">{audio_frames}</property>')
                # 添加元数据，方便在剪辑软件中识别
                xml_lines.append(f'    <property name="shot_id">{segment.分镜号}</property>')
                xml_lines.append(f'  </producer>')
                audio_producers.append((producer_id, segment, audio_path))
        
        # 生成playlist（时间线）
        xml_lines.extend([
            '',
            '  <playlist id="playlist0">',
        ])
        
        # 添加视频轨道
        # 重要: 每个视频片段必须是独立的entry，这样在剪辑软件中才能单独调整
        # 视频片段按顺序连续排列，每个片段对应一个独立的entry
        video_playlist_duration = 0
        for producer_name, segment, has_video_file in video_producers:
            duration_frames = int(segment.时长 * fps)
            
            # 每个视频片段创建独立的entry，使用producer的实际名称
            # 关键：每个entry都是独立的，可以在Shotcut中单独选择、移动、删除
            # 注意：entry的in/out应该相对于producer，而不是时间线
            # 对于视频文件，使用完整的producer范围；对于color producer，使用segment时长
            if has_video_file:
                # 有视频文件，entry的out值应该基于producer的实际长度
                producer_out = max(0, duration_frames - 1)
            else:
                # color producer，使用segment时长
                producer_out = max(0, duration_frames - 1)
            
            xml_lines.append(f'    <entry producer="{producer_name}" in="0" out="{producer_out}">')
            xml_lines.append(f'      <property name="shot_id">{segment.分镜号}</property>')
            if not has_video_file:
                xml_lines.append(f'      <property name="missing_video">1</property>')
            xml_lines.append(f'    </entry>')
            
            video_playlist_duration += duration_frames
        
        xml_lines.append('  </playlist>')
        
        # 添加音频轨道
        if audio_producers:
            xml_lines.append('')
            xml_lines.append('  <playlist id="playlist1">')
            
            current_frame = 0
            for producer_id, segment, audio_path in audio_producers:
                start_frame = int(segment.开始时间 * fps)
                audio_duration = self._get_audio_duration(audio_path) or segment.时长
                duration_frames = int(audio_duration * fps)
                
                # 如果时间不连续，添加空白
                if start_frame > current_frame:
                    blank_frames = start_frame - current_frame
                    xml_lines.append(f'    <blank length="{blank_frames}"/>')
                
                xml_lines.append(f'    <entry producer="producer{producer_id}" in="0" out="{max(0, duration_frames-1)}"/>')
                current_frame = start_frame + duration_frames
            
            xml_lines.append('  </playlist>')
        
        # 生成tractor（多轨道合成）
        # 计算实际的总帧数（使用视频轨道或音频轨道中较长的）
        audio_playlist_frames = current_frame if audio_producers else 0
        actual_total_frames = max(video_playlist_duration, audio_playlist_frames, total_frames)
        
        # Shotcut/Kdenlive期望的结构
        # 重要：确保tractor正确引用playlist，这样每个playlist中的entry都会显示为独立的片段
        # 关键：tractor的root属性应该指向主playlist，这样Shotcut才能正确识别每个片段
        xml_lines.extend([
            '',
            '  <tractor id="tractor0" title="自动剪辑项目" in="0" out="{}">'.format(max(0, actual_total_frames-1)),
            '    <property name="shotcut:projectName">自动剪辑项目</property>',
            '    <property name="shotcut:projectNotes"></property>',
            '    <track producer="playlist0"/>',
        ])
        
        if audio_producers:
            xml_lines.append('    <track producer="playlist1"/>')
            # 只有当有音频轨道时才添加transition来混合音视频
            xml_lines.extend([
                '    <transition id="transition0">',
                '      <property name="a_track">0</property>',
                '      <property name="b_track">1</property>',
                '      <property name="mlt_service">mix</property>',
                '      <property name="always_active">1</property>',
                '      <property name="sum">1</property>',
                '    </transition>',
            ])
        
        xml_lines.extend([
            '  </tractor>',
            '',
            '</mlt>',
        ])
        
        return '\n'.join(xml_lines)
    
    def export_video(
        self,
        episode_id: Optional[str] = None,
        output_filename: Optional[str] = None,
        fps: int = 25,
        video_codec: str = "libx264",
        audio_codec: str = "aac",
        video_bitrate: str = "5000k",
        audio_bitrate: str = "192k"
    ) -> str:
        """
        直接导出最终影片（使用ffmpeg）
        
        Args:
            episode_id: 只导出指定剧集，如果为None则导出所有剧集
            output_filename: 输出文件名，如果为None则自动生成
            fps: 视频帧率（默认: 25）
            video_codec: 视频编码器（默认: libx264）
            audio_codec: 音频编码器（默认: aac）
            video_bitrate: 视频比特率（默认: 5000k）
            audio_bitrate: 音频比特率（默认: 192k）
            
        Returns:
            输出文件路径
        """
        logger.info("开始导出影片...")
        
        # 检查ffmpeg是否可用
        if not shutil.which("ffmpeg"):
            raise RuntimeError("未找到ffmpeg，请先安装ffmpeg")
        
        # 过滤片段
        segments = self.clip_segments
        if episode_id:
            segments = [s for s in segments if self._get_episode_id(s.分镜号) == episode_id]
        
        if not segments:
            raise ValueError("没有可用的剪辑片段")
        
        # 生成输出文件名
        if not output_filename:
            output_filename = f"edit_{episode_id or 'all'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
        
        output_path = self.output_dir / output_filename
        
        # 创建临时文件列表
        concat_file = self.output_dir / f"concat_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        
        try:
            # 生成concat文件
            with open(concat_file, 'w', encoding='utf-8') as f:
                for segment in segments:
                    if segment.视频文件路径:
                        # 检查文件是否存在
                        if not Path(segment.视频文件路径).exists():
                            logger.warning(f"视频文件不存在: {segment.视频文件路径}")
                            continue
                        
                        # 如果时长不匹配，需要裁剪
                        video_duration = self._get_video_duration(segment.视频文件路径)
                        if video_duration > segment.时长:
                            # 需要裁剪视频
                            f.write(f"file '{segment.视频文件路径}'\n")
                            f.write(f"inpoint {0.0}\n")
                            f.write(f"outpoint {segment.时长}\n")
                        else:
                            f.write(f"file '{segment.视频文件路径}'\n")
            
            # 使用ffmpeg合并视频
            cmd = [
                "ffmpeg",
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_file),
                "-c:v", video_codec,
                "-b:v", video_bitrate,
                "-r", str(fps),
                "-c:a", audio_codec,
                "-b:a", audio_bitrate,
                "-y",  # 覆盖输出文件
                str(output_path)
            ]
            
            logger.info(f"执行ffmpeg命令: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                logger.error(f"ffmpeg执行失败: {result.stderr}")
                raise RuntimeError(f"ffmpeg执行失败: {result.stderr}")
            
            # 如果有音频文件，需要合并音频轨道
            # 重要: 需要根据时间线正确对齐音频，确保音频与视频同步
            # 策略: 视频是按顺序concat的，所以音频也应该按视频片段的顺序对齐
            # 每个视频片段对应一段音频，如果音频时长不够，用静音填充；如果太长，裁剪
            audio_segments_by_video = []
            for segment in segments:
                if segment.视频文件路径:
                    # 为每个视频片段收集对应的音频
                    segment_audios = []
                    for audio_path in segment.音频文件路径列表:
                        if Path(audio_path).exists():
                            audio_duration = self._get_audio_duration(audio_path)
                            segment_audios.append({
                                "path": audio_path,
                                "duration": audio_duration or segment.时长,
                                "segment_duration": segment.时长
                            })
                    audio_segments_by_video.append({
                        "segment": segment,
                        "audios": segment_audios
                    })
            
            if audio_segments_by_video and any(item["audios"] for item in audio_segments_by_video):
                # 为每个视频片段准备对应的音频
                # 如果片段有多个音频，先混合；如果没有音频，生成静音
                temp_audio_files = []
                
                for item in audio_segments_by_video:
                    segment = item["segment"]
                    audios = item["audios"]
                    
                    if audios:
                        if len(audios) == 1:
                            # 单个音频
                            audio_path = audios[0]["path"]
                            audio_duration = audios[0]["duration"]
                            
                            if audio_duration < segment.时长:
                                # 音频时长不够，需要延长：先添加音频，再添加静音
                                temp_segment_audio = self.output_dir / f"temp_seg_audio_{segment.分镜号.replace('/', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.m4a"
                                silence_duration = segment.时长 - audio_duration
                                
                                # 使用filter_complex来连接音频和静音
                                extend_cmd = [
                                    "ffmpeg",
                                    "-i", audio_path,
                                    "-f", "lavfi",
                                    "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
                                    "-filter_complex", f"[0:a][1:a]concat=n=2:v=0:a=1[out]",
                                    "-map", "[out]",
                                    "-t", str(segment.时长),  # 确保总时长正确
                                    "-c:a", audio_codec,
                                    "-b:a", audio_bitrate,
                                    "-ar", "48000",
                                    "-y",
                                    str(temp_segment_audio)
                                ]
                                result = subprocess.run(extend_cmd, capture_output=True, text=True)
                                if result.returncode == 0:
                                    temp_audio_files.append(str(temp_segment_audio))
                                else:
                                    logger.warning(f"延长音频失败，使用原音频: {result.stderr}")
                                    temp_audio_files.append(audio_path)
                            elif audio_duration > segment.时长:
                                # 音频时长太长，需要裁剪
                                temp_segment_audio = self.output_dir / f"temp_seg_audio_{segment.分镜号.replace('/', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.m4a"
                                trim_cmd = [
                                    "ffmpeg",
                                    "-i", audio_path,
                                    "-t", str(segment.时长),
                                    "-c:a", audio_codec,
                                    "-b:a", audio_bitrate,
                                    "-y",
                                    str(temp_segment_audio)
                                ]
                                result = subprocess.run(trim_cmd, capture_output=True, text=True)
                                if result.returncode == 0:
                                    temp_audio_files.append(str(temp_segment_audio))
                                else:
                                    logger.warning(f"裁剪音频失败，使用原音频: {result.stderr}")
                                    temp_audio_files.append(audio_path)
                            else:
                                # 时长正好
                                temp_audio_files.append(audio_path)
                        else:
                            # 多个音频，需要混合
                            temp_mixed = self.output_dir / f"temp_mixed_{segment.分镜号.replace('/', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.m4a"
                            mix_inputs = []
                            for a in audios:
                                mix_inputs.extend(["-i", a["path"]])
                            
                            mix_cmd = [
                                "ffmpeg",
                            ] + mix_inputs + [
                                "-filter_complex", f"amix=inputs={len(audios)}:duration=longest:dropout_transition=0",
                                "-t", str(segment.时长),  # 确保不超过片段时长
                                "-c:a", audio_codec,
                                "-b:a", audio_bitrate,
                                "-ar", "48000",
                                "-y",
                                str(temp_mixed)
                            ]
                            result = subprocess.run(mix_cmd, capture_output=True, text=True)
                            if result.returncode == 0:
                                temp_audio_files.append(str(temp_mixed))
                            else:
                                logger.warning(f"混合音频失败，使用第一个音频: {result.stderr}")
                                temp_audio_files.append(audios[0]["path"])
                    else:
                        # 没有音频，生成静音
                        silence_file = self.output_dir / f"silence_{segment.分镜号.replace('/', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
                        silence_cmd = [
                            "ffmpeg",
                            "-f", "lavfi",
                            "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
                            "-t", str(segment.时长),
                            "-y",
                            str(silence_file)
                        ]
                        result = subprocess.run(silence_cmd, capture_output=True, text=True)
                        if result.returncode == 0:
                            temp_audio_files.append(str(silence_file))
                        else:
                            logger.warning(f"生成静音失败: {result.stderr}")
                
                # 按顺序连接所有音频片段
                if temp_audio_files:
                    audio_concat_file = self.output_dir / f"audio_concat_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                    with open(audio_concat_file, 'w', encoding='utf-8') as f:
                        for audio_file in temp_audio_files:
                            f.write(f"file '{audio_file}'\n")
                    
                    # 合并音频
                    temp_audio = self.output_dir / f"temp_audio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.m4a"
                    audio_cmd = [
                        "ffmpeg",
                        "-f", "concat",
                        "-safe", "0",
                        "-i", str(audio_concat_file),
                        "-c:a", audio_codec,
                        "-b:a", audio_bitrate,
                        "-ar", "48000",
                        "-ac", "2",
                        "-y",
                        str(temp_audio)
                    ]
                    
                    logger.info(f"执行音频合并命令: {' '.join(audio_cmd)}")
                    result = subprocess.run(audio_cmd, capture_output=True, text=True)
                    
                    if result.returncode == 0:
                        # 将音频合并到视频
                        final_output = self.output_dir / f"final_{output_filename}"
                        final_cmd = [
                            "ffmpeg",
                            "-i", str(output_path),
                            "-i", str(temp_audio),
                            "-c:v", "copy",
                            "-c:a", audio_codec,
                            "-b:a", audio_bitrate,
                            "-map", "0:v:0",
                            "-map", "1:a:0",
                            "-shortest",
                            "-y",
                            str(final_output)
                        ]
                        
                        logger.info(f"执行音视频合并命令: {' '.join(final_cmd)}")
                        result = subprocess.run(final_cmd, capture_output=True, text=True)
                        if result.returncode == 0:
                            # 替换原文件
                            if output_path.exists():
                                output_path.unlink()
                            final_output.rename(output_path)
                            logger.info(f"✓ 音视频已正确同步并合并")
                        else:
                            logger.error(f"音视频合并失败: {result.stderr}")
                            logger.warning(f"仅视频文件已保存: {output_path}")
                        
                        # 清理临时文件
                        if temp_audio.exists():
                            temp_audio.unlink()
                    else:
                        logger.error(f"音频合并失败: {result.stderr}")
                        logger.warning(f"仅视频文件已保存: {output_path}")
                    
                    # 清理临时文件
                    if audio_concat_file.exists():
                        audio_concat_file.unlink()
                    
                    # 清理临时音频文件
                    for temp_file in temp_audio_files:
                        temp_path = Path(temp_file)
                        if temp_path.exists() and "temp_" in temp_path.name:
                            try:
                                temp_path.unlink()
                            except:
                                pass
            else:
                logger.info("未找到音频文件,仅导出视频")
            
            logger.info(f"影片已导出: {output_path}")
            return str(output_path)
            
        finally:
            # 清理临时文件
            if concat_file.exists():
                concat_file.unlink()
    
    def _merge_audio_simple(
        self, 
        audio_segments: List[Dict], 
        video_path: Path, 
        output_filename: str,
        audio_codec: str,
        audio_bitrate: str,
        total_duration: float
    ):
        """简单的音频合并方法（回退方案）"""
        try:
            # 创建音频时间线文件
            audio_timeline_file = self.output_dir / f"audio_timeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            
            with open(audio_timeline_file, 'w', encoding='utf-8') as f:
                current_time = 0.0
                for audio_seg in sorted(audio_segments, key=lambda x: x["start_time"]):
                    # 如果音频开始时间与当前时间不一致，添加静音
                    if audio_seg["start_time"] > current_time:
                        silence_duration = audio_seg["start_time"] - current_time
                        # 使用anullsrc生成静音
                        f.write(f"file 'anullsrc=channel_layout=stereo:sample_rate=48000'\n")
                        f.write(f"inpoint 0\n")
                        f.write(f"outpoint {silence_duration}\n")
                    
                    # 添加音频文件
                    f.write(f"file '{audio_seg['path']}'\n")
                    # 如果音频时长小于片段时长，在末尾添加静音
                    if audio_seg["duration"] < audio_seg["segment_duration"]:
                        remaining = audio_seg["segment_duration"] - audio_seg["duration"]
                        f.write(f"file 'anullsrc=channel_layout=stereo:sample_rate=48000'\n")
                        f.write(f"inpoint 0\n")
                        f.write(f"outpoint {remaining}\n")
                    
                    current_time = max(current_time, audio_seg["start_time"]) + audio_seg["segment_duration"]
            
            # 合并音频
            temp_audio = self.output_dir / f"temp_audio_simple_{datetime.now().strftime('%Y%m%d_%H%M%S')}.m4a"
            audio_cmd = [
                "ffmpeg",
                "-f", "concat",
                "-safe", "0",
                "-i", str(audio_timeline_file),
                "-c:a", audio_codec,
                "-b:a", audio_bitrate,
                "-y",
                str(temp_audio)
            ]
            
            result = subprocess.run(audio_cmd, capture_output=True, text=True)
            if result.returncode == 0:
                # 合并到视频
                final_output = self.output_dir / f"final_{output_filename}"
                final_cmd = [
                    "ffmpeg",
                    "-i", str(video_path),
                    "-i", str(temp_audio),
                    "-c:v", "copy",
                    "-c:a", audio_codec,
                    "-map", "0:v:0",
                    "-map", "1:a:0",
                    "-shortest",
                    "-y",
                    str(final_output)
                ]
                
                result = subprocess.run(final_cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    if video_path.exists():
                        video_path.unlink()
                    final_output.rename(video_path)
                    logger.info("✓ 使用简单方法完成音视频合并")
                else:
                    logger.error(f"简单方法合并失败: {result.stderr}")
            
            # 清理
            if audio_timeline_file.exists():
                audio_timeline_file.unlink()
            if temp_audio.exists():
                temp_audio.unlink()
                
        except Exception as e:
            logger.error(f"简单音频合并方法失败: {e}")
    
    def _get_episode_id(self, shot_id: str) -> str:
        """从分镜号提取剧集ID"""
        parts = shot_id.split('_')
        return parts[0] if parts else ""
    
    def _timecode(self, seconds: float, fps: int) -> str:
        """将秒数转换为时间码格式 HH:MM:SS:FF"""
        total_frames = int(seconds * fps)
        hours = total_frames // (fps * 3600)
        minutes = (total_frames // (fps * 60)) % 60
        secs = (total_frames // fps) % 60
        frames = total_frames % fps
        return f"{hours:02d}:{minutes:02d}:{secs:02d}:{frames:02d}"
    
    def _get_video_duration(self, video_path: str) -> float:
        """获取视频时长（秒）"""
        if not shutil.which("ffprobe"):
            logger.warning("未找到ffprobe，无法获取视频时长，使用默认值")
            return 0.0
        
        try:
            cmd = [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                return float(result.stdout.strip())
        except Exception as e:
            logger.warning(f"获取视频时长失败: {e}")
        
        return 0.0
    
    def _get_audio_duration(self, audio_path: str) -> float:
        """获取音频时长（秒）"""
        if not shutil.which("ffprobe"):
            logger.warning("未找到ffprobe，无法获取音频时长，使用默认值")
            return 0.0
        
        try:
            cmd = [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                audio_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                return float(result.stdout.strip())
        except Exception as e:
            logger.warning(f"获取音频时长失败: {e}")
        
        return 0.0


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='自动剪辑程序 - 根据Excel剪辑汇总数据创建剪辑项目')
    parser.add_argument('--excel', type=str, default='all_episodes.xlsx',
                       help='Excel文件路径 (默认: all_episodes.xlsx)')
    parser.add_argument('--video-dir', type=str, default='./output',
                       help='视频文件目录 (默认: ./output)')
    parser.add_argument('--audio-dir', type=str, default=None,
                       help='音频文件目录 (默认: 与video-dir相同)')
    parser.add_argument('--output-dir', type=str, default='./edit_output',
                       help='输出目录 (默认: ./edit_output)')
    parser.add_argument('--episode', type=str, default=None,
                       help='只处理指定剧集 (如: EP01)，如果未指定则处理所有剧集')
    
    # 导出格式选择
    parser.add_argument('--export-jianying', action='store_true',
                       help='导出为剪映草稿格式')
    parser.add_argument('--export-fcpxml', action='store_true',
                       help='导出为FCPXML格式')
    parser.add_argument('--export-edl', action='store_true',
                       help='导出为EDL格式')
    parser.add_argument('--export-mlt', action='store_true',
                       help='导出为MLT格式(支持Kdenlive、Shotcut等)')
    parser.add_argument('--export-video', action='store_true',
                       help='直接导出最终影片')
    
    # 视频导出参数
    parser.add_argument('--output-filename', type=str, default=None,
                       help='输出视频文件名 (默认: 自动生成)')
    parser.add_argument('--fps', type=int, default=25,
                       help='视频帧率 (默认: 25)')
    parser.add_argument('--video-codec', type=str, default='libx264',
                       help='视频编码器 (默认: libx264)')
    parser.add_argument('--audio-codec', type=str, default='aac',
                       help='音频编码器 (默认: aac)')
    parser.add_argument('--video-bitrate', type=str, default='5000k',
                       help='视频比特率 (默认: 5000k)')
    parser.add_argument('--audio-bitrate', type=str, default='192k',
                       help='音频比特率 (默认: 192k)')
    
    args = parser.parse_args()
    
    try:
        # 创建剪辑器
        editor = VideoEditor(
            excel_path=args.excel,
            video_dir=args.video_dir,
            audio_dir=args.audio_dir,
            output_dir=args.output_dir
        )
        
        # 导出
        if args.export_jianying:
            output_path = editor.export_to_jianying(args.episode)
            print(f"\n✓ 剪映草稿已生成: {output_path}")
        
        if args.export_fcpxml:
            output_path = editor.export_to_fcpxml(args.episode)
            print(f"\n✓ FCPXML文件已生成: {output_path}")
        
        if args.export_edl:
            output_path = editor.export_to_edl(args.episode)
            print(f"\n✓ EDL文件已生成: {output_path}")
        
        if args.export_mlt:
            output_path = editor.export_to_mlt(args.episode)
            print(f"\n✓ MLT文件已生成: {output_path}")
        
        if args.export_video:
            output_path = editor.export_video(
                episode_id=args.episode,
                output_filename=args.output_filename,
                fps=args.fps,
                video_codec=args.video_codec,
                audio_codec=args.audio_codec,
                video_bitrate=args.video_bitrate,
                audio_bitrate=args.audio_bitrate
            )
            print(f"\n✓ 影片已导出: {output_path}")
        
        # 如果没有指定任何导出格式，显示帮助信息
        if not any([args.export_jianying, args.export_fcpxml, args.export_edl, args.export_mlt, args.export_video]):
            print("\n请指定至少一种导出格式:")
            print("  --export-jianying  导出为剪映草稿")
            print("  --export-fcpxml    导出为FCPXML格式")
            print("  --export-edl       导出为EDL格式")
            print("  --export-mlt       导出为MLT格式(支持Kdenlive、Shotcut等)")
            print("  --export-video     直接导出影片")
            print("\n使用 --help 查看完整帮助信息")
        
    except Exception as e:
        logger.error(f"处理失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())

