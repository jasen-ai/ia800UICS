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
Nano Banana 图生图客户端 - 用于调用Nano Banana绘画API
支持图生图、流式响应、webhook回调等功能
"""
import json
import os
import sys
import time
import urllib.request
import urllib.parse
import urllib.error
import base64
import mimetypes
import ssl
from typing import Dict, Any, Optional, Iterator
import argparse


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
        os.path.join(os.path.dirname(__file__), "nanobanana_config.json"),
        os.path.join(os.path.expanduser("~"), ".nanobanana_config.json"),
        "nanobanana_config.json"
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
                    print(f"已加载配置文件: {path}")
                    return config
            except Exception as e:
                print(f"警告: 无法读取配置文件 {path}: {e}")
                continue
    
    # 如果所有配置文件都不存在，返回空字典
    return {}


def get_api_key(api_key: Optional[str] = None, config_path: Optional[str] = None) -> str:
    """
    获取API密钥（优先使用参数，其次从配置文件读取）
    
    Args:
        api_key: 直接提供的API密钥（可选）
        config_path: 配置文件路径（可选）
        
    Returns:
        API密钥
        
    Raises:
        ValueError: 如果无法获取API密钥
    """
    # 如果直接提供了API密钥，优先使用
    if api_key:
        return api_key
    
    # 尝试从配置文件读取
    config = load_config(config_path)
    
    # 尝试多个可能的键名
    possible_keys = ['api_key', 'apikey', 'apiKey', 'API_KEY', 'APIKEY']
    for key in possible_keys:
        if key in config:
            return config[key]
    
    # 如果都找不到，抛出错误
    raise ValueError(
        "未找到API密钥。请使用以下方式之一提供API密钥：\n"
        "1. 使用 --api-key 参数\n"
        "2. 在配置文件中设置 api_key 字段\n"
        f"   配置文件路径: {os.path.join(os.path.dirname(__file__), 'nanobanana_config.json')}\n"
        "   配置文件格式: {\"api_key\": \"YOUR_API_KEY\", \"host\": \"https://api.example.com\"}"
    )


def image_file_to_base64(image_path: str) -> str:
    """
    将本地图片文件转换为Base64格式
    
    Args:
        image_path: 图片文件路径
        
    Returns:
        Base64编码的图片字符串
        
    Raises:
        FileNotFoundError: 如果文件不存在
        ValueError: 如果文件不是有效的图片格式
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"文件不存在: {image_path}")
    
    # 检查文件类型
    mime_type, _ = mimetypes.guess_type(image_path)
    if not mime_type:
        ext = os.path.splitext(image_path)[1].lower()
        image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
        if ext not in image_extensions:
            raise ValueError(f"文件不是有效的图片格式: {image_path}")
        mime_type = 'image/jpeg' if ext in ['.jpg', '.jpeg'] else 'image/png'
    elif not mime_type.startswith('image/'):
        ext = os.path.splitext(image_path)[1].lower()
        image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
        if ext not in image_extensions:
            raise ValueError(f"文件不是有效的图片格式: {image_path}")
    
    # 读取文件并转换为Base64
    with open(image_path, 'rb') as f:
        file_data = f.read()
        base64_data = base64.b64encode(file_data).decode('utf-8')
    
    return base64_data


