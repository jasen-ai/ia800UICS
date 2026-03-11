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
Qwen3-TTS 语音克隆客户端 - 用于调用ComfyUI的Qwen3-TTSVoiceCloneAPI工作流
支持语音克隆音频生成
"""
import json
import os
import argparse
import sys
from pathlib import Path
from typing import Dict, Any, Optional

# 导入ComfyUI客户端
from comfyui_client import ComfyUIClient


class Qwen3TTSClient:
    """Qwen3-TTS语音克隆客户端"""
    
    def __init__(
        self,
        server_address: str = "127.0.0.1:8188",
        workflow_path: str = "Qwen3-TTSVoiceCloneAPI.json",
        output_dir: str = "./output"
    ):
        """
        初始化Qwen3-TTS客户端
        
        Args:
            server_address: ComfyUI服务器地址，格式为 "host:port"
            workflow_path: 工作流JSON文件路径
            output_dir: 输出目录
        """
        self.server_address = server_address
        self.workflow_path = workflow_path
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        
        # 创建ComfyUI客户端
        self.client = ComfyUIClient(server_address=server_address)
        
        # 工作流节点ID（根据Qwen3-TTSVoiceCloneAPI.json）
        self.NODE_LOAD_AUDIO = "6"  # LoadAudio节点
        self.NODE_SAVE_AUDIO = "8"  # SaveAudio节点
        self.NODE_VOICE_CLONE = "39"  # Qwen3TTSVoiceClone节点
    
    def load_workflow(self) -> Dict[str, Any]:
        """
        加载工作流文件
        
        Returns:
            工作流字典
        """
        if not os.path.exists(self.workflow_path):
            raise FileNotFoundError(
                f"工作流文件不存在: {self.workflow_path}\n"
                f"请确保文件存在于当前目录，或使用 --workflow 参数指定完整路径"
            )
        
        return self.client.load_workflow(self.workflow_path)
    
    def generate_audio(
        self,
        ref_audio_path: str,
        target_text: str,
        target_language: str = "Chinese",
        seed: Optional[int] = None,
        temperature: float = 0.9,
        top_p: float = 1.0,
        top_k: int = 50,
        repetition_penalty: float = 1.05,
        max_new_tokens: int = 2048,
        output_mode: str = "Concatenate (Merge)",
        filename_prefix: Optional[str] = None,
        ref_text: Optional[str] = None,
        instruct: Optional[str] = None,
        wait: bool = True
    ) -> Dict[str, Any]:
        """
        生成语音克隆音频
        
        Args:
            ref_audio_path: 参考音频文件路径（用于语音克隆）
            target_text: 要生成的文本内容
            target_language: 目标语言（默认: "Chinese"）
            seed: 随机种子（可选）
            temperature: 温度参数（默认: 0.9）
            top_p: Top-p采样参数（默认: 1.0）
            top_k: Top-k采样参数（默认: 50）
            repetition_penalty: 重复惩罚（默认: 1.05）
            max_new_tokens: 最大生成token数（默认: 2048）
            output_mode: 输出模式（默认: "Concatenate (Merge)"）
            filename_prefix: 输出文件名前缀（可选）
            ref_text: 参考文本（可选，如果不提供则使用ASR自动识别）
            instruct: 指令文本（可选）
            wait: 是否等待执行完成（默认: True）
            
        Returns:
            执行结果字典，包含生成的音频信息
        """
        # 连接服务器
        if not self.client.is_running:
            print("正在连接ComfyUI服务器...")
            self.client.connect()
        
        # 加载工作流
        print(f"正在加载工作流: {self.workflow_path}")
        workflow = self.load_workflow()
        
        # 检查参考音频文件
        if not os.path.exists(ref_audio_path):
            raise FileNotFoundError(f"参考音频文件不存在: {ref_audio_path}")
        
        # 上传参考音频文件到ComfyUI
        try:
            print(f"正在上传参考音频文件: {ref_audio_path}")
            uploaded_result = self.client.upload_file(ref_audio_path, subfolder="input")
            print(f"  上传成功: {uploaded_result}")
            
            # LoadAudio 节点：工作流中为纯文件名（如 ComfyUI_00008_.mp3），节点会在 input 目录下查找
            # 传 "input/文件名" 会导致校验失败，只传文件名即可
            if isinstance(uploaded_result, dict):
                name = uploaded_result.get('name', os.path.basename(ref_audio_path))
            else:
                name = str(uploaded_result).strip() if uploaded_result else os.path.basename(ref_audio_path)
            audio_path = name.split("/")[-1] if "/" in name else name  # 仅文件名
            print(f"  使用音频路径: {audio_path}")
                
        except Exception as e:
            print(f"警告: 上传文件失败: {e}")
            audio_path = os.path.basename(ref_audio_path)
            print(f"  尝试使用文件名: {audio_path}")
        
        # 更新LoadAudio节点的音频文件路径
        if not self.client.update_workflow_input(workflow, self.NODE_LOAD_AUDIO, 'audio', audio_path):
            raise ValueError(f"无法更新节点 {self.NODE_LOAD_AUDIO} 的音频文件")
        print(f"已更新参考音频: {audio_path} (节点 {self.NODE_LOAD_AUDIO})")
        
        # 更新Qwen3TTSVoiceClone节点的参数
        voice_clone_inputs = workflow[self.NODE_VOICE_CLONE]['inputs']
        voice_clone_inputs['target_text'] = target_text
        voice_clone_inputs['target_language'] = target_language
        voice_clone_inputs['output_mode'] = output_mode
        voice_clone_inputs['temperature'] = temperature
        voice_clone_inputs['top_p'] = top_p
        voice_clone_inputs['top_k'] = top_k
        voice_clone_inputs['repetition_penalty'] = repetition_penalty
        voice_clone_inputs['max_new_tokens'] = max_new_tokens
        
        if seed is not None:
            voice_clone_inputs['seed'] = seed
        
        if ref_text is not None:
            voice_clone_inputs['ref_text'] = ref_text
        
        if instruct is not None:
            voice_clone_inputs['instruct'] = instruct
        
        print(f"已更新生成参数:")
        print(f"  目标文本: {target_text[:50]}..." if len(target_text) > 50 else f"  目标文本: {target_text}")
        print(f"  目标语言: {target_language}")
        print(f"  输出模式: {output_mode}")
        print(f"  温度: {temperature}")
        print(f"  Top-p: {top_p}")
        print(f"  Top-k: {top_k}")
        print(f"  重复惩罚: {repetition_penalty}")
        print(f"  最大token数: {max_new_tokens}")
        if seed is not None:
            print(f"  随机种子: {seed}")
        
        # 更新SaveAudio节点的文件名前缀
        if filename_prefix:
            workflow[self.NODE_SAVE_AUDIO]['inputs']['filename_prefix'] = filename_prefix
            print(f"已更新输出文件名前缀: {filename_prefix}")
        
        # 执行工作流
        print("正在执行工作流...")
        result = self.client.execute_workflow(workflow, wait=wait)
        
        print(f"\n执行完成!")
        print(f"Prompt ID: {result['prompt_id']}")
        
        # 保存音频输出
        if result.get('audio'):
            print("\n保存音频文件...")
            for node_id, audio_info in result['audio'].items():
                try:
                    audio_data = self.client.get_audio(
                        audio_info['filename'],
                        audio_info.get('subfolder', ''),
                        audio_info.get('type', 'output')
                    )
                    output_path = os.path.join(self.output_dir, audio_info['filename'])
                    with open(output_path, 'wb') as f:
                        f.write(audio_data)
                    print(f"  保存: {output_path}")
                    
                    # 更新结果字典
                    result['audio_file'] = output_path
                    result['audio_filename'] = audio_info['filename']
                    result['audio_size'] = len(audio_data)
                except Exception as e:
                    print(f"  警告: 无法保存音频文件: {e}")
        
        return result
    
    def connect(self):
        """连接到ComfyUI服务器"""
        self.client.connect()
    
    def disconnect(self):
        """断开连接"""
        self.client.disconnect()


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='Qwen3-TTS语音克隆客户端 - 调用ComfyUI的Qwen3-TTSVoiceCloneAPI工作流',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 基本使用
  python qwen3_tts_client.py \\
    --ref-audio input/reference.wav \\
    --text "我想用这个声音说这句话。"

  # 指定输出文件名前缀
  python qwen3_tts_client.py \\
    --ref-audio input/reference.wav \\
    --text "测试语音克隆" \\
    --output-prefix "test_output"

  # 使用自定义参数
  python qwen3_tts_client.py \\
    --ref-audio input/reference.wav \\
    --text "测试文本" \\
    --temperature 0.8 \\
    --seed 12345 \\
    --language "English"

  # 指定ComfyUI服务器地址
  python qwen3_tts_client.py \\
    --server 192.168.1.100:8188 \\
    --ref-audio input/reference.wav \\
    --text "测试文本"
        """
    )
    
    parser.add_argument(
        '--server',
        type=str,
        default='127.0.0.1:8188',
        help='ComfyUI服务器地址 (默认: 127.0.0.1:8188)'
    )
    parser.add_argument(
        '--workflow',
        type=str,
        default='Qwen3-TTSVoiceCloneAPI.json',
        help='工作流JSON文件路径 (默认: Qwen3-TTSVoiceCloneAPI.json)'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        default='./output',
        help='输出目录 (默认: ./output)'
    )
    parser.add_argument(
        '--ref-audio',
        type=str,
        required=True,
        help='参考音频文件路径（用于语音克隆）'
    )
    parser.add_argument(
        '--text',
        type=str,
        required=True,
        help='要生成的文本内容'
    )
    parser.add_argument(
        '--language',
        type=str,
        default='Chinese',
        choices=['Chinese', 'English'],
        help='目标语言 (默认: Chinese)'
    )
    parser.add_argument(
        '--seed',
        type=int,
        default=None,
        help='随机种子（可选）'
    )
    parser.add_argument(
        '--temperature',
        type=float,
        default=0.9,
        help='温度参数 (默认: 0.9)'
    )
    parser.add_argument(
        '--top-p',
        type=float,
        default=1.0,
        help='Top-p采样参数 (默认: 1.0)'
    )
    parser.add_argument(
        '--top-k',
        type=int,
        default=50,
        help='Top-k采样参数 (默认: 50)'
    )
    parser.add_argument(
        '--repetition-penalty',
        type=float,
        default=1.05,
        help='重复惩罚 (默认: 1.05)'
    )
    parser.add_argument(
        '--max-tokens',
        type=int,
        default=2048,
        help='最大生成token数 (默认: 2048)'
    )
    parser.add_argument(
        '--output-mode',
        type=str,
        default='Concatenate (Merge)',
        choices=['Concatenate (Merge)', 'Separate'],
        help='输出模式 (默认: Concatenate (Merge))'
    )
    parser.add_argument(
        '--output-prefix',
        type=str,
        default=None,
        help='输出文件名前缀（可选）'
    )
    parser.add_argument(
        '--ref-text',
        type=str,
        default=None,
        help='参考文本（可选，如果不提供则使用ASR自动识别）'
    )
    parser.add_argument(
        '--instruct',
        type=str,
        default=None,
        help='指令文本（可选）'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='显示调试信息'
    )
    
    args = parser.parse_args()
    
    # 创建客户端
    client = Qwen3TTSClient(
        server_address=args.server,
        workflow_path=args.workflow,
        output_dir=args.output_dir
    )
    
    try:
        # 连接服务器
        print("正在连接ComfyUI服务器...")
        client.connect()
        
        # 生成音频
        result = client.generate_audio(
            ref_audio_path=args.ref_audio,
            target_text=args.text,
            target_language=args.language,
            seed=args.seed,
            temperature=args.temperature,
            top_p=args.top_p,
            top_k=args.top_k,
            repetition_penalty=args.repetition_penalty,
            max_new_tokens=args.max_tokens,
            output_mode=args.output_mode,
            filename_prefix=args.output_prefix,
            ref_text=args.ref_text,
            instruct=args.instruct,
            wait=True
        )
        
        # 显示结果
        if result.get('audio_file'):
            print(f"\n✓ 音频生成成功!")
            print(f"  文件路径: {result['audio_file']}")
            print(f"  文件大小: {result.get('audio_size', 0)} 字节")
        else:
            print("\n⚠ 警告: 未找到生成的音频文件")
            if args.debug:
                print(f"  完整结果: {json.dumps(result, indent=2, ensure_ascii=False)}")
        
    except Exception as e:
        print(f"\n✗ 错误: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)
    finally:
        client.disconnect()


if __name__ == "__main__":
    main()

