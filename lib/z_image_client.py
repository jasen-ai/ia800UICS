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
Z-Image Turbo 客户端 - 用于调用ComfyUI z-image-turbo工作流
基于ComfyUI客户端，专门用于图像生成
支持 act_02_qwen_Image_edit-aigc-3-api.json 工作流（1/2/3 张参考图）
"""
import json
import os
import argparse
import logging
from typing import List, Optional
from comfyui_client import ComfyUIClient

logger = logging.getLogger(__name__)

# 三参考图 Qwen Image Edit 工作流文件名（与 z_image_client 同目录）
QWEN_IMAGE_EDIT_3REF_WORKFLOW = "act_02_qwen_Image_edit-aigc-3-api.json"
# 工作流中节点 ID：78=图1, 120=图2, 121=图3；115:111=正提示词；115:110=负提示词；60=SaveImage；115:3=KSampler
QWEN_EDIT_NODE_IMAGE1 = "78"
QWEN_EDIT_NODE_IMAGE2 = "120"
QWEN_EDIT_NODE_IMAGE3 = "121"
QWEN_EDIT_NODE_PROMPT_POS = "115:111"
QWEN_EDIT_NODE_SAVE = "60"
QWEN_EDIT_NODE_SAMPLER = "115:3"


class ZImageClient(ComfyUIClient):
    """Z-Image Turbo工作流专用客户端"""
    
    def __init__(self, server_address: str = "127.0.0.1:8188", workflow_path: str = None):
        """
        初始化Z-Image客户端
        
        Args:
            server_address: ComfyUI服务器地址
            workflow_path: 工作流JSON文件路径（可选，默认使用内置工作流）
        """
        super().__init__(server_address)
        if workflow_path is None:
            # 使用默认工作流路径
            workflow_path = os.path.join(os.path.dirname(__file__), "z_image_workflow.json")
        self.workflow_path = workflow_path
        self.default_workflow = None
    
    def load_default_workflow(self) -> dict:
        """加载默认工作流"""
        if self.default_workflow is None:
            if os.path.exists(self.workflow_path):
                self.default_workflow = self.load_workflow(self.workflow_path)
            else:
                raise FileNotFoundError(f"工作流文件不存在: {self.workflow_path}")
        return self.default_workflow.copy()
    
    def update_prompt(self, workflow: dict, prompt: str) -> bool:
        """
        更新提示文本（节点58）
        
        Args:
            workflow: 工作流字典
            prompt: 新的提示文本
            
        Returns:
            是否成功更新
        """
        return self.update_workflow_input(workflow, "58", "value", prompt)
    
    def update_style_prefix(self, workflow: dict, style_prefix: str) -> bool:
        """
        更新风格前缀（节点61的string_a）
        
        Args:
            workflow: 工作流字典
            style_prefix: 风格前缀文本（例如："Pixel art style,"）
            
        Returns:
            是否成功更新
        """
        return self.update_workflow_input(workflow, "61", "string_a", style_prefix)
    
    def update_seed(self, workflow: dict, seed: int) -> bool:
        """
        更新随机种子（节点57:3）
        
        Args:
            workflow: 工作流字典
            seed: 随机种子
            
        Returns:
            是否成功更新
        """
        return self.update_workflow_input(workflow, "57:3", "seed", seed)
    
    def update_steps(self, workflow: dict, steps: int) -> bool:
        """
        更新采样步数（节点57:3）
        
        Args:
            workflow: 工作流字典
            steps: 采样步数
            
        Returns:
            是否成功更新
        """
        return self.update_workflow_input(workflow, "57:3", "steps", steps)
    
    def update_cfg(self, workflow: dict, cfg: float) -> bool:
        """
        更新CFG值（节点57:3）
        
        Args:
            workflow: 工作流字典
            cfg: CFG值
            
        Returns:
            是否成功更新
        """
        return self.update_workflow_input(workflow, "57:3", "cfg", cfg)
    
    def update_resolution(self, workflow: dict, width: int, height: int) -> bool:
        """
        更新图像分辨率（节点57:13）
        
        Args:
            workflow: 工作流字典
            width: 图像宽度
            height: 图像高度
            
        Returns:
            是否成功更新
        """
        if "57:13" not in workflow:
            return False
        
        node = workflow["57:13"]
        if "inputs" not in node:
            node["inputs"] = {}
        
        node["inputs"]["width"] = width
        node["inputs"]["height"] = height
        return True
    
    def update_filename_prefix(self, workflow: dict, prefix: str) -> bool:
        """
        更新输出文件名前缀（节点9）
        
        Args:
            workflow: 工作流字典
            prefix: 文件名前缀
            
        Returns:
            是否成功更新
        """
        return self.update_workflow_input(workflow, "9", "filename_prefix", prefix)
    
    def _qwen_edit_workflow_path(self) -> str:
        """act_02_qwen_Image_edit-aigc-3-api.json 的绝对路径"""
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), QWEN_IMAGE_EDIT_3REF_WORKFLOW)
    
    def load_qwen_image_edit_workflow(self) -> dict:
        """
        加载三参考图 Qwen Image Edit 工作流（act_02_qwen_Image_edit-aigc-3-api.json）。
        支持运行时传入 1 张、2 张或 3 张参考图，不足的槽位用第一张图填充。
        """
        path = self._qwen_edit_workflow_path()
        if not os.path.exists(path):
            raise FileNotFoundError(f"工作流文件不存在: {path}")
        return self.load_workflow(path)
    
    def _upload_ref_and_get_name(self, file_path: str) -> str:
        """从本地上传参考图至 ComfyUI，返回 ComfyUI 使用的文件名。"""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"参考图不存在: {file_path}")
        result = self.upload_file(file_path, subfolder="input")
        name = result.get("name", os.path.basename(file_path)) if isinstance(result, dict) else (str(result) if result else os.path.basename(file_path))
        logger.info(f"从本地上传参考图至 ComfyUI: {file_path} -> {name}")
        return name
    
    def update_qwen_edit_ref_images(
        self, workflow: dict, ref_names: List[str]
    ) -> bool:
        """
        更新 Qwen Image Edit 工作流中的三路参考图。
        ref_names: 长度为 3 的列表，依次对应节点 78、120、121。
        """
        if len(ref_names) != 3:
            return False
        ok = True
        ok &= self.update_workflow_input(workflow, QWEN_EDIT_NODE_IMAGE1, "image", ref_names[0])
        ok &= self.update_workflow_input(workflow, QWEN_EDIT_NODE_IMAGE2, "image", ref_names[1])
        ok &= self.update_workflow_input(workflow, QWEN_EDIT_NODE_IMAGE3, "image", ref_names[2])
        return ok
    
    def update_qwen_edit_prompt(self, workflow: dict, prompt: str) -> bool:
        """更新 Qwen Image Edit 正提示词（节点 115:111）。"""
        return self.update_workflow_input(workflow, QWEN_EDIT_NODE_PROMPT_POS, "prompt", prompt)
    
    def update_qwen_edit_filename_prefix(self, workflow: dict, prefix: str) -> bool:
        """更新 Qwen Image Edit 输出文件名前缀（节点 60）。"""
        return self.update_workflow_input(workflow, QWEN_EDIT_NODE_SAVE, "filename_prefix", prefix)
    
    def generate_image_edit(
        self,
        prompt: str,
        reference_images: List[str],
        filename_prefix: str,
        seed: Optional[int] = None,
        steps: Optional[int] = None,
        cfg: Optional[float] = None,
        wait: bool = True,
    ) -> dict:
        """
        使用 act_02_qwen_Image_edit-aigc-3-api.json 工作流，基于 1/2/3 张参考图生成图像。
        
        Args:
            prompt: 编辑提示词（正提示词）
            reference_images: 参考图路径列表，支持 1 张、2 张或 3 张；不足 3 张时用第一张（或第二张）填充
            filename_prefix: 输出文件名前缀
            seed: 随机种子（可选）
            steps: 采样步数（可选）
            cfg: CFG（可选）
            wait: 是否等待执行完成
            
        Returns:
            与 execute_workflow 相同格式的结果字典（含 prompt_id, images, audio）
        """
        if not reference_images or len(reference_images) > 3:
            raise ValueError("reference_images 必须为 1、2 或 3 张参考图路径")
        
        # 上传并得到 3 个槽位对应的文件名（不足则重复）
        uploaded = [self._upload_ref_and_get_name(p) for p in reference_images]
        if len(uploaded) == 1:
            ref_names = [uploaded[0], uploaded[0], uploaded[0]]
        elif len(uploaded) == 2:
            ref_names = [uploaded[0], uploaded[1], uploaded[1]]
        else:
            ref_names = uploaded
        
        workflow = self.load_qwen_image_edit_workflow()
        self.update_qwen_edit_ref_images(workflow, ref_names)
        self.update_qwen_edit_prompt(workflow, prompt)
        self.update_qwen_edit_filename_prefix(workflow, filename_prefix)
        
        if seed is not None:
            self.update_workflow_input(workflow, QWEN_EDIT_NODE_SAMPLER, "seed", seed)
        if steps is not None:
            self.update_workflow_input(workflow, QWEN_EDIT_NODE_SAMPLER, "steps", steps)
        if cfg is not None:
            self.update_workflow_input(workflow, QWEN_EDIT_NODE_SAMPLER, "cfg", cfg)
        
        return self.execute_workflow(workflow, wait=wait)
    
    @staticmethod
    def load_prompt_from_file(file_path: str) -> str:
        """
        从文本文件加载提示词
        
        Args:
            file_path: 提示词文件路径
            
        Returns:
            提示词文本
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"提示词文件不存在: {file_path}")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            prompt = f.read().strip()
        
        if not prompt:
            raise ValueError(f"提示词文件为空: {file_path}")
        
        return prompt
    
    @staticmethod
    def find_prompt_files(directory: str, extensions: list = None) -> list:
        """
        查找目录中的所有提示词文件
        
        Args:
            directory: 目录路径
            extensions: 文件扩展名列表（默认: ['.txt', '.prompt']）
            
        Returns:
            提示词文件路径列表
        """
        if extensions is None:
            extensions = ['.txt', '.prompt']
        
        if not os.path.exists(directory):
            raise FileNotFoundError(f"目录不存在: {directory}")
        
        if not os.path.isdir(directory):
            raise ValueError(f"路径不是目录: {directory}")
        
        prompt_files = []
        for filename in os.listdir(directory):
            file_path = os.path.join(directory, filename)
            if os.path.isfile(file_path):
                _, ext = os.path.splitext(filename)
                if ext.lower() in extensions:
                    prompt_files.append(file_path)
        
        return sorted(prompt_files)
    
    def batch_generate_images(
        self,
        prompt_dir: str,
        style_prefix: str = "Pixel art style,",
        seed: int = None,
        steps: int = None,
        cfg: float = None,
        width: int = None,
        height: int = None,
        output_dir: str = "./output",
        file_extensions: list = None,
        auto_filename_prefix: bool = True
    ) -> list:
        """
        批量生成图像
        
        Args:
            prompt_dir: 提示词文件目录
            style_prefix: 风格前缀
            seed: 随机种子（如果为None，使用工作流中的默认值）
            steps: 采样步数（如果为None，使用工作流中的默认值）
            cfg: CFG值（如果为None，使用工作流中的默认值）
            width: 图像宽度（如果为None，使用工作流中的默认值）
            height: 图像高度（如果为None，使用工作流中的默认值）
            output_dir: 输出目录
            file_extensions: 要处理的文件扩展名列表（默认: ['.txt', '.prompt']）
            auto_filename_prefix: 是否根据提示词文件名自动设置输出文件名前缀
            
        Returns:
            执行结果列表
        """
        # 查找所有提示词文件
        prompt_files = self.find_prompt_files(prompt_dir, file_extensions)
        
        if not prompt_files:
            print(f"警告: 在目录 {prompt_dir} 中未找到提示词文件")
            return []
        
        print(f"找到 {len(prompt_files)} 个提示词文件")
        
        results = []
        total = len(prompt_files)
        
        for idx, prompt_file in enumerate(prompt_files, 1):
            filename = os.path.basename(prompt_file)
            filename_base = os.path.splitext(filename)[0]
            
            print(f"\n[{idx}/{total}] 处理文件: {filename}")
            print("-" * 60)
            
            try:
                # 读取提示词
                prompt = self.load_prompt_from_file(prompt_file)
                print(f"提示词已加载（长度: {len(prompt)} 字符）")
                
                # 自动设置文件名前缀
                filename_prefix = None
                if auto_filename_prefix:
                    filename_prefix = filename_base
                
                # 生成图像
                print("正在生成图像...")
                result = self.generate_image(
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
                
                # 保存图片
                if result['images']:
                    print("保存图片文件...")
                    for node_id, image_info in result['images'].items():
                        image_data = self.get_image(
                            image_info['filename'],
                            image_info.get('subfolder', ''),
                            image_info.get('type', 'output')
                        )
                        output_path = os.path.join(output_dir, image_info['filename'])
                        with open(output_path, 'wb') as f:
                            f.write(image_data)
                        print(f"  保存: {output_path}")
                
                result['prompt_file'] = prompt_file
                result['success'] = True
                results.append(result)
                print(f"✓ 完成: {filename}")
                
            except Exception as e:
                print(f"✗ 错误: 处理文件 {filename} 时出错: {e}")
                import traceback
                traceback.print_exc()
                results.append({
                    'prompt_file': prompt_file,
                    'success': False,
                    'error': str(e)
                })
        
        return results
    
    def generate_image(
        self,
        prompt: str = None,
        style_prefix: str = "Pixel art style,",
        seed: int = None,
        steps: int = None,
        cfg: float = None,
        width: int = None,
        height: int = None,
        filename_prefix: str = None,
        wait: bool = True
    ) -> dict:
        """
        生成图像
        
        Args:
            prompt: 提示文本（如果为None，使用工作流中的默认提示）
            style_prefix: 风格前缀（默认: "Pixel art style,"）
            seed: 随机种子（如果为None，使用工作流中的默认值）
            steps: 采样步数（如果为None，使用工作流中的默认值）
            cfg: CFG值（如果为None，使用工作流中的默认值）
            width: 图像宽度（如果为None，使用工作流中的默认值）
            height: 图像高度（如果为None，使用工作流中的默认值）
            filename_prefix: 文件名前缀（如果为None，使用工作流中的默认值）
            wait: 是否等待执行完成
            
        Returns:
            执行结果字典
        """
        # 加载工作流
        workflow = self.load_default_workflow()
        
        # 更新参数
        if prompt is not None:
            self.update_prompt(workflow, prompt)
        
        if style_prefix is not None:
            self.update_style_prefix(workflow, style_prefix)
        
        if seed is not None:
            self.update_seed(workflow, seed)
        
        if steps is not None:
            self.update_steps(workflow, steps)
        
        if cfg is not None:
            self.update_cfg(workflow, cfg)
        
        if width is not None and height is not None:
            self.update_resolution(workflow, width, height)
        
        if filename_prefix is not None:
            self.update_filename_prefix(workflow, filename_prefix)
        
        # 执行工作流
        return self.execute_workflow(workflow, wait=wait)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='Z-Image Turbo 图像生成客户端')
    parser.add_argument('--workflow', type=str, default='z_image_workflow.json',
                        help='工作流JSON文件路径（默认: z_image_workflow.json）')
    parser.add_argument('--server', type=str, default='127.0.0.1:8188',
                        help='ComfyUI服务器地址（默认: 127.0.0.1:8188）')
    parser.add_argument('--output-dir', type=str, default='./output',
                        help='输出目录（默认: ./output）')
    parser.add_argument('--prompt', type=str, default=None,
                        help='提示文本（如果指定，将替换工作流中的默认提示）')
    parser.add_argument('--prompt-file', type=str, default=None,
                        help='提示词文本文件路径（如果指定，将从文件读取提示词，优先级高于--prompt）')
    parser.add_argument('--prompt-dir', type=str, default=None,
                        help='提示词文件目录（如果指定，将批量处理目录中的所有提示词文件，优先级最高）')
    parser.add_argument('--file-extensions', type=str, nargs='+', default=['.txt', '.prompt'],
                        help='批量处理时要处理的文件扩展名（默认: .txt .prompt）')
    parser.add_argument('--no-auto-filename-prefix', action='store_true',
                        help='批量处理时禁用根据文件名自动设置输出文件名前缀')
    parser.add_argument('--style-prefix', type=str, default='Pixel art style,',
                        help='风格前缀（默认: "Pixel art style,"）')
    parser.add_argument('--seed', type=int, default=None,
                        help='随机种子（可选）')
    parser.add_argument('--steps', type=int, default=None,
                        help='采样步数（可选，默认使用工作流中的值）')
    parser.add_argument('--cfg', type=float, default=None,
                        help='CFG值（可选，默认使用工作流中的值）')
    parser.add_argument('--width', type=int, default=None,
                        help='图像宽度（可选，默认1024）')
    parser.add_argument('--height', type=int, default=None,
                        help='图像高度（可选，默认1024）')
    parser.add_argument('--filename-prefix', type=str, default=None,
                        help='输出文件名前缀（可选，默认: z-image）')
    parser.add_argument('--debug', action='store_true',
                        help='显示调试信息（包括提交的工作流JSON）')
    
    args = parser.parse_args()
    
    # 创建输出目录
    os.makedirs(args.output_dir, exist_ok=True)
    
    # 创建客户端
    client = ZImageClient(server_address=args.server, workflow_path=args.workflow)
    
    try:
        # 连接服务器
        print("正在连接ComfyUI服务器...")
        client.connect()
        
        # 检查工作流文件
        if not os.path.exists(args.workflow):
            print(f"错误: 工作流文件不存在: {args.workflow}")
            print(f"\n当前目录: {os.getcwd()}")
            print(f"当前目录中的JSON文件: {', '.join([f for f in os.listdir('.') if f.endswith('.json')]) if any(f.endswith('.json') for f in os.listdir('.')) else '无JSON文件'}")
            return
        
        # 批量处理模式
        if args.prompt_dir:
            print(f"批量处理模式: 处理目录 {args.prompt_dir} 中的所有提示词文件")
            print("=" * 60)
            
            # 调试模式：显示工作流内容
            if args.debug:
                workflow = client.load_default_workflow()
                print("\n调试信息 - 工作流内容:")
                print(json.dumps(workflow, indent=2, ensure_ascii=False))
                print("\n工作流中的节点:")
                for node_id, node_data in workflow.items():
                    if isinstance(node_data, dict):
                        class_type = node_data.get('class_type', 'Unknown')
                        print(f"  节点 {node_id}: {class_type}")
            
            # 批量生成
            results = client.batch_generate_images(
                prompt_dir=args.prompt_dir,
                style_prefix=args.style_prefix,
                seed=args.seed,
                steps=args.steps,
                cfg=args.cfg,
                width=args.width,
                height=args.height,
                output_dir=args.output_dir,
                file_extensions=args.file_extensions,
                auto_filename_prefix=not args.no_auto_filename_prefix
            )
            
            # 统计结果
            print("\n" + "=" * 60)
            print("批量处理完成!")
            successful = sum(1 for r in results if r.get('success', False))
            failed = len(results) - successful
            print(f"总计: {len(results)} 个文件")
            print(f"成功: {successful} 个")
            print(f"失败: {failed} 个")
            
            if failed > 0:
                print("\n失败的文件:")
                for r in results:
                    if not r.get('success', False):
                        print(f"  - {os.path.basename(r.get('prompt_file', 'Unknown'))}: {r.get('error', 'Unknown error')}")
        
        else:
            # 单文件处理模式
            # 处理提示词输入（文件优先于命令行参数）
            prompt = args.prompt
            if args.prompt_file:
                try:
                    print(f"正在从文件读取提示词: {args.prompt_file}")
                    prompt = ZImageClient.load_prompt_from_file(args.prompt_file)
                    print(f"提示词已加载（长度: {len(prompt)} 字符）")
                except Exception as e:
                    print(f"错误: 无法读取提示词文件: {e}")
                    return
            elif args.prompt:
                print(f"使用命令行提示词（长度: {len(args.prompt)} 字符）")
            
            # 调试模式：显示工作流内容
            if args.debug:
                workflow = client.load_default_workflow()
                print("\n调试信息 - 工作流内容:")
                print(json.dumps(workflow, indent=2, ensure_ascii=False))
                print("\n工作流中的节点:")
                for node_id, node_data in workflow.items():
                    if isinstance(node_data, dict):
                        class_type = node_data.get('class_type', 'Unknown')
                        print(f"  节点 {node_id}: {class_type}")
            
            # 生成图像
            print("正在生成图像...")
            result = client.generate_image(
                prompt=prompt,
                style_prefix=args.style_prefix,
                seed=args.seed,
                steps=args.steps,
                cfg=args.cfg,
                width=args.width,
                height=args.height,
                filename_prefix=args.filename_prefix,
                wait=True
            )
            
            print(f"\n执行完成!")
            print(f"Prompt ID: {result['prompt_id']}")
            
            # 保存图片输出
            if result['images']:
                print("\n保存图片文件...")
                for node_id, image_info in result['images'].items():
                    image_data = client.get_image(
                        image_info['filename'],
                        image_info.get('subfolder', ''),
                        image_info.get('type', 'output')
                    )
                    output_path = os.path.join(args.output_dir, image_info['filename'])
                    with open(output_path, 'wb') as f:
                        f.write(image_data)
                    print(f"  保存: {output_path}")
            else:
                print("\n警告: 未生成图片文件")
                print("提示: 请检查工作流是否正确执行，或查看ComfyUI服务器的日志")
    
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        client.disconnect()


if __name__ == "__main__":
    main()