class NanoBananaClient:
    """Nano Banana 图生图客户端类"""
    
    # 支持的模型列表
    SUPPORTED_MODELS = [
        "nano-banana-fast",
        "nano-banana",
        "nano-banana-pro",
        "nano-banana-pro-vt",
        "nano-banana-pro-cl",
        "nano-banana-pro-vip",
        "nano-banana-pro-4k-vip"
    ]
    
    # 支持的宽高比
    SUPPORTED_ASPECT_RATIOS = [
        "auto",
        "1:1",
        "16:9",
        "9:16",
        "4:3",
        "3:4",
        "3:2",
        "2:3",
        "5:4",
        "4:5",
        "21:9"
    ]
    
    # 支持的图像大小
    SUPPORTED_IMAGE_SIZES = ["1K", "2K", "4K"]
    
    def __init__(
        self,
        api_key: str,
        host: Optional[str] = None,
        config_path: Optional[str] = None
    ):
        """
        初始化Nano Banana客户端
        
        Args:
            api_key: API密钥
            host: API服务器地址（可选，如果为None则从配置文件读取）
            config_path: 配置文件路径（可选）
        """
        self.api_key = api_key
        
        # 获取host
        if host:
            self.host = host.rstrip('/')
        else:
            config = load_config(config_path)
            self.host = config.get('host', 'https://grsai.dakka.com.cn').rstrip('/')
        
        self.base_url = f"{self.host}/v1/draw/nano-banana"
    
    def _get_headers(self) -> Dict[str, str]:
        """获取请求头"""
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
    
    def _prepare_urls(self, reference_images: Optional[list] = None) -> list:
        """
        准备参考图URL列表
        
        Args:
            reference_images: 参考图列表，可以是：
                - URL字符串列表：["https://example.com/image.png"]
                - 本地文件路径列表：["/path/to/image.png"]
                - Base64字符串列表：["base64_string"]
                - 混合列表
        
        Returns:
            处理后的URL列表（URL或Base64字符串）
        """
        if not reference_images:
            return []
        
        urls = []
        for ref in reference_images:
            if isinstance(ref, str):
                # 1) 远程 URL 直接使用
                if ref.startswith(('http://', 'https://')):
                    urls.append(ref)
                # 2) 本地文件路径：始终读取并转成 Base64（图生图推荐 Base64 上传）
                elif os.path.exists(ref):
                    base64_data = image_file_to_base64(ref)
                    urls.append(base64_data)
                else:
                    # 3) 其余情况：保留原始字符串（假定已是 Base64 或由调用方保证正确）
                    urls.append(ref)
            else:
                raise ValueError(f"不支持的参考图格式: {type(ref)}")
        
        return urls
    
    def generate_image(
        self,
        prompt: str,
        model: str = "nano-banana-fast",
        reference_images: Optional[list] = None,
        aspect_ratio: str = "auto",
        image_size: str = "1K",
        webhook: Optional[str] = None,
        shut_progress: bool = False,
        stream: bool = True
    ) -> Dict[str, Any]:
        """
        生成图像
        
        Args:
            prompt: 提示词（必填）
            model: 模型名称（默认: "nano-banana-fast"）
            reference_images: 参考图列表（可选），可以是URL或本地文件路径或Base64
            aspect_ratio: 输出图像比例（默认: "auto"）
            image_size: 输出图像大小（默认: "1K"）
            webhook: 回调链接（可选）。如果为"-1"，则立即返回id用于轮询
            shut_progress: 关闭进度回复，直接回复最终结果（默认: False）
            stream: 是否使用流式响应（默认: True）。如果为False且webhook为None，则webhook设为"-1"
        
        Returns:
            生成结果字典，包含：
            - 如果使用流式响应：包含完整的响应数据
            - 如果使用webhook="-1"：包含id用于后续轮询
            - 如果使用webhook URL：包含id
        
        Raises:
            ValueError: 如果参数无效
            urllib.error.HTTPError: 如果API请求失败
        """
        # 验证模型
        if model not in self.SUPPORTED_MODELS:
            raise ValueError(
                f"不支持的模型: {model}。支持的模型: {', '.join(self.SUPPORTED_MODELS)}"
            )
        
        # 验证宽高比
        if aspect_ratio not in self.SUPPORTED_ASPECT_RATIOS:
            raise ValueError(
                f"不支持的宽高比: {aspect_ratio}。支持的宽高比: {', '.join(self.SUPPORTED_ASPECT_RATIOS)}"
            )
        
        # 验证图像大小
        if image_size not in self.SUPPORTED_IMAGE_SIZES:
            raise ValueError(
                f"不支持的图像大小: {image_size}。支持的图像大小: {', '.join(self.SUPPORTED_IMAGE_SIZES)}"
            )
        
        # 准备参考图URL
        urls = self._prepare_urls(reference_images)
        
        # 构建请求数据
        data = {
            "model": model,
            "prompt": prompt,
            "aspectRatio": aspect_ratio,
            "imageSize": image_size,
        }
        
        # 添加参考图（如果有）
        if urls:
            data["urls"] = urls
        
        # 处理webhook和stream选项
        if not stream and webhook is None:
            # 如果不使用流式响应且没有webhook，设置为"-1"以立即返回id
            data["webHook"] = "-1"
        elif webhook is not None:
            data["webHook"] = webhook
        
        # 添加shutProgress
        if shut_progress:
            data["shutProgress"] = True
        
        # 发送请求
        headers = self._get_headers()
        json_data = json.dumps(data, ensure_ascii=False).encode('utf-8')
        
        req = urllib.request.Request(
            self.base_url,
            data=json_data,
            headers=headers,
            method='POST'
        )
        
        try:
            with urllib.request.urlopen(req, context=ssl._create_unverified_context()) as response:
                # 如果使用webhook="-1"，返回id
                if not stream and webhook is None:
                    response_data = response.read().decode('utf-8')
                    result = json.loads(response_data)
                    if result.get('code') == 0:
                        return {
                            'id': result['data']['id'],
                            'code': result['code'],
                            'msg': result['msg']
                        }
                    else:
                        raise ValueError(f"API返回错误: {result.get('msg', 'Unknown error')}")
                
                # 流式响应：逐行读取SSE格式的数据
                if stream:
                    return self._read_stream_response(response)
                else:
                    # 非流式响应（webhook URL）
                    response_data = response.read().decode('utf-8')
                    result = json.loads(response_data)
                    if result.get('code') == 0:
                        return {
                            'id': result['data']['id'],
                            'code': result['code'],
                            'msg': result['msg']
                        }
                    else:
                        raise ValueError(f"API返回错误: {result.get('msg', 'Unknown error')}")
        
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8') if e.fp else ''
            raise urllib.error.HTTPError(
                e.url, e.code, f"{e.reason}: {error_body}", e.headers, e.fp
            )
    
    def _read_stream_response(self, response) -> Dict[str, Any]:
        """
        读取流式响应数据（SSE格式）
        
        Args:
            response: urllib响应对象
        
        Returns:
            解析后的结果字典（包含最终状态）
        """
        result = {
            'id': None,
            'results': [],
            'progress': 0,
            'status': 'running',
            'failure_reason': '',
            'error': ''
        }
        
        # 逐行读取SSE格式的数据
        buffer = ''
        for line_bytes in response:
            try:
                line = line_bytes.decode('utf-8')
                buffer += line
                
                # SSE格式：每行以 'data: ' 开头，后面是JSON数据
                if line.startswith('data: '):
                    try:
                        data_str = line[6:].strip()  # 移除 'data: ' 前缀
                        if data_str:
                            data = json.loads(data_str)
                            
                            # 更新结果
                            if 'id' in data:
                                result['id'] = data['id']
                            if 'results' in data:
                                result['results'] = data['results']
                            if 'progress' in data:
                                result['progress'] = data['progress']
                            if 'status' in data:
                                result['status'] = data['status']
                            if 'failure_reason' in data:
                                result['failure_reason'] = data['failure_reason']
                            if 'error' in data:
                                result['error'] = data['error']
                            
                            # 如果状态是成功或失败，可以提前返回
                            if data.get('status') in ['succeeded', 'failed']:
                                break
                    
                    except json.JSONDecodeError:
                        # 忽略无法解析的行
                        continue
                
                # 如果遇到空行，可能是SSE消息分隔符
                elif line.strip() == '':
                    continue
                
            except UnicodeDecodeError:
                # 忽略解码错误
                continue
        
        # 如果缓冲区中还有数据，尝试解析（处理一次性返回的情况）
        if result['status'] == 'running' and buffer:
            try:
                # 尝试作为普通JSON解析
                data = json.loads(buffer.strip())
                if 'id' in data:
                    result['id'] = data.get('id')
                if 'results' in data:
                    result['results'] = data.get('results', [])
                if 'progress' in data:
                    result['progress'] = data.get('progress', 0)
                if 'status' in data:
                    result['status'] = data.get('status', 'running')
                if 'failure_reason' in data:
                    result['failure_reason'] = data.get('failure_reason', '')
                if 'error' in data:
                    result['error'] = data.get('error', '')
            except json.JSONDecodeError:
                # 如果无法解析，使用之前解析的结果
                pass
        
        return result
    
    def get_result(self, task_id: str) -> Dict[str, Any]:
        """
        查询任务结果（如果使用webhook="-1"或webhook URL，可以使用此方法轮询结果）
        
        Args:
            task_id: 任务ID
        
        Returns:
            任务结果字典
        
        Note:
            此方法需要API提供查询接口。如果API不支持，请使用webhook回调。
        """
        # 注意：根据API文档，如果使用webhook，结果会通过回调返回
        # 如果API提供了查询接口，可以在这里实现
        # 目前API文档中没有提到查询接口，所以这个方法可能需要根据实际API实现
        raise NotImplementedError(
            "API文档中未提供查询接口。如果使用webhook='-1'，请使用webhook回调获取结果。"
        )


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='Nano Banana 图生图客户端',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 使用提示词生成图片（流式响应）
  python nanobanana_client.py --prompt "一只可爱的猫咪在草地上玩耍"
  
  # 使用参考图生成图片
  python nanobanana_client.py --prompt "一只可爱的猫咪" --reference-image input/example.png
  
  # 使用指定模型和参数
  python nanobanana_client.py --prompt "一只可爱的猫咪" --model nano-banana-pro --image-size 2K --aspect-ratio 16:9
  
  # 使用webhook回调（返回id）
  python nanobanana_client.py --prompt "一只可爱的猫咪" --no-stream --webhook "-1"
  
  # 使用自定义webhook URL
  python nanobanana_client.py --prompt "一只可爱的猫咪" --webhook "https://example.com/callback"
        """
    )
    
    # API配置参数
    parser.add_argument('--api-key', type=str, default=None,
                        help='API密钥（可选，也可以从配置文件读取）')
    parser.add_argument('--host', type=str, default=None,
                        help='API服务器地址（可选，默认从配置文件读取）')
    parser.add_argument('--config', type=str, default=None,
                        help='配置文件路径（可选）')
    
    # 生成参数
    parser.add_argument('--prompt', type=str, required=True,
                        help='提示词（必填）')
    parser.add_argument('--model', type=str, default='nano-banana-fast',
                        choices=NanoBananaClient.SUPPORTED_MODELS,
                        help='模型名称（默认: nano-banana-fast）')
    parser.add_argument('--reference-image', type=str, nargs='+', default=None,
                        help='参考图路径或URL（可以指定多个）')
    parser.add_argument('--aspect-ratio', type=str, default='auto',
                        choices=NanoBananaClient.SUPPORTED_ASPECT_RATIOS,
                        help='输出图像比例（默认: auto）')
    parser.add_argument('--image-size', type=str, default='1K',
                        choices=NanoBananaClient.SUPPORTED_IMAGE_SIZES,
                        help='输出图像大小（默认: 1K）')
    
    # 响应方式参数
    parser.add_argument('--webhook', type=str, default=None,
                        help='回调链接（可选）。如果为"-1"，则立即返回id用于轮询')
    parser.add_argument('--no-stream', action='store_true',
                        help='不使用流式响应（如果未指定webhook，则自动设置为"-1"）')
    parser.add_argument('--shut-progress', action='store_true',
                        help='关闭进度回复，直接回复最终结果（建议搭配webhook使用）')
    
    # 输出参数
    parser.add_argument('--output-dir', type=str, default='./output',
                        help='输出目录（默认: ./output）')
    parser.add_argument('--save-image', action='store_true',
                        help='保存生成的图片到本地')
    
    args = parser.parse_args()
    
    # 获取API密钥
    try:
        api_key = get_api_key(args.api_key, args.config)
    except ValueError as e:
        print(f"错误: {e}")
        return
    
    # 创建客户端
    client = NanoBananaClient(
        api_key=api_key,
        host=args.host,
        config_path=args.config
    )
    
    try:
        print(f"正在生成图像...")
        print(f"提示词: {args.prompt}")
        print(f"模型: {args.model}")
        if args.reference_image:
            print(f"参考图: {', '.join(args.reference_image)}")
        print(f"宽高比: {args.aspect_ratio}")
        print(f"图像大小: {args.image_size}")
        print("-" * 60)
        
        # 生成图像
        result = client.generate_image(
            prompt=args.prompt,
            model=args.model,
            reference_images=args.reference_image,
            aspect_ratio=args.aspect_ratio,
            image_size=args.image_size,
            webhook=args.webhook,
            shut_progress=args.shut_progress,
            stream=not args.no_stream
        )
        
        # 显示结果
        print("\n生成结果:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        # 如果使用webhook="-1"，只返回id
        if 'id' in result and len(result) == 3:
            print(f"\n任务ID: {result['id']}")
            print("提示: 使用webhook回调获取结果，或使用API提供的查询接口")
            return
        
        # 处理流式响应结果
        if result.get('status') == 'succeeded' and result.get('results'):
            print(f"\n✓ 生成成功!")
            print(f"进度: {result.get('progress', 0)}%")
            
            # 保存图片
            if args.save_image:
                os.makedirs(args.output_dir, exist_ok=True)
                
                for idx, res in enumerate(result.get('results', [])):
                    image_url = res.get('url')
                    if image_url:
                        # 下载图片
                        try:
                            print(f"\n正在下载图片 {idx + 1}...")
                            with urllib.request.urlopen(image_url) as img_response:
                                image_data = img_response.read()
                                
                                # 生成文件名
                                timestamp = int(time.time())
                                filename = f"nanobanana_{timestamp}_{idx + 1}.png"
                                output_path = os.path.join(args.output_dir, filename)
                                
                                # 保存文件
                                with open(output_path, 'wb') as f:
                                    f.write(image_data)
                                
                                print(f"✓ 图片已保存: {output_path}")
                                
                                # 显示内容描述（如果有）
                                content = res.get('content')
                                if content:
                                    print(f"  内容描述: {content}")
                        
                        except Exception as e:
                            print(f"✗ 下载图片失败: {e}")
        
        elif result.get('status') == 'failed':
            print(f"\n✗ 生成失败!")
            print(f"失败原因: {result.get('failure_reason', 'Unknown')}")
            if result.get('error'):
                print(f"错误详情: {result.get('error')}")
        
        elif result.get('status') == 'running':
            print(f"\n⏳ 生成中...")
            print(f"进度: {result.get('progress', 0)}%")
            print("提示: 如果使用流式响应，请等待完成。如果使用webhook，结果将通过回调返回。")
    
    except ValueError as e:
        print(f"错误: {e}")
        return
    except urllib.error.HTTPError as e:
        print(f"HTTP错误: {e.code} - {e.reason}")
        if e.fp:
            error_body = e.read().decode('utf-8')
            print(f"错误详情: {error_body}")
        return
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
        return


if __name__ == "__main__":
    main()

