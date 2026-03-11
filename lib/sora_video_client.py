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
Sora2视频生成客户端 - 用于调用Sora2视频生成API
支持视频生成、角色上传、角色创建等功能
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
from typing import Dict, Any, Optional, Callable, Iterator
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
        os.path.join(os.path.dirname(__file__), "sora_video_config.json"),
        os.path.join(os.path.expanduser("~"), ".sora_video_config.json"),
        "sora_video_config.json"
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


def load_providers_config(providers_path: Optional[str] = None) -> Dict[str, Any]:
    """
    加载供应商配置文件
    
    Args:
        providers_path: 供应商配置文件路径（可选）
        
    Returns:
        供应商配置字典
    """
    # 默认供应商配置文件路径
    default_paths = [
        os.path.join(os.path.dirname(__file__), "sora_video_providers.json"),
        os.path.join(os.path.expanduser("~"), ".sora_video_providers.json"),
        "sora_video_providers.json"
    ]
    
    if providers_path:
        paths = [providers_path] + default_paths
    else:
        paths = default_paths
    
    for path in paths:
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    providers_config = json.load(f)
                    print(f"已加载供应商配置: {path}")
                    return providers_config
            except Exception as e:
                print(f"警告: 无法读取供应商配置文件 {path}: {e}")
                continue
    
    # 返回默认配置
    return {
        "providers": {
            "default": {
                "name": "默认供应商",
                "host": "https://grsai.dakka.com.cn",
                "type": "standard",
                "endpoints": {
                    "generate": "/v1/video/sora-video",
                    "upload_character": "/v1/video/sora-upload-character",
                    "create_character": "/v1/video/sora-create-character",
                    "get_result": "/v1/draw/result"
                },
                "request_format": "json",
                "auth_header": "Bearer",
                "success_code": 0
            }
        },
        "default_provider": "default"
    }


def image_file_to_base64(image_path: str, use_data_uri: bool = False) -> str:
    """
    将本地图片或视频文件转换为Base64格式
    
    Args:
        image_path: 图片或视频文件路径
        use_data_uri: 是否使用data URI格式（data:image/xxx;base64,xxxxx）。
                      如果为False，只返回纯Base64字符串
        
    Returns:
        Base64编码的文件字符串。
        如果use_data_uri=True: "data:image/xxx;base64,xxxxx" 格式
        如果use_data_uri=False: 纯Base64字符串
        
    Raises:
        FileNotFoundError: 如果文件不存在
        ValueError: 如果文件不是有效的图片或视频格式
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"文件不存在: {image_path}")
    
    # 检查文件类型
    mime_type, _ = mimetypes.guess_type(image_path)
    if not mime_type:
        # 尝试根据扩展名判断
        ext = os.path.splitext(image_path)[1].lower()
        image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg']
        video_extensions = ['.mp4', '.avi', '.mov', '.webm', '.mkv', '.flv']
        
        if ext in image_extensions:
            mime_type = 'image/jpeg' if ext in ['.jpg', '.jpeg'] else 'image/png'
        elif ext in video_extensions:
            mime_type = 'video/mp4' if ext == '.mp4' else 'video/webm'
        else:
            raise ValueError(f"文件不是有效的图片或视频格式: {image_path}")
    elif not (mime_type.startswith('image/') or mime_type.startswith('video/')):
        # 如果MIME类型不是图片或视频，检查扩展名
        ext = os.path.splitext(image_path)[1].lower()
        image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg']
        video_extensions = ['.mp4', '.avi', '.mov', '.webm', '.mkv', '.flv']
        if ext not in image_extensions and ext not in video_extensions:
            raise ValueError(f"文件不是有效的图片或视频格式: {image_path}")
    
    # 读取文件并转换为Base64
    with open(image_path, 'rb') as f:
        file_data = f.read()
        base64_data = base64.b64encode(file_data).decode('utf-8')
    
    # 根据参数决定返回格式
    if use_data_uri:
        return f"data:{mime_type};base64,{base64_data}"
    else:
        # 返回纯Base64字符串（某些API可能只接受这种格式）
        return base64_data


def get_image_info(image_path: str) -> Dict[str, Any]:
    """
    获取图片文件的详细信息
    
    Args:
        image_path: 图片文件路径
        
    Returns:
        包含图片信息的字典
    """
    info = {
        "path": image_path,
        "exists": os.path.exists(image_path),
        "size_bytes": 0,
        "size_mb": 0.0,
        "mime_type": None,
        "extension": None
    }
    
    if not info["exists"]:
        return info
    
    # 文件大小
    info["size_bytes"] = os.path.getsize(image_path)
    info["size_mb"] = info["size_bytes"] / (1024 * 1024)
    
    # 扩展名
    info["extension"] = os.path.splitext(image_path)[1].lower()
    
    # MIME类型
    mime_type, _ = mimetypes.guess_type(image_path)
    info["mime_type"] = mime_type
    
    # 尝试读取图片尺寸（如果可能）
    try:
        from PIL import Image
        with Image.open(image_path) as img:
            info["width"] = img.width
            info["height"] = img.height
            info["format"] = img.format
            info["mode"] = img.mode
    except ImportError:
        # PIL不可用，跳过
        pass
    except Exception:
        # 无法读取图片信息，跳过
        pass
    
    return info


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
        f"   配置文件路径: {os.path.join(os.path.dirname(__file__), 'sora_video_config.json')}\n"
        "   配置文件格式: {\"api_key\": \"YOUR_API_KEY\"}"
    )


class SoraVideoClient:
    """Sora2视频生成客户端类"""
    
    def __init__(
        self,
        api_key: str,
        host: Optional[str] = None,
        provider: Optional[str] = None,
        providers_config: Optional[Dict[str, Any]] = None
    ):
        """
        初始化Sora2视频客户端
        
        Args:
            api_key: API密钥
            host: API服务器地址（可选，如果提供provider则忽略）
            provider: 供应商名称（可选，从providers_config中读取配置）
            providers_config: 供应商配置字典（可选）
        """
        self.api_key = api_key
        
        # 加载供应商配置
        if providers_config is None:
            providers_config = load_providers_config()
        
        self.providers_config = providers_config
        providers = providers_config.get("providers", {})
        
        # 确定使用的供应商
        if provider:
            if provider not in providers:
                raise ValueError(f"供应商 '{provider}' 不存在。可用供应商: {', '.join(providers.keys())}")
            self.provider_name = provider
        else:
            self.provider_name = providers_config.get("default_provider", "default")
            if self.provider_name not in providers:
                self.provider_name = "default"
        
        self.provider_config = providers.get(self.provider_name, {})
        
        # 设置host和base_url
        if host:
            self.host = host.rstrip('/')
        else:
            self.host = self.provider_config.get("host", "https://grsai.dakka.com.cn").rstrip('/')
        
        # 根据供应商类型设置base_url
        if self.provider_config.get("type") == "wuyinkeji":
            self.base_url = self.host
        else:
            self.base_url = f"{self.host}/v1/video"
        
        self.provider_type = self.provider_config.get("type", "standard")
    
    def _get_headers(self) -> Dict[str, str]:
        """获取请求头"""
        headers = {}
        
        # 根据供应商类型设置Content-Type
        request_format = self.provider_config.get("request_format", "json")
        if request_format == "form":
            headers["Content-Type"] = "application/x-www-form-urlencoded;charset=utf-8"
        else:
            headers["Content-Type"] = "application/json"
        
        # 根据供应商类型设置Authorization
        auth_header = self.provider_config.get("auth_header", "Bearer")
        if auth_header == "Authorization":
            # 无音科技格式：直接使用API密钥
            headers["Authorization"] = self.api_key
        else:
            # 标准格式：Bearer token
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        return headers
    
    def _clean_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        清理请求数据，移除空值和None值
        
        Args:
            data: 原始请求数据
            
        Returns:
            清理后的请求数据
        """
        cleaned = {}
        for key, value in data.items():
            # 跳过None值
            if value is None:
                continue
            # 跳过空字符串（某些字段可能需要保留空字符串，但大多数不需要）
            if isinstance(value, str) and value == "":
                # 对于某些字段，空字符串可能是有意义的，保留它们
                # 但对于remixTargetId等，空字符串应该被移除
                if key in ["remixTargetId", "remix_target_id"]:
                    continue
            cleaned[key] = value
        return cleaned
    
    def _make_request(
        self,
        endpoint: str,
        data: Dict[str, Any],
        stream: bool = False,
        debug: bool = False
    ) -> Any:
        """
        发送HTTP请求
        
        Args:
            endpoint: API端点
            data: 请求数据
            stream: 是否使用流式响应
            debug: 是否显示调试信息
            
        Returns:
            响应数据或流式响应迭代器
        """
        # 清理数据，移除空值
        cleaned_data = self._clean_data(data)
        
        # 构建URL
        if endpoint.startswith('/'):
            url = f"{self.host}{endpoint}"
        else:
            url = f"{self.base_url}/{endpoint}"
        
        # 根据供应商类型处理请求数据
        request_format = self.provider_config.get("request_format", "json")
        headers = self._get_headers()
        
        if request_format == "form":
            # Form格式（无音科技）
            # key参数需要放在URL中
            key_param = self.provider_config.get("key_param", "key")
            if "?" in url:
                url = f"{url}&{key_param}={urllib.parse.quote(self.api_key)}"
            else:
                url = f"{url}?{key_param}={urllib.parse.quote(self.api_key)}"
            
            # 将数据转换为form格式
            form_data = urllib.parse.urlencode(cleaned_data).encode('utf-8')
            req = urllib.request.Request(
                url,
                data=form_data,
                headers=headers,
                method='POST'
            )
            
            # 调试模式：显示请求信息
            if debug:
                debug_data = cleaned_data.copy()
                if "url" in debug_data and isinstance(debug_data["url"], str) and len(debug_data["url"]) > 100:
                    debug_data["url"] = f"[Base64数据，长度: {len(debug_data['url'])} 字符]"
                print("\n" + "=" * 60)
                print("调试信息 - 发送的请求:")
                print("=" * 60)
                print(f"URL: {url}")
                print(f"请求方法: POST")
                print(f"Content-Type: {headers.get('Content-Type')}")
                print(f"Authorization: {headers.get('Authorization', 'N/A')[:50]}...")
                print(f"请求数据 (Form): {urllib.parse.urlencode(debug_data)}")
                print("=" * 60 + "\n")
        else:
            # JSON格式（标准）
            req = urllib.request.Request(
                url,
                data=json.dumps(cleaned_data).encode('utf-8'),
                headers=headers,
                method='POST'
            )
            
        
        try:
            # 设置超时
            try:
                response = urllib.request.urlopen(req, timeout=30)
            except urllib.error.URLError as url_error:
                # 网络错误，提供更详细的错误信息
                error_reason = str(url_error.reason) if hasattr(url_error, 'reason') else str(url_error)
                if debug:
                    print(f"\n调试信息 - 网络错误:")
                    print(f"  URL: {url}")
                    print(f"  错误: {error_reason}")
                raise RuntimeError(f"网络请求失败: {error_reason}")
            
            if stream:
                # 流式响应
                return self._parse_stream_response(response)
            else:
                # 普通响应
                response_body = response.read().decode('utf-8')
                
                # 检查响应是否为空
                if not response_body or not response_body.strip():
                    raise RuntimeError(
                        f"API返回空响应。状态码: {response.getcode()}, "
                        f"URL: {url}"
                    )
                
                # 尝试解析JSON
                try:
                    result = json.loads(response_body)
                    return result
                except json.JSONDecodeError as e:
                    # JSON解析失败，打印原始响应以便调试
                    error_msg = (
                        f"API返回非JSON响应。状态码: {response.getcode()}, "
                        f"URL: {url}\n"
                        f"响应内容（前500字符）: {response_body[:500]}\n"
                        f"JSON解析错误: {e}"
                    )
                    if debug:
                        print("\n" + "=" * 60)
                        print("调试信息 - API响应:")
                        print("=" * 60)
                        print(f"状态码: {response.getcode()}")
                        print(f"URL: {url}")
                        print(f"响应内容: {response_body}")
                        print("=" * 60 + "\n")
                    raise RuntimeError(error_msg)
                
        except urllib.error.HTTPError as e:
            # HTTP错误（如404, 500等）
            try:
                error_body = e.read().decode('utf-8')
            except:
                error_body = f"无法读取错误响应体（状态码: {e.code}）"
            
            error_msg = f"API请求失败 (HTTP {e.code}): {e.reason}"
            if error_body:
                try:
                    error_json = json.loads(error_body)
                    error_msg = error_json.get('msg', error_json.get('error', error_body))
                except:
                    # 如果不是JSON，使用原始错误体
                    if len(error_body) > 500:
                        error_msg = f"{error_msg}\n响应内容（前500字符）: {error_body[:500]}"
                    else:
                        error_msg = f"{error_msg}\n响应内容: {error_body}"
            
            if debug:
                print("\n" + "=" * 60)
                print("调试信息 - HTTP错误:")
                print("=" * 60)
                print(f"状态码: {e.code}")
                print(f"原因: {e.reason}")
                print(f"URL: {url}")
                print(f"错误响应: {error_body}")
                print("=" * 60 + "\n")
            
            raise RuntimeError(error_msg)
        except urllib.error.URLError as e:
            # URL错误（如网络连接问题）
            error_msg = f"网络请求失败: {e.reason}"
            if debug:
                print("\n" + "=" * 60)
                print("调试信息 - 网络错误:")
                print("=" * 60)
                print(f"URL: {url}")
                print(f"请求方法: POST")
                print(f"请求头: {headers}")
                if request_format == "form":
                    form_debug = cleaned_data.copy()
                    if "url" in form_debug and isinstance(form_debug["url"], str) and len(form_debug["url"]) > 100:
                        form_debug["url"] = f"[Base64数据，长度: {len(form_debug['url'])} 字符]"
                    print(f"请求数据 (Form): {urllib.parse.urlencode(form_debug)}")
                else:
                    debug_data = cleaned_data.copy()
                    if "url" in debug_data and isinstance(debug_data["url"], str) and len(debug_data["url"]) > 100:
                        debug_data["url"] = f"[Base64数据，长度: {len(debug_data['url'])} 字符]"
                    print(f"请求数据 (JSON): {json.dumps(debug_data, indent=2, ensure_ascii=False)}")
                print(f"错误详情: {e}")
                print("=" * 60 + "\n")
            raise RuntimeError(error_msg)
    
    def _parse_stream_response(self, response, timeout: float = 300.0) -> Iterator[Dict[str, Any]]:
        """
        解析流式响应
        
        Args:
            response: HTTP响应对象
            timeout: 超时时间（秒，默认300秒）
            
        Yields:
            解析后的JSON对象
        """
        import socket
        import select
        
        buffer = ""
        last_data_time = time.time()
        no_data_timeout = 120.0  # 如果120秒没有新数据，认为连接可能已断开（增加超时时间）
        
        # 尝试设置socket超时（如果可能）
        # 注意：设置较长的超时时间，避免频繁超时
        try:
            if hasattr(response, 'fp') and hasattr(response.fp, 'raw'):
                sock = response.fp.raw
                if hasattr(sock, 'sock'):
                    sock.sock.settimeout(60.0)  # 设置socket读取超时为60秒（从30秒增加到60秒）
        except:
            pass
        
        try:
            while True:
                # 检查总超时
                if time.time() - last_data_time > timeout:
                    print(f"\n⚠️  警告: 流式响应超时（{timeout}秒无响应）")
                    break
                
                # 检查无数据超时
                if time.time() - last_data_time > no_data_timeout:
                    print(f"\n⚠️  警告: 超过{no_data_timeout}秒未收到新数据，可能连接已断开")
                    print("提示: 任务可能仍在服务器端处理中，建议使用轮询模式（--webhook=-1 --poll）")
                    break
                
                try:
                    # 尝试读取数据（可能是一行或多行）
                    # 使用readline()或直接读取chunk
                    if hasattr(response, 'readline'):
                        line = response.readline()
                    else:
                        # 如果没有readline，尝试读取chunk
                        chunk = response.read(1024)
                        if not chunk:
                            time.sleep(0.5)
                            continue
                        line = chunk
                    
                    if not line:
                        # 如果没有数据，等待一小段时间
                        time.sleep(0.5)
                        continue
                    
                    last_data_time = time.time()
                    
                    # 解码数据
                    if isinstance(line, bytes):
                        line = line.decode('utf-8', errors='ignore')
                    buffer += line
                    
                    # 尝试解析完整的JSON对象
                    if buffer.strip():
                        try:
                            # 查找完整的JSON对象（以{开始，以}结束）
                            start = buffer.find('{')
                            if start != -1:
                                brace_count = 0
                                end = -1
                                for i in range(start, len(buffer)):
                                    if buffer[i] == '{':
                                        brace_count += 1
                                    elif buffer[i] == '}':
                                        brace_count -= 1
                                        if brace_count == 0:
                                            end = i + 1
                                            break
                                
                                if end != -1:
                                    json_str = buffer[start:end]
                                    buffer = buffer[end:]
                                    try:
                                        parsed = json.loads(json_str)
                                        yield parsed
                                        
                                        # 如果收到完成状态，可以提前退出
                                        if parsed.get("status") in ["succeeded", "failed"]:
                                            return
                                    except json.JSONDecodeError:
                                        continue
                        except Exception as e:
                            # 如果解析出错，继续尝试
                            continue
                except socket.timeout:
                    # Socket超时，但继续等待（可能是服务器处理较慢）
                    # 只有在长时间无数据时才真正中断
                    elapsed = time.time() - last_data_time
                    if elapsed > no_data_timeout:
                        print(f"\n⚠️  警告: Socket读取超时，且超过{no_data_timeout}秒未收到新数据")
                        print("提示: 任务可能仍在服务器端处理中，建议使用轮询模式（--webhook=-1 --poll）")
                        break
                    # 否则继续等待（socket超时是正常的，服务器可能处理较慢）
                    continue
                except Exception as e:
                    # 其他异常，可能是连接断开
                    print(f"\n⚠️  警告: 读取流式响应时出错: {e}")
                    break
        finally:
            try:
                response.close()
            except:
                pass
    
    def generate_video(
        self,
        prompt: str,
        model: str = "sora-2",
        url: Optional[str] = None,
        image_file: Optional[str] = None,
        aspect_ratio: str = "9:16",
        duration: int = 10,
        remix_target_id: Optional[str] = None,
        size: str = "small",
        webhook: Optional[str] = None,
        shut_progress: bool = False,
        stream: bool = False,
        callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        debug: bool = False
    ) -> Dict[str, Any]:
        """
        生成Sora2视频
        
        Args:
            prompt: 提示词（必填）
            model: 模型名称（默认: "sora-2"）
            url: 参考图URL或Base64（选填）
            image_file: 本地图片文件路径（选填）。如果提供，将自动转换为Base64格式
            aspect_ratio: 输出视频比例，支持 "9:16" 或 "16:9"（默认: "9:16"）
            duration: 视频时长（秒），支持 10 或 15（默认: 10）
            remix_target_id: 视频续作目标ID（选填）
            size: 视频清晰度，"small" 或 "large"（默认: "small"）
            webhook: 回调链接（选填）。如果设为 "-1"，会立即返回id用于轮询
            shut_progress: 关闭进度回复，直接回复最终结果（默认: False）
            stream: 是否使用流式响应（默认: False）
            callback: 流式响应回调函数（可选）
            
        Returns:
            响应结果字典。如果使用webhook="-1"，返回包含id的字典；如果使用流式响应，返回最终结果
            
        Note:
            url 和 image_file 参数不能同时使用。如果同时提供，image_file 优先级更高。
        """
        # 根据供应商类型构建请求数据
        if self.provider_type == "wuyinkeji":
            # 无音科技格式
            data = {
                "prompt": prompt,
                "aspectRatio": aspect_ratio,
                "duration": str(duration),  # 无音科技需要字符串格式
                "size": size
            }
            
            # 无音科技不支持model参数
            if remix_target_id:
                data["remixTargetId"] = remix_target_id
        else:
            # 标准格式
            data = {
                "model": model,
                "prompt": prompt,
                "aspectRatio": aspect_ratio,
                "duration": duration,
                "size": size,
                "shutProgress": shut_progress
            }
            
            if remix_target_id:
                data["remixTargetId"] = remix_target_id
            
            if webhook:
                data["webHook"] = webhook
        
        # 处理参考图：优先使用 image_file，其次使用 url
        if image_file:
            # 将本地图片文件转换为Base64
            try:
                print(f"正在读取图片文件: {image_file}")
                
                # 检查文件大小
                if os.path.exists(image_file):
                    file_size = os.path.getsize(image_file) / (1024 * 1024)  # MB
                    if file_size > 20:
                        print(f"⚠️  警告: 图片文件较大 ({file_size:.2f} MB)，可能影响处理速度")
                    elif file_size > 10:
                        print(f"提示: 图片文件大小 {file_size:.2f} MB")
                
                # 尝试使用纯Base64格式（不包含data URI前缀）
                # 某些API可能只接受纯Base64字符串
                base64_image = image_file_to_base64(image_file, use_data_uri=False)
                
                # 检查Base64数据大小
                base64_size = len(base64_image) / (1024 * 1024)  # MB
                if base64_size > 15:
                    print(f"⚠️  警告: Base64数据较大 ({base64_size:.2f} MB)，可能导致请求失败")
                
                data["url"] = base64_image
                print("✓ 图片已转换为Base64格式（纯Base64字符串）")
            except Exception as e:
                raise ValueError(f"无法处理图片文件 {image_file}: {e}")
        elif url:
            data["url"] = url
        
        # 根据供应商类型处理响应
        if self.provider_type == "wuyinkeji":
            # 无音科技不支持stream和webhook，只返回任务ID
            endpoint = self.provider_config.get("endpoints", {}).get("generate", "/api/sora2/submit")
            try:
                result = self._make_request(endpoint, data, stream=False, debug=debug)
            except RuntimeError as e:
                # 如果是网络异常，提供更详细的错误信息
                error_msg = str(e)
                if "网络异常" in error_msg or "网络请求失败" in error_msg or "URLError" in error_msg:
                    print("\n" + "=" * 60)
                    print("网络错误排查:")
                    print("=" * 60)
                    print(f"1. 检查网络连接是否正常")
                    print(f"2. 检查API服务器地址: {self.host}")
                    print(f"3. 检查API密钥是否正确（已配置）")
                    print(f"4. 检查供应商配置:")
                    print(f"   供应商: {self.provider_name}")
                    print(f"   Host: {self.host}")
                    print(f"   Endpoint: {endpoint}")
                    print(f"5. 尝试使用 --debug 参数查看详细请求信息")
                    print("=" * 60 + "\n")
                raise
            
            # 转换响应格式为标准格式
            success_code = self.provider_config.get("success_code", 200)
            if result.get("code") == success_code:
                task_id = result.get("data", {}).get("id")
                if task_id:
                    # 返回标准格式
                    return {
                        "code": 0,
                        "msg": result.get("msg", "success"),
                        "data": {
                            "id": task_id
                        }
                    }
            else:
                # API返回了错误
                error_msg = result.get("msg", "Unknown error")
                error_code = result.get("code", "Unknown")
                raise RuntimeError(f"API请求失败 (code={error_code}): {error_msg}")
            return result
        elif stream or (webhook and webhook != "-1"):
            # 流式响应或webhook回调（标准供应商）
            endpoint = self.provider_config.get("endpoints", {}).get("generate", "/v1/video/sora-video")
            if stream:
                results = []
                try:
                    for response in self._make_request(endpoint, data, stream=True, debug=debug):
                        if callback:
                            callback(response)
                        results.append(response)
                        
                        # 检查是否完成
                        if response.get("status") in ["succeeded", "failed"]:
                            return response
                    
                    # 如果没有收到完成状态，返回最后一个响应
                    if results:
                        last_result = results[-1]
                        print(f"\n⚠️  警告: 流式响应中断，返回最后收到的状态")
                        print(f"   最后状态: {last_result.get('status', 'unknown')}")
                        print(f"   最后进度: {last_result.get('progress', 0)}%")
                        if last_result.get('id'):
                            print(f"   任务ID: {last_result.get('id')}")
                            print(f"   提示: 可以使用 --webhook=-1 --poll 模式，或使用 get-result 命令查询结果")
                        return last_result
                    else:
                        print("\n⚠️  警告: 未收到任何响应数据")
                        return {}
                except Exception as e:
                    print(f"\n❌ 错误: 流式响应处理失败: {e}")
                    if results:
                        return results[-1]
                    raise
            else:
                # webhook模式，返回初始响应（包含id）
                return self._make_request(endpoint, data, stream=False, debug=debug)
        else:
            # 普通请求（标准供应商）
            endpoint = self.provider_config.get("endpoints", {}).get("generate", "/v1/video/sora-video")
            return self._make_request(endpoint, data, stream=False, debug=debug)
    
    def upload_character(
        self,
        url: Optional[str] = None,
        video_file: Optional[str] = None,
        timestamps: Optional[str] = None,
        webhook: Optional[str] = None,
        shut_progress: bool = False,
        stream: bool = False,
        callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        debug: bool = False
    ) -> Dict[str, Any]:
        """
        上传角色视频
        
        Args:
            url: 角色视频URL或Base64（选填）
            video_file: 本地视频文件路径（选填）。如果提供，将自动转换为Base64格式
            timestamps: 角色视频范围，格式为 "开始秒数,结束秒数"，例如 "0,3"（选填，最多3秒）
            webhook: 回调链接（选填）。如果设为 "-1"，会立即返回id用于轮询
            shut_progress: 关闭进度回复，直接回复最终结果（默认: False）
            stream: 是否使用流式响应（默认: False）
            callback: 流式响应回调函数（可选）
            
        Returns:
            响应结果字典
            
        Note:
            url 和 video_file 参数不能同时使用。如果同时提供，video_file 优先级更高。
        """
        data = {
            "shutProgress": shut_progress
        }
        
        # 处理视频文件：优先使用 video_file，其次使用 url
        if video_file:
            # 检查文件类型
            ext = os.path.splitext(video_file)[1].lower()
            video_extensions = ['.mp4', '.avi', '.mov', '.webm', '.mkv', '.flv']
            image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
            
            if ext in image_extensions:
                print(f"⚠️  警告: 上传角色接口需要视频文件，但检测到图片文件: {video_file}")
                print("   提示: 上传角色应该使用视频文件（.mp4, .avi, .mov等）")
                print("   继续处理，但可能无法正常工作...")
            
            # 将本地视频文件转换为Base64
            try:
                print(f"正在读取文件: {video_file}")
                # 使用纯Base64格式
                base64_video = image_file_to_base64(video_file, use_data_uri=False)
                data["url"] = base64_video
                print("文件已转换为Base64格式（纯Base64字符串）")
            except Exception as e:
                raise ValueError(f"无法处理文件 {video_file}: {e}")
        elif url:
            data["url"] = url
        
        if timestamps:
            data["timestamps"] = timestamps
        
        if webhook:
            data["webHook"] = webhook
        
        # 根据API文档：
        # 1. 如果使用stream，使用流式响应
        # 2. 如果webhook="-1"，立即返回id用于轮询
        # 3. 如果设置了其他webhook，使用webhook回调
        # 4. 默认使用流式响应
        
        endpoint = self.provider_config.get("endpoints", {}).get("upload_character", "/v1/video/sora-upload-character")
        
        if stream:
            # 流式响应模式
            results = []
            try:
                for response in self._make_request(endpoint, data, stream=True, debug=debug):
                    if callback:
                        callback(response)
                    results.append(response)
                    
                    # 检查是否完成
                    if response.get("status") in ["succeeded", "failed"]:
                        return response
                
                # 如果没有收到完成状态，返回最后一个响应
                if results:
                    last_result = results[-1]
                    print(f"\n⚠️  警告: 流式响应中断，返回最后收到的状态")
                    print(f"   最后状态: {last_result.get('status', 'unknown')}")
                    print(f"   最后进度: {last_result.get('progress', 0)}%")
                    if last_result.get('id'):
                        task_id = last_result.get('id')
                        print(f"   任务ID: {task_id}")
                        print(f"   提示: 可以使用以下方式查询结果：")
                        print(f"   1. 轮询模式: python sora_video_client.py upload-character --video-file \"character.mp4\" --timestamps \"0,3\" --webhook=-1 --poll")
                        print(f"   2. 查询结果: python sora_video_client.py get-result --task-id {task_id}")
                    return last_result
                else:
                    print("\n⚠️  警告: 未收到任何响应数据")
                    return {}
            except Exception as e:
                print(f"\n❌ 错误: 流式响应处理失败: {e}")
                if results:
                    return results[-1]
                raise
        elif webhook == "-1":
            # webhook="-1"模式：立即返回id用于轮询
            result = self._make_request(endpoint, data, stream=False, debug=debug)
            # 返回格式应该是: {"code": 0, "msg": "success", "data": {"id": "id"}}
            return result
        elif webhook:
            # webhook回调模式：返回初始响应（包含id）
            return self._make_request(endpoint, data, stream=False, debug=debug)
        else:
            # 默认：使用流式响应（根据API文档，默认是流式响应）
            results = []
            try:
                for response in self._make_request(endpoint, data, stream=True, debug=debug):
                    if callback:
                        callback(response)
                    results.append(response)
                    
                    # 检查是否完成
                    if response.get("status") in ["succeeded", "failed"]:
                        return response
                
                # 如果没有收到完成状态，返回最后一个响应
                if results:
                    return results[-1]
                else:
                    print("\n⚠️  警告: 未收到任何响应数据")
                    return {}
            except Exception as e:
                print(f"\n❌ 错误: 流式响应处理失败: {e}")
                if results:
                    return results[-1]
                raise
    
    def create_character_from_video(
        self,
        pid: str,
        timestamps: Optional[str] = None,
        webhook: Optional[str] = None,
        shut_progress: bool = False,
        stream: bool = False,
        callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        debug: bool = False
    ) -> Dict[str, Any]:
        """
        从原视频创建角色
        
        Args:
            pid: 原视频ID（必填），格式为 "s_xxxxxxxxxxxxxxx"
            timestamps: 角色视频范围，格式为 "开始秒数,结束秒数"，例如 "0,3"（选填，最多3秒）
            webhook: 回调链接（选填）。如果设为 "-1"，会立即返回id用于轮询
            shut_progress: 关闭进度回复，直接回复最终结果（默认: False）
            stream: 是否使用流式响应（默认: False）
            callback: 流式响应回调函数（可选）
            
        Returns:
            响应结果字典
        """
        data = {
            "pid": pid,
            "shutProgress": shut_progress
        }
        
        if timestamps:
            data["timestamps"] = timestamps
        
        if webhook:
            data["webHook"] = webhook
        
        if stream or (webhook and webhook != "-1"):
            # 流式响应或webhook回调
            if stream:
                results = []
                for response in self._make_request("sora-create-character", data, stream=True, debug=debug):
                    if callback:
                        callback(response)
                    results.append(response)
                    
                    # 检查是否完成
                    if response.get("status") in ["succeeded", "failed"]:
                        return response
                
                # 如果没有收到完成状态，返回最后一个响应
                return results[-1] if results else {}
            else:
                # webhook模式，返回初始响应（包含id）
                return self._make_request("sora-create-character", data, stream=False, debug=debug)
        else:
            # 普通请求
            return self._make_request("sora-create-character", data, stream=False, debug=debug)
    
    def get_result(self, task_id: str, debug: bool = False) -> Dict[str, Any]:
        """
        获取任务结果
        
        Args:
            task_id: 任务ID
            debug: 是否显示调试信息
            
        Returns:
            任务结果字典
        """
        # 根据供应商类型选择不同的查询接口
        if self.provider_type == "wuyinkeji":
            # 无音科技：尝试使用可能的查询接口
            # 注意：如果速创API有查询接口，需要在配置文件中添加endpoint
            endpoint = self.provider_config.get("endpoints", {}).get("get_result")
            
            # 如果没有配置查询接口，尝试使用submit接口查询（传递task_id）
            if not endpoint:
                # 尝试使用submit接口查询结果
                submit_endpoint = self.provider_config.get("endpoints", {}).get("generate", "/api/sora2/submit")
                if submit_endpoint.startswith('/'):
                    url = f"{self.host}{submit_endpoint}"
                else:
                    url = f"{self.base_url}/{submit_endpoint}"
                
                key_param = self.provider_config.get("key_param", "key")
                if "?" in url:
                    url = f"{url}&{key_param}={urllib.parse.quote(self.api_key)}"
                else:
                    url = f"{url}?{key_param}={urllib.parse.quote(self.api_key)}"
                
                # 尝试使用task_id作为参数查询
                # 可能的参数名：id, task_id, taskId
                possible_params = ["id", "task_id", "taskId"]
                
                for param_name in possible_params:
                    try:
                        # 使用Form格式发送POST请求
                        form_data = {param_name: task_id}
                        form_data_encoded = urllib.parse.urlencode(form_data).encode('utf-8')
                        
                        req = urllib.request.Request(
                            url,
                            data=form_data_encoded,
                            headers=self._get_headers(),
                            method='POST'
                        )
                        
                        if debug:
                            print(f"尝试使用参数 {param_name}={task_id} 查询结果")
                        
                        response = urllib.request.urlopen(req, timeout=30)
                        result = json.loads(response.read().decode('utf-8'))
                        
                        # 检查响应格式
                        success_code = self.provider_config.get("success_code", 200)
                        if result.get("code") == success_code:
                            # 查询成功
                            if debug:
                                print(f"✓ 使用参数 {param_name} 查询成功")
                            return result.get("data", result)
                        else:
                            # 接口返回错误，但可能是正确的接口（只是参数名不对）
                            # 继续尝试下一个参数名
                            continue
                            
                    except urllib.error.HTTPError as e:
                        # HTTP错误，继续尝试下一个参数名
                        if e.code == 400:
                            # 400可能是参数错误，继续尝试
                            continue
                        # 其他HTTP错误，可能是接口不存在
                        break
                    except Exception as e:
                        # 其他错误，继续尝试
                        if debug:
                            print(f"尝试参数 {param_name} 时出错: {e}")
                        continue
            
            if endpoint:
                # 如果有配置查询接口，使用配置的接口
                if endpoint.startswith('/'):
                    url = f"{self.host}{endpoint}"
                else:
                    url = f"{self.base_url}/{endpoint}"
                
                # 无音科技可能使用Form格式或URL参数
                request_format = self.provider_config.get("request_format", "form")
                if request_format == "form":
                    # Form格式：将task_id作为URL参数
                    key_param = self.provider_config.get("key_param", "key")
                    if "?" in url:
                        url = f"{url}&id={urllib.parse.quote(task_id)}&{key_param}={urllib.parse.quote(self.api_key)}"
                    else:
                        url = f"{url}?id={urllib.parse.quote(task_id)}&{key_param}={urllib.parse.quote(self.api_key)}"
                    
                    req = urllib.request.Request(
                        url,
                        headers=self._get_headers(),
                        method='GET'  # 查询接口可能使用GET
                    )
                else:
                    # JSON格式
                    data = {"id": task_id}
                    req = urllib.request.Request(
                        url,
                        data=json.dumps(data).encode('utf-8'),
                        headers=self._get_headers(),
                        method='POST'
                    )
            else:
                # 如果没有配置查询接口，尝试常见的查询接口路径
                # 常见的查询接口路径
                common_endpoints = [
                    "/api/sora2/result",
                    "/api/sora2/query",
                    "/api/sora2/status",
                    "/api/sora2/get"
                ]
                
                last_error = None
                for endpoint in common_endpoints:
                    try:
                        url = f"{self.host}{endpoint}"
                        key_param = self.provider_config.get("key_param", "key")
                        if "?" in url:
                            url = f"{url}&id={urllib.parse.quote(task_id)}&{key_param}={urllib.parse.quote(self.api_key)}"
                        else:
                            url = f"{url}?id={urllib.parse.quote(task_id)}&{key_param}={urllib.parse.quote(self.api_key)}"
                        
                        req = urllib.request.Request(
                            url,
                            headers=self._get_headers(),
                            method='GET'
                        )
                        
                        if debug:
                            print(f"尝试查询接口: {url}")
                        
                        response = urllib.request.urlopen(req, timeout=10)
                        result = json.loads(response.read().decode('utf-8'))
                        
                        # 检查响应格式
                        success_code = self.provider_config.get("success_code", 200)
                        if result.get("code") == success_code:
                            # 找到可用的接口，返回结果
                            if debug:
                                print(f"✓ 找到可用的查询接口: {endpoint}")
                            return result.get("data", result)
                        else:
                            # 接口存在但返回错误，继续尝试下一个
                            last_error = result.get("msg", "Unknown error")
                            continue
                            
                    except urllib.error.HTTPError as e:
                        # 404或其他HTTP错误，继续尝试下一个
                        if e.code == 404:
                            continue
                        last_error = f"HTTP {e.code}: {e.reason}"
                        continue
                    except Exception as e:
                        # 其他错误，继续尝试
                        last_error = str(e)
                        continue
                
                # 所有常见接口都尝试失败，提示用户配置
                raise RuntimeError(
                    f"无音科技供应商未配置查询接口，且无法找到默认查询接口。\n\n"
                    f"请按以下步骤操作：\n"
                    f"1. 联系速创API供应商获取查询接口详情\n"
                    f"2. 在供应商配置文件中添加查询接口配置：\n"
                    f"   编辑文件: sora_video_providers.json\n"
                    f"   在 wuyinkeji 的 endpoints 中添加：\n"
                    f"   \"get_result\": \"/api/sora2/result\"  // 替换为实际的查询接口路径\n\n"
                    f"配置示例：\n"
                    f"{{\n"
                    f"  \"providers\": {{\n"
                    f"    \"wuyinkeji\": {{\n"
                    f"      ...\n"
                    f"      \"endpoints\": {{\n"
                    f"        \"generate\": \"/api/sora2/submit\",\n"
                    f"        \"get_result\": \"/api/sora2/result\"  // 添加这一行\n"
                    f"      }}\n"
                    f"    }}\n"
                    f"  }}\n"
                    f"}}\n\n"
                    f"任务ID: {task_id}\n"
                    f"最后尝试的错误: {last_error if last_error else '所有常见接口路径都不可用'}"
                )
        else:
            # 标准供应商：使用 /v1/draw/result
            endpoint = self.provider_config.get("endpoints", {}).get("get_result", "/v1/draw/result")
            if endpoint.startswith('/'):
                url = f"{self.host}{endpoint}"
            else:
                url = f"{self.base_url}/{endpoint}"
            
            data = {"id": task_id}
            req = urllib.request.Request(
                url,
                data=json.dumps(data).encode('utf-8'),
                headers=self._get_headers(),
                method='POST'
            )
        
        if debug:
            print(f"\n调试信息 - 查询任务结果:")
            print(f"URL: {url}")
            print(f"任务ID: {task_id}")
        
        try:
            response = urllib.request.urlopen(req, timeout=30)
            result = json.loads(response.read().decode('utf-8'))
            
            # 根据供应商类型处理响应
            success_code = self.provider_config.get("success_code", 0)
            if result.get("code") == success_code:
                # 返回data字段或整个result
                return result.get("data", result)
            else:
                error_msg = result.get("msg", "Unknown error")
                raise RuntimeError(f"获取结果失败: {error_msg}")
                
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8')
            try:
                error_json = json.loads(error_body)
                error_msg = error_json.get('msg', error_body)
                raise RuntimeError(f"API请求失败: {error_msg}")
            except:
                raise RuntimeError(f"API请求失败: {error_body}")
        except urllib.error.URLError as e:
            raise RuntimeError(f"网络请求失败: {e.reason}")
    
    def poll_result(
        self,
        task_id: str,
        interval: float = 2.0,
        timeout: float = 300.0,
        callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> Dict[str, Any]:
        """
        轮询任务结果直到完成
        
        Args:
            task_id: 任务ID
            interval: 轮询间隔（秒，默认: 2.0）
            timeout: 超时时间（秒，默认: 300.0）
            callback: 每次轮询时的回调函数（可选）
            
        Returns:
            最终任务结果字典
        """
        start_time = time.time()
        
        while True:
            if time.time() - start_time > timeout:
                raise TimeoutError(f"轮询超时: {timeout}秒")
            
            result = self.get_result(task_id, debug=False)
            
            if callback:
                callback(result)
            
            status = result.get("status", "")
            if status == "succeeded":
                return result
            elif status == "failed":
                raise RuntimeError(
                    f"任务失败: {result.get('failure_reason', 'Unknown')} - {result.get('error', '')}"
                )
            elif status == "running":
                # 显示进度
                progress = result.get("progress", 0)
                print(f"任务进行中... 进度: {progress}%")
            
            time.sleep(interval)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='Sora2视频生成客户端')
    parser.add_argument('--api-key', type=str, default=None,
                        help='API密钥（可选，如果未提供，将从配置文件读取）')
    parser.add_argument('--config', type=str, default=None,
                        help='配置文件路径（可选，默认: sora_video_config.json）')
    parser.add_argument('--host', type=str, default=None,
                        help='API服务器地址（可选，默认从配置文件读取或使用 https://grsai.dakka.com.cn）')
    parser.add_argument('--provider', type=str, default=None,
                        help='供应商名称（可选，从sora_video_providers.json读取配置）')
    parser.add_argument('--providers-config', type=str, default=None,
                        help='供应商配置文件路径（可选，默认: sora_video_providers.json）')
    
    # 子命令
    subparsers = parser.add_subparsers(dest='command', help='可用命令')
    
    # 生成视频命令
    gen_parser = subparsers.add_parser('generate', help='生成视频')
    gen_parser.add_argument('--prompt', type=str, required=True,
                            help='提示词（必填）')
    gen_parser.add_argument('--model', type=str, default='sora-2',
                            help='模型名称（默认: sora-2）')
    gen_parser.add_argument('--url', type=str, default=None,
                            help='参考图URL或Base64（选填）')
    gen_parser.add_argument('--image-file', type=str, default=None,
                            help='本地图片文件路径（选填）。如果提供，将自动转换为Base64格式')
    gen_parser.add_argument('--aspect-ratio', type=str, default='9:16',
                            choices=['9:16', '16:9'],
                            help='输出视频比例（默认: 9:16）')
    gen_parser.add_argument('--duration', type=int, default=10,
                            choices=[10, 15],
                            help='视频时长（秒，默认: 10）')
    gen_parser.add_argument('--remix-target-id', type=str, default=None,
                            help='视频续作目标ID（选填）')
    gen_parser.add_argument('--size', type=str, default='small',
                            choices=['small', 'large'],
                            help='视频清晰度（默认: small）')
    gen_parser.add_argument('--webhook', type=str, default=None,
                            help='回调链接（选填）。设为 "-1" 可立即返回id用于轮询')
    gen_parser.add_argument('--shut-progress', action='store_true',
                            help='关闭进度回复，直接回复最终结果')
    gen_parser.add_argument('--stream', action='store_true',
                            help='使用流式响应')
    gen_parser.add_argument('--poll', action='store_true',
                            help='使用轮询方式获取结果（需要webhook="-1"）')
    gen_parser.add_argument('--poll-interval', type=float, default=2.0,
                            help='轮询间隔（秒，默认: 2.0）')
    gen_parser.add_argument('--poll-timeout', type=float, default=300.0,
                            help='轮询超时时间（秒，默认: 300.0）')
    gen_parser.add_argument('--output-dir', type=str, default='./output',
                            help='输出目录（默认: ./output）')
    gen_parser.add_argument('--debug', action='store_true',
                            help='显示调试信息（包括发送的请求数据）')
    
    # 上传角色命令
    upload_parser = subparsers.add_parser('upload-character', help='上传角色视频')
    upload_parser.add_argument('--url', type=str, default=None,
                               help='角色视频URL或Base64（选填）')
    upload_parser.add_argument('--video-file', type=str, default=None,
                               help='本地视频文件路径（选填）。如果提供，将自动转换为Base64格式')
    upload_parser.add_argument('--timestamps', type=str, default=None,
                               help='角色视频范围，格式为 "开始秒数,结束秒数"，例如 "0,3"（选填）')
    upload_parser.add_argument('--webhook', type=str, default=None,
                                help='回调链接（选填）。设为 "-1" 可立即返回id用于轮询')
    upload_parser.add_argument('--shut-progress', action='store_true',
                                help='关闭进度回复，直接回复最终结果')
    upload_parser.add_argument('--stream', action='store_true',
                                help='使用流式响应')
    upload_parser.add_argument('--poll', action='store_true',
                                help='使用轮询方式获取结果（需要webhook="-1"）')
    upload_parser.add_argument('--poll-interval', type=float, default=2.0,
                                help='轮询间隔（秒，默认: 2.0）')
    upload_parser.add_argument('--poll-timeout', type=float, default=300.0,
                                help='轮询超时时间（秒，默认: 300.0）')
    upload_parser.add_argument('--debug', action='store_true',
                                help='显示调试信息（包括发送的请求数据）')
    
    # 从视频创建角色命令
    create_parser = subparsers.add_parser('create-character', help='从原视频创建角色')
    create_parser.add_argument('--pid', type=str, required=True,
                               help='原视频ID（必填），格式为 "s_xxxxxxxxxxxxxxx"')
    create_parser.add_argument('--timestamps', type=str, default=None,
                               help='角色视频范围，格式为 "开始秒数,结束秒数"，例如 "0,3"（选填）')
    create_parser.add_argument('--webhook', type=str, default=None,
                                help='回调链接（选填）。设为 "-1" 可立即返回id用于轮询')
    create_parser.add_argument('--shut-progress', action='store_true',
                                help='关闭进度回复，直接回复最终结果')
    create_parser.add_argument('--stream', action='store_true',
                                help='使用流式响应')
    create_parser.add_argument('--poll', action='store_true',
                                help='使用轮询方式获取结果（需要webhook="-1"）')
    create_parser.add_argument('--poll-interval', type=float, default=2.0,
                                help='轮询间隔（秒，默认: 2.0）')
    create_parser.add_argument('--poll-timeout', type=float, default=300.0,
                                help='轮询超时时间（秒，默认: 300.0）')
    create_parser.add_argument('--debug', action='store_true',
                                help='显示调试信息（包括发送的请求数据）')
    
    # 获取结果命令
    result_parser = subparsers.add_parser('get-result', help='获取任务结果')
    result_parser.add_argument('--task-id', type=str, required=True,
                              help='任务ID（必填）')
    result_parser.add_argument('--debug', action='store_true',
                              help='显示调试信息')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # 加载供应商配置
    providers_config = load_providers_config(args.providers_config)
    
    # 确定使用的供应商
    provider = args.provider
    if not provider:
        # 尝试从配置文件中读取
        config = load_config(args.config)
        provider = config.get('provider')
    
    # 获取API密钥（优先使用参数，其次从供应商配置读取，最后从配置文件读取）
    api_key = args.api_key
    if not api_key:
        # 如果指定了供应商，尝试从供应商配置中读取
        if provider:
            provider_config = providers_config.get("providers", {}).get(provider, {})
            api_key = provider_config.get("api_key")
        
        # 如果还是没有，从配置文件读取
        if not api_key:
            try:
                api_key = get_api_key(None, args.config)
            except ValueError as e:
                print(f"错误: {e}")
                if provider:
                    print(f"提示: 请在供应商配置文件中设置 {provider} 的 api_key，或在命令行使用 --api-key 参数")
                return
    
    # 获取host（优先使用参数，其次从供应商配置读取）
    host = args.host
    if not host and provider:
        provider_config = providers_config.get("providers", {}).get(provider, {})
        host = provider_config.get("host")
    
    if not host:
        config = load_config(args.config)
        host = config.get('host')
    
    # 创建客户端
    client = SoraVideoClient(
        api_key=api_key,
        host=host,
        provider=provider,
        providers_config=providers_config
    )
    
    # 显示使用的供应商信息
    if provider:
        provider_info = providers_config.get("providers", {}).get(provider, {})
        print(f"使用供应商: {provider_info.get('name', provider)} ({provider})")
    else:
        provider_info = providers_config.get("providers", {}).get("default", {})
        print(f"使用供应商: {provider_info.get('name', '默认供应商')} (default)")
    
    try:
        if args.command == 'generate':
            # 流式响应回调
            def progress_callback(response):
                progress = response.get("progress", 0)
                status = response.get("status", "")
                
                # 显示进度，失败时显示错误信息
                if status == "failed":
                    failure_reason = response.get("failure_reason", "")
                    error_msg = response.get("error", "")
                    print(f"❌ 进度: {progress}% - 状态: {status}")
                    if failure_reason:
                        print(f"   失败原因: {failure_reason}")
                    if error_msg:
                        print(f"   错误信息: {error_msg}")
                elif status == "succeeded":
                    print(f"✅ 进度: {progress}% - 状态: {status}")
                else:
                    print(f"进度: {progress}% - 状态: {status}")
                
                if response.get("results"):
                    for result in response["results"]:
                        if "url" in result:
                            print(f"视频URL: {result['url']}")
            
            # 生成视频
            if args.poll and args.webhook != "-1":
                print("错误: 使用轮询模式需要设置 --webhook=-1")
                return
            
            if args.poll:
                # 使用轮询模式
                args.webhook = "-1"
            
            result = client.generate_video(
                prompt=args.prompt,
                model=args.model,
                url=args.url,
                image_file=args.image_file,
                aspect_ratio=args.aspect_ratio,
                duration=args.duration,
                remix_target_id=args.remix_target_id,
                size=args.size,
                webhook=args.webhook,
                shut_progress=args.shut_progress,
                stream=args.stream,
                callback=progress_callback if args.stream else None,
                debug=args.debug
            )
            
            # 处理结果
            if args.poll and args.webhook == "-1":
                # 从初始响应中获取id
                if isinstance(result, dict):
                    # 检查是否是webHook响应格式
                    if "code" in result and "data" in result:
                        if result.get("code") == 0:
                            task_id = result["data"].get("id")
                            if task_id:
                                print(f"任务ID: {task_id}")
                                print("开始轮询结果...")
                                
                                # 轮询结果
                                def poll_callback(response):
                                    progress = response.get("progress", 0)
                                    status = response.get("status", "")
                                    print(f"进度: {progress}% - 状态: {status}")
                                
                                try:
                                    final_result = client.poll_result(
                                        task_id,
                                        interval=args.poll_interval,
                                        timeout=args.poll_timeout,
                                        callback=poll_callback
                                    )
                                    result = final_result
                                except TimeoutError as e:
                                    print(f"\n❌ 错误: {e}")
                                    print(f"任务ID: {task_id}")
                                    print("提示: 可以使用 get-result 命令手动查询结果")
                                    return
                                except Exception as e:
                                    print(f"\n❌ 错误: 轮询失败: {e}")
                                    print(f"任务ID: {task_id}")
                                    print("提示: 可以使用 get-result 命令手动查询结果")
                                    return
                            else:
                                print("错误: 未获取到任务ID")
                                print(f"响应: {result}")
                                return
                        else:
                            print(f"错误: API返回错误代码 {result.get('code')}: {result.get('msg', 'Unknown error')}")
                            return
                    elif "id" in result:
                        # 直接是流式响应格式，已经有id
                        task_id = result.get("id")
                        if task_id:
                            print(f"任务ID: {task_id}")
                            print("提示: 可以使用 get-result 命令查询结果")
            
            # 显示结果
            print("\n" + "=" * 60)
            
            # 检查任务状态（对于无音科技，可能返回的是任务ID格式）
            if client.provider_type == "wuyinkeji":
                # 无音科技返回的是任务ID
                if isinstance(result, dict) and "data" in result and "id" in result["data"]:
                    task_id = result["data"]["id"]
                    print("✅ 任务已提交")
                    print("=" * 60)
                    print(f"任务ID: {task_id}")
                    print("\n提示:")
                    print("  - 无音科技供应商不支持流式响应和轮询")
                    print("  - 可以使用以下命令查询任务结果:")
                    print(f"    python sora_video_client.py --provider wuyinkeji get-result --task-id {task_id}")
                    print("  - 或联系供应商获取查询接口详情")
                    return
                else:
                    print("生成结果:")
                    print(json.dumps(result, indent=2, ensure_ascii=False))
                    return
            
            # 检查任务状态（标准供应商）
            status = result.get("status", "")
            if status == "failed":
                print("❌ 任务失败")
                print("=" * 60)
                
                failure_reason = result.get("failure_reason", "")
                error_msg = result.get("error", "")
                task_id = result.get("id", "")
                
                print(f"任务ID: {task_id}")
                print(f"失败原因: {failure_reason}")
                print(f"错误信息: {error_msg}")
                
                # 提供详细的错误分析和建议
                print("\n" + "-" * 60)
                print("可能的原因和解决方案:")
                print("-" * 60)
                
                if failure_reason == "input_moderation":
                    print("⚠️  输入内容违规")
                    print("   解决方案:")
                    print("   - 检查提示词是否包含违规内容")
                    print("   - 检查参考图片是否符合规范")
                    print("   - 尝试修改提示词或更换参考图")
                elif failure_reason == "output_moderation":
                    print("⚠️  输出内容违规")
                    print("   解决方案:")
                    print("   - 生成的视频内容可能不符合规范")
                    print("   - 尝试修改提示词或参考图")
                elif failure_reason == "error" or error_msg:
                    print("⚠️  系统错误")
                    print("   可能的原因:")
                    print("   1. 图片文件问题（格式、尺寸、内容）")
                    if args.image_file:
                        try:
                            img_info = get_image_info(args.image_file)
                            print(f"      图片文件信息:")
                            print(f"        - 文件大小: {img_info['size_mb']:.2f} MB ({img_info['size_bytes']} 字节)")
                            print(f"        - 文件格式: {img_info.get('mime_type', '未知')}")
                            print(f"        - 文件扩展名: {img_info['extension']}")
                            
                            if 'width' in img_info and 'height' in img_info:
                                print(f"        - 图片尺寸: {img_info['width']} x {img_info['height']} 像素")
                                # 检查图片尺寸是否过大
                                total_pixels = img_info['width'] * img_info['height']
                                if total_pixels > 4194304:  # 2048x2048
                                    print(f"        ⚠️  图片尺寸较大 ({total_pixels:,} 像素)，建议使用较小尺寸")
                            
                            if img_info['size_mb'] > 10:
                                print("        ⚠️  图片文件较大，建议压缩到10MB以下")
                            elif img_info['size_mb'] < 0.01:
                                print("        ⚠️  图片文件过小，可能已损坏")
                        except Exception as e:
                            print(f"      无法读取图片信息: {e}")
                    
                    print("   2. 提示词或图片内容可能触发限制")
                    print("   3. 服务器临时故障或过载")
                    print("   4. API配额或权限问题")
                    print("   5. Base64编码问题")
                    print("   解决方案:")
                    print("   - 检查图片格式（建议使用 JPG 或 PNG）")
                    print("   - 尝试压缩图片或调整图片尺寸（建议小于 2048x2048）")
                    print("   - 尝试使用不同的图片")
                    print("   - 简化提示词，避免复杂描述")
                    print("   - 稍后重试（可能是服务器临时故障）")
                    print("   - 检查API密钥是否有效且有足够配额")
                    print("   - 如果问题持续，联系技术支持并提供任务ID")
                else:
                    print("⚠️  未知错误")
                    print("   建议:")
                    print("   - 检查网络连接")
                    print("   - 稍后重试")
                    print("   - 联系技术支持")
                
                # 显示完整错误信息（用于调试）
                print("\n" + "-" * 60)
                print("完整错误信息（用于调试）:")
                print("-" * 60)
                print(json.dumps(result, indent=2, ensure_ascii=False))
                
                # 提供额外的排查建议
                print("\n" + "-" * 60)
                print("额外排查建议:")
                print("-" * 60)
                print("1. 检查图片文件:")
                if args.image_file:
                    try:
                        img_info = get_image_info(args.image_file)
                        print(f"   - 文件: {img_info['path']}")
                        print(f"   - 大小: {img_info['size_mb']:.2f} MB")
                        if 'width' in img_info and 'height' in img_info:
                            print(f"   - 尺寸: {img_info['width']} x {img_info['height']}")
                            aspect = img_info['width'] / img_info['height'] if img_info['height'] > 0 else 0
                            print(f"   - 宽高比: {aspect:.2f}")
                            if abs(aspect - 9/16) > 0.1 and abs(aspect - 16/9) > 0.1:
                                print(f"     ⚠️  图片宽高比 ({aspect:.2f}) 与设置的 aspectRatio ({args.aspect_ratio}) 不匹配")
                                print(f"     建议: 使用与 aspectRatio 匹配的图片，或调整 --aspect-ratio 参数")
                    except:
                        pass
                
                print("2. 尝试以下操作:")
                print("   - 使用 JPG 格式的图片（通常兼容性更好）")
                print("   - 尝试不使用参考图，只用提示词生成")
                print("   - 简化提示词，移除复杂描述")
                print("   - 检查网络连接是否稳定")
                print("   - 等待几分钟后重试（可能是服务器临时过载）")
                
                print("3. 如果问题持续:")
                print(f"   - 任务ID: {task_id}")
                print("   - 联系技术支持时提供以上信息")
                
            elif status == "succeeded":
                print("✅ 任务成功")
                print("=" * 60)
                print(json.dumps(result, indent=2, ensure_ascii=False))
                
                # 保存视频URL（如果有）
                if result.get("results"):
                    os.makedirs(args.output_dir, exist_ok=True)
                    for idx, video_result in enumerate(result["results"]):
                        if "url" in video_result:
                            video_url = video_result["url"]
                            print(f"\n视频URL: {video_url}")
                            print(f"PID: {video_result.get('pid', 'N/A')}")
                            print(f"去水印: {video_result.get('removeWatermark', False)}")
                            
                            # 可选：下载视频
                            # 注意：视频URL有效期为2小时
                            print(f"\n提示: 视频URL有效期为2小时，请及时下载")
            else:
                print("生成结果:")
                print(json.dumps(result, indent=2, ensure_ascii=False))
        
        elif args.command == 'upload-character':
            # 流式响应回调
            def progress_callback(response):
                progress = response.get("progress", 0)
                status = response.get("status", "")
                print(f"进度: {progress}% - 状态: {status}")
            
            if args.poll and args.webhook != "-1":
                print("错误: 使用轮询模式需要设置 --webhook=-1")
                return
            
            if args.poll:
                args.webhook = "-1"
            
            result = client.upload_character(
                url=args.url,
                video_file=args.video_file,
                timestamps=args.timestamps,
                webhook=args.webhook,
                shut_progress=args.shut_progress,
                stream=args.stream,
                callback=progress_callback if args.stream else None,
                debug=args.debug
            )
            
            # 处理轮询
            if args.poll and args.webhook == "-1":
                # webhook="-1"时，响应格式为: {"code": 0, "msg": "success", "data": {"id": "..."}}
                if isinstance(result, dict):
                    # 检查是否是webHook响应格式
                    if "code" in result and "data" in result:
                        if result.get("code") == 0:
                            task_id = result["data"].get("id")
                            if task_id:
                                print(f"任务ID: {task_id}")
                                print("开始轮询结果...")
                                
                                def poll_callback(response):
                                    progress = response.get("progress", 0)
                                    status = response.get("status", "")
                                    print(f"进度: {progress}% - 状态: {status}")
                                
                                try:
                                    final_result = client.poll_result(
                                        task_id,
                                        interval=args.poll_interval,
                                        timeout=args.poll_timeout,
                                        callback=poll_callback
                                    )
                                    result = final_result
                                except TimeoutError as e:
                                    print(f"\n❌ 错误: {e}")
                                    print(f"任务ID: {task_id}")
                                    print("提示: 可以使用 get-result 命令手动查询结果")
                                    return
                                except Exception as e:
                                    print(f"\n❌ 错误: 轮询失败: {e}")
                                    print(f"任务ID: {task_id}")
                                    print("提示: 可以使用 get-result 命令手动查询结果")
                                    return
                            else:
                                print("错误: 未获取到任务ID")
                                print(f"响应: {result}")
                                return
                        else:
                            print(f"错误: API返回错误代码 {result.get('code')}: {result.get('msg', 'Unknown error')}")
                            return
                    elif "id" in result:
                        # 直接是流式响应格式，已经有id
                        task_id = result.get("id")
                        if task_id:
                            print(f"任务ID: {task_id}")
                            print("提示: 可以使用 get-result 命令查询结果")
            
            # 显示结果
            print("\n" + "=" * 60)
            
            # 检查任务状态
            status = result.get("status", "")
            if status == "failed":
                print("❌ 上传失败")
                print("=" * 60)
                
                failure_reason = result.get("failure_reason", "")
                error_msg = result.get("error", "")
                task_id = result.get("id", "")
                
                print(f"任务ID: {task_id}")
                print(f"失败原因: {failure_reason}")
                print(f"错误信息: {error_msg}")
                
                print("\n" + "-" * 60)
                print("可能的原因和解决方案:")
                print("-" * 60)
                
                if failure_reason == "input_moderation":
                    print("⚠️  输入内容违规")
                    print("   解决方案: 检查视频内容是否符合规范")
                elif failure_reason == "error" or error_msg:
                    print("⚠️  系统错误")
                    if args.video_file:
                        try:
                            file_size = os.path.getsize(args.video_file) / (1024 * 1024)  # MB
                            print(f"   当前视频大小: {file_size:.2f} MB")
                            if file_size > 50:
                                print("   ⚠️  视频文件较大，建议压缩")
                        except:
                            pass
                    print("   解决方案:")
                    print("   - 检查视频文件大小和格式")
                    print("   - 确保timestamps参数格式正确（例如: '0,3'）")
                    print("   - 稍后重试")
                else:
                    print("⚠️  未知错误")
                    print("   建议: 稍后重试或联系技术支持")
                
                print("\n" + "-" * 60)
                print("完整错误信息（用于调试）:")
                print("-" * 60)
                print(json.dumps(result, indent=2, ensure_ascii=False))
            elif status == "succeeded":
                print("✅ 上传成功")
                print("=" * 60)
                print(json.dumps(result, indent=2, ensure_ascii=False))
                
                if result.get("results"):
                    for char_result in result["results"]:
                        if "character_id" in char_result:
                            print(f"\n角色ID: {char_result['character_id']}")
                            print(f"提示: 在提示词中使用 @{char_result['character_id']} 来使用该角色")
            else:
                print("上传结果:")
                print(json.dumps(result, indent=2, ensure_ascii=False))
        
        elif args.command == 'create-character':
            # 流式响应回调
            def progress_callback(response):
                progress = response.get("progress", 0)
                status = response.get("status", "")
                print(f"进度: {progress}% - 状态: {status}")
            
            if args.poll and args.webhook != "-1":
                print("错误: 使用轮询模式需要设置 --webhook=-1")
                return
            
            if args.poll:
                args.webhook = "-1"
            
            result = client.create_character_from_video(
                pid=args.pid,
                timestamps=args.timestamps,
                webhook=args.webhook,
                shut_progress=args.shut_progress,
                stream=args.stream,
                callback=progress_callback if args.stream else None,
                debug=args.debug
            )
            
            # 处理轮询
            if args.poll and args.webhook == "-1":
                if isinstance(result, dict) and "data" in result:
                    task_id = result["data"].get("id")
                    if task_id:
                        print(f"任务ID: {task_id}")
                        print("开始轮询结果...")
                        
                        def poll_callback(response):
                            progress = response.get("progress", 0)
                            status = response.get("status", "")
                            print(f"进度: {progress}% - 状态: {status}")
                        
                        final_result = client.poll_result(
                            task_id,
                            interval=args.poll_interval,
                            timeout=args.poll_timeout,
                            callback=poll_callback
                        )
                        result = final_result
            
            # 显示结果
            print("\n" + "=" * 60)
            
            # 检查任务状态
            status = result.get("status", "")
            if status == "failed":
                print("❌ 创建失败")
                print("=" * 60)
                
                failure_reason = result.get("failure_reason", "")
                error_msg = result.get("error", "")
                task_id = result.get("id", "")
                
                print(f"任务ID: {task_id}")
                print(f"失败原因: {failure_reason}")
                print(f"错误信息: {error_msg}")
                
                print("\n" + "-" * 60)
                print("可能的原因和解决方案:")
                print("-" * 60)
                
                if failure_reason == "error" or error_msg:
                    print("⚠️  系统错误")
                    print("   可能的原因:")
                    print("   1. 视频ID (pid) 不存在或无效")
                    print("   2. timestamps参数格式错误")
                    print("   3. 服务器临时故障")
                    print("   解决方案:")
                    print("   - 检查pid是否正确（格式: s_xxxxxxxxxxxxxxx）")
                    print("   - 确保timestamps格式正确（例如: '0,3'）")
                    print("   - 确保原视频已成功生成")
                    print("   - 稍后重试")
                else:
                    print("⚠️  未知错误")
                    print("   建议: 稍后重试或联系技术支持")
                
                print("\n" + "-" * 60)
                print("完整错误信息（用于调试）:")
                print("-" * 60)
                print(json.dumps(result, indent=2, ensure_ascii=False))
            elif status == "succeeded":
                print("✅ 创建成功")
                print("=" * 60)
                print(json.dumps(result, indent=2, ensure_ascii=False))
                
                if result.get("results"):
                    for char_result in result["results"]:
                        if "character_id" in char_result:
                            print(f"\n角色ID: {char_result['character_id']}")
                            print(f"提示: 在提示词中使用 @{char_result['character_id']} 来使用该角色")
            else:
                print("创建结果:")
                print(json.dumps(result, indent=2, ensure_ascii=False))
        
        elif args.command == 'get-result':
            try:
                result = client.get_result(args.task_id, debug=args.debug)
                print("\n" + "=" * 60)
                print("任务结果:")
                print("=" * 60)
                print(json.dumps(result, indent=2, ensure_ascii=False))
                
                # 如果是无音科技供应商，检查是否有视频URL
                if client.provider_type == "wuyinkeji":
                    if isinstance(result, dict):
                        if "url" in result:
                            print(f"\n✅ 视频URL: {result['url']}")
                        elif "results" in result and isinstance(result["results"], list):
                            for r in result["results"]:
                                if "url" in r:
                                    print(f"\n✅ 视频URL: {r['url']}")
            except RuntimeError as e:
                error_msg = str(e)
                if "未配置查询接口" in error_msg:
                    print(f"\n❌ {error_msg}")
                    print("\n提示:")
                    print("  1. 检查供应商配置文件中的 endpoints.get_result 字段")
                    print("  2. 联系供应商获取查询接口详情")
                    print(f"  3. 任务ID: {args.task_id}")
                else:
                    raise
            
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

