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
ComfyUI客户端 - 用于调用本地ComfyUI工作流
支持调用sonic-audio-workflow
"""
import json
import uuid
import urllib.request
import urllib.parse
import urllib.error
import os
import mimetypes
try:
    from websocket import WebSocketApp
except ImportError:
    raise ImportError(
        "请安装 websocket-client 包: pip install websocket-client\n"
        "注意: 如果已安装但仍有错误，请先卸载错误的包: pip uninstall websocket\n"
        "然后重新安装: pip install websocket-client"
    )
import threading
import time
from typing import Dict, Any, Optional, Callable, Tuple, List


class ComfyUIClient:
    """ComfyUI客户端类，用于连接和执行工作流"""
    
    def __init__(self, server_address: str = "127.0.0.1:8188"):
        """
        初始化ComfyUI客户端
        
        Args:
            server_address: ComfyUI服务器地址，格式为 "host:port"
        """
        self.server_address = server_address
        self.client_id = str(uuid.uuid4())
        self.ws = None
        self.ws_thread = None
        self.prompt_id = None
        self.output_images = {}
        self.output_audio = {}
        self.output_videos = {}  # SaveVideo 节点输出 (gifs)
        self.is_running = False
        
    def _get_ws_url(self) -> str:
        """获取WebSocket URL"""
        return f"ws://{self.server_address}/ws?clientId={self.client_id}"
    
    def _get_api_url(self, endpoint: str) -> str:
        """获取API URL"""
        return f"http://{self.server_address}/{endpoint}"
    
    def _on_message(self, ws, message):
        """WebSocket消息处理"""
        if isinstance(message, str):
            message = json.loads(message)
        
        if message['type'] == 'execution_cached':
            print(f"执行已缓存: {message['data']}")
        elif message['type'] == 'execution_start':
            print(f"执行开始: {message['data']}")
        elif message['type'] == 'progress':
            data = message['data']
            print(f"进度: {data['value']}/{data['max']} - {data.get('node', '')}")
        elif message['type'] == 'executed':
            data = message['data']
            node_id = data['node']
            output = data.get('output') or {}  # 防止 output 为 None 导致 'images' in output 报错
            
            # 处理图片输出
            if output and 'images' in output:
                for image in output['images']:
                    filename = image['filename']
                    subfolder = image.get('subfolder', '')
                    image_type = image.get('type', 'output')
                    self.output_images[node_id] = {
                        'filename': filename,
                        'subfolder': subfolder,
                        'type': image_type
                    }
            
            # 处理音频输出
            if output and 'audio' in output:
                for audio in output['audio']:
                    filename = audio['filename']
                    subfolder = audio.get('subfolder', '')
                    audio_type = audio.get('type', 'output')
                    self.output_audio[node_id] = {
                        'filename': filename,
                        'subfolder': subfolder,
                        'type': audio_type
                    }
            
            # 处理视频输出 (SaveVideo 节点通常使用 gifs 或 videos 键)
            if output:
                video_list = None
                if 'gifs' in output:
                    video_list = output['gifs']
                elif 'videos' in output:
                    video_list = output['videos']
                if video_list:
                    for video in video_list:
                        filename = video['filename']
                        subfolder = video.get('subfolder', '')
                        video_type = video.get('type', 'output')
                        self.output_videos[node_id] = {
                            'filename': filename,
                            'subfolder': subfolder,
                            'type': video_type
                        }
            
            print(f"节点 {node_id} 执行完成")
        elif message['type'] == 'execution_error':
            print(f"执行错误: {message['data']}")
        elif message['type'] == 'execution_interrupted':
            print(f"执行中断: {message['data']}")
    
    def _on_error(self, ws, error):
        """WebSocket错误处理"""
        print(f"WebSocket错误: {error}")
    
    def _on_close(self, ws, close_status_code, close_msg):
        """WebSocket关闭处理"""
        print("WebSocket连接已关闭")
        self.is_running = False
    
    def _on_open(self, ws):
        """WebSocket打开处理"""
        print("WebSocket连接已建立")
        self.is_running = True
    
    def connect(self):
        """连接到ComfyUI服务器"""
        ws_url = self._get_ws_url()
        print(f"正在连接到: {ws_url}")
        
        self.ws = WebSocketApp(
            ws_url,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
            on_open=self._on_open
        )
        
        self.ws_thread = threading.Thread(target=self.ws.run_forever)
        self.ws_thread.daemon = True
        self.ws_thread.start()
        
        # 等待连接建立
        timeout = 10
        start_time = time.time()
        while not self.is_running and (time.time() - start_time) < timeout:
            time.sleep(0.1)
        
        if not self.is_running:
            raise ConnectionError("无法连接到ComfyUI服务器")
    
    def disconnect(self):
        """断开连接"""
        if self.ws:
            self.ws.close()
        if self.ws_thread:
            self.ws_thread.join(timeout=5)
    
    def queue_prompt(self, prompt: Dict[str, Any]) -> str:
        """
        提交工作流到队列
        
        Args:
            prompt: 工作流提示字典
            
        Returns:
            prompt_id: 提示ID
        """
        p = {"prompt": prompt, "client_id": self.client_id}
        data = json.dumps(p).encode('utf-8')
        
        req = urllib.request.Request(
            self._get_api_url("prompt"),
            data=data,
            headers={"Content-Type": "application/json"}
        )
        
        try:
            response = urllib.request.urlopen(req)
            result = json.loads(response.read())
            
            self.prompt_id = result['prompt_id']
            print(f"工作流已提交，Prompt ID: {self.prompt_id}")
            return self.prompt_id
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8')
            try:
                error_json = json.loads(error_body)
                error_data = error_json.get('error', {})
                error_msg = error_data.get('message', error_body)
                error_type = error_data.get('type', 'Unknown')
                extra_info = error_data.get('extra_info', {})
                
                print(f"\n错误详情:")
                print(f"  类型: {error_type}")
                print(f"  消息: {error_msg}")
                
                # 显示节点错误
                if 'node_errors' in error_data:
                    print(f"\n  节点错误:")
                    for node_id, node_error in error_data['node_errors'].items():
                        print(f"    节点 {node_id}:")
                        if isinstance(node_error, dict):
                            # 显示节点类型
                            if 'class_type' in node_error:
                                print(f"      节点类型: {node_error['class_type']}")
                            # 显示错误列表
                            if 'errors' in node_error:
                                print(f"      错误:")
                                for err in node_error['errors']:
                                    if isinstance(err, dict):
                                        err_type = err.get('type', 'Unknown')
                                        err_msg = err.get('message', '')
                                        err_details = err.get('details', '')
                                        print(f"        类型: {err_type}")
                                        if err_msg:
                                            print(f"        消息: {err_msg}")
                                        if err_details:
                                            print(f"        详情: {err_details}")
                                    else:
                                        print(f"        {err}")
                            # 显示依赖的输出节点
                            if 'dependent_outputs' in node_error:
                                print(f"      影响的输出节点: {node_error['dependent_outputs']}")
                        else:
                            print(f"      {node_error}")
                
                # 显示额外信息
                if extra_info:
                    print(f"\n  额外信息:")
                    for key, value in extra_info.items():
                        if isinstance(value, (dict, list)):
                            print(f"    {key}: {json.dumps(value, indent=6, ensure_ascii=False)}")
                        else:
                            print(f"    {key}: {value}")
                
                # 打印完整的错误JSON以便调试
                print(f"\n  完整错误信息 (JSON):")
                print(f"    {json.dumps(error_json, indent=4, ensure_ascii=False)}")
                
                # 如果是输出验证失败，检查是否是文件路径问题
                if 'outputs_failed_validation' in error_type or 'outputs' in error_type.lower():
                    # 检查是否有文件路径相关的错误
                    has_file_error = False
                    file_errors = []
                    # node_errors 在 error_json 的顶层，不在 error_data 中
                    if 'node_errors' in error_json:
                        for node_id, node_error in error_json['node_errors'].items():
                            if isinstance(node_error, dict) and 'errors' in node_error:
                                for err in node_error['errors']:
                                    if isinstance(err, dict):
                                        details = err.get('details', '')
                                        if 'Invalid' in details and ('file' in details.lower() or 'image' in details.lower() or 'audio' in details.lower()):
                                            has_file_error = True
                                            file_errors.append({
                                                'node_id': node_id,
                                                'class_type': node_error.get('class_type', 'Unknown'),
                                                'details': details
                                            })
                    
                    if has_file_error:
                        print(f"\n  ⚠️  文件路径错误:")
                        for fe in file_errors:
                            print(f"    节点 {fe['node_id']} ({fe['class_type']}):")
                            print(f"      {fe['details']}")
                        
                        print(f"\n  解决方案:")
                        print(f"    1. 确保文件存在于 ComfyUI 的 input 目录中")
                        print(f"       文件路径应该是相对于 ComfyUI 根目录的（例如: 'input/filename.jpg'）")
                        print(f"    2. 如果文件不在 ComfyUI 目录中，请将文件复制到 ComfyUI/input/ 目录")
                        print(f"       例如: cp input/inimg.jpg /path/to/ComfyUI/input/")
                        print(f"    3. 或者手动将文件放到 ComfyUI 的 input 目录，然后使用文件名（不含路径）")
                        print(f"       例如: 如果文件在 ComfyUI/input/inimg.jpg，路径应该是 'inimg.jpg' 或 'input/inimg.jpg'")
                    else:
                        print(f"\n  提示: 工作流的输出节点配置不正确。")
                        print(f"  请确保:")
                        print(f"    1. 工作流包含有效的输出节点（如 SaveImage, SaveAudio, SaveVideo 等）")
                        print(f"    2. 输出节点的输入连接正确")
                        print(f"    3. 所有节点类型都在你的 ComfyUI 中可用")
                        print(f"  建议: 从 ComfyUI 界面导出工作流（Save API Format）以确保格式正确")
                    
                    # 检查工作流中的输出节点
                    print(f"\n  工作流中的输出节点:")
                    output_nodes = []
                    for node_id, node_data in prompt.items():
                        if isinstance(node_data, dict):
                            class_type = node_data.get('class_type', '')
                            if 'Save' in class_type or 'Output' in class_type:
                                output_nodes.append(f"节点 {node_id}: {class_type}")
                    if output_nodes:
                        for node in output_nodes:
                            print(f"    - {node}")
                    else:
                        print(f"    (未找到输出节点)")
                    
            except Exception as parse_error:
                print(f"\n错误响应: {error_body}")
                print(f"解析错误响应时出错: {parse_error}")
            raise
    
    def load_workflow(self, workflow_path: str) -> Dict[str, Any]:
        """
        加载工作流文件
        
        Args:
            workflow_path: 工作流JSON文件路径
            
        Returns:
            工作流字典
        """
        with open(workflow_path, 'r', encoding='utf-8') as f:
            workflow = json.load(f)
        
        # 清理工作流：移除非API字段
        cleaned_workflow = {}
        for key, value in workflow.items():
            # 跳过注释和说明字段
            if key.startswith('_'):
                continue
            
            # 清理节点中的_meta字段
            if isinstance(value, dict):
                cleaned_node = {}
                for node_key, node_value in value.items():
                    if node_key != '_meta':
                        cleaned_node[node_key] = node_value
                cleaned_workflow[key] = cleaned_node
            else:
                cleaned_workflow[key] = value
        
        return cleaned_workflow
    
    def update_workflow_input(self, workflow: Dict[str, Any], node_id: str, input_key: str, input_value: Any) -> bool:
        """
        更新工作流中指定节点的输入值
        
        Args:
            workflow: 工作流字典
            node_id: 节点ID（字符串格式，如 "18"）
            input_key: 输入键名（如 "image", "audio"）
            input_value: 新的输入值
            
        Returns:
            是否成功更新
        """
        if node_id not in workflow:
            return False
        
        node = workflow[node_id]
        if 'inputs' not in node:
            node['inputs'] = {}
        
        node['inputs'][input_key] = input_value
        return True
    
    def find_nodes_by_class_type(self, workflow: Dict[str, Any], class_type: str) -> List[str]:
        """
        根据节点类型查找节点ID
        
        Args:
            workflow: 工作流字典
            class_type: 节点类型（如 "LoadImage", "LoadAudio"）
            
        Returns:
            节点ID列表
        """
        node_ids = []
        for node_id, node_data in workflow.items():
            if isinstance(node_data, dict) and node_data.get('class_type') == class_type:
                node_ids.append(node_id)
        return node_ids
    
    def execute_workflow(self, workflow: Dict[str, Any], wait: bool = True, wait_timeout: Optional[int] = None) -> Dict[str, Any]:
        """
        执行工作流
        
        Args:
            workflow: 工作流字典
            wait: 是否等待执行完成
            wait_timeout: 等待超时秒数；为 None 时默认 600（10 分钟）。数字人/长流程可传更大值（如 1800、3600）
            
        Returns:
            执行结果字典
        """
        if not self.is_running:
            self.connect()
        
        # 清空之前的输出
        self.output_images = {}
        self.output_audio = {}
        self.output_videos = {}
        
        # 提交工作流
        prompt_id = self.queue_prompt(workflow)
        
        if wait:
            # 等待执行完成（有参考图时 ComfyUI 可能先报 execution_cached 再重跑，耗时会更长）
            max_wait_time = 600 if wait_timeout is None else max(60, int(wait_timeout))
            start_time = time.time()
            
            while (time.time() - start_time) < max_wait_time:
                # 检查执行状态
                try:
                    history = self.get_history(prompt_id)
                except Exception:
                    history = None
                entry = None
                if history and prompt_id in history:
                    entry = history[prompt_id]
                    # ComfyUI 可能返回单条或列表（同一 prompt_id 多次执行如 cached 后重跑）
                    if isinstance(entry, list) and len(entry) > 0:
                        entry = entry[-1]
                    if isinstance(entry, dict):
                        st = entry.get('status') or {}
                        # 1) 标准 completed 标记
                        completed = bool(st.get('completed'))
                        # 2) 某些版本只提供 status_str 字段，如 success / error
                        status_str = str(st.get('status_str', '') or '').lower()
                        if status_str in ('success', 'finished', 'complete'):
                            completed = True
                        if completed:
                            break
                        # 3) 若 status 中有 error 字段，直接报错
                        if st.get('error', False):
                            raise RuntimeError(f"工作流执行失败: {st.get('error', 'Unknown error')}")
                        # 4) 若 history 条目中已经包含 outputs，也视为完成
                        outputs = entry.get('outputs') or {}
                        if outputs:
                            break
                # 若 WebSocket 已收到 SaveImage/SaveVideo/Audio 等输出，也视为完成（避免 history 结构差异导致一直不 break）
                if self.output_images or self.output_videos or self.output_audio:
                    time.sleep(0.5)  # 再等 0.5 秒确保输出写全
                    break
                time.sleep(1)
            else:
                raise TimeoutError(f"工作流执行超时（已等待 {max_wait_time} 秒）")
        
        return {
            'prompt_id': prompt_id,
            'images': self.output_images,
            'audio': self.output_audio,
            'videos': self.output_videos
        }
    
    def get_history(self, prompt_id: Optional[str] = None) -> Dict[str, Any]:
        """
        获取执行历史
        
        Args:
            prompt_id: 可选的提示ID，如果提供则只获取该提示的历史
            
        Returns:
            历史记录字典
        """
        url = self._get_api_url("history")
        if prompt_id:
            url += f"/{prompt_id}"
        
        req = urllib.request.Request(url)
        response = urllib.request.urlopen(req)
        return json.loads(response.read())
    
    def get_node_definitions(self) -> Dict[str, Any]:
        """
        获取可用的节点定义
        
        Returns:
            节点定义字典
        """
        url = self._get_api_url("object_info")
        req = urllib.request.Request(url)
        response = urllib.request.urlopen(req)
        return json.loads(response.read())
    
    def upload_file(self, file_path: str, subfolder: str = "input", overwrite: bool = True) -> Dict[str, Any]:
        """
        上传文件到ComfyUI服务器
        
        Args:
            file_path: 本地文件路径
            subfolder: 子文件夹（默认: "input"）
            overwrite: 是否覆盖已存在的文件
            
        Returns:
            上传后的文件名（相对于ComfyUI根目录）
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        filename = os.path.basename(file_path)
        
        # 读取文件
        with open(file_path, 'rb') as f:
            file_data = f.read()
        
        # 准备multipart/form-data请求
        content_type = mimetypes.guess_type(file_path)[0] or 'application/octet-stream'
        is_audio = content_type.startswith("audio/")
        
        # 每个端点需要其期望的表单字段名：ComfyUI 标准仅有 POST /upload/image，字段名为 "image"
        # 音频无 upload/audio，故回退到 upload/image 时必须使用字段 "image" 才能被接受
        if is_audio:
            endpoint_and_field = [
                (f"upload/audio?subfolder={subfolder}&overwrite={str(overwrite).lower()}", "audio"),
                (f"upload?subfolder={subfolder}&overwrite={str(overwrite).lower()}", "file"),
                (f"upload/image?subfolder={subfolder}&overwrite={str(overwrite).lower()}", "image"),
            ]
        else:
            endpoint_and_field = [
                (f"upload/image?subfolder={subfolder}&overwrite={str(overwrite).lower()}", "image"),
                (f"upload?subfolder={subfolder}&overwrite={str(overwrite).lower()}", "file"),
            ]
        
        last_error = None
        for endpoint, field_name in endpoint_and_field:
            boundary = uuid.uuid4().hex
            data_parts = []
            data_parts.append(f'--{boundary}'.encode())
            data_parts.append(f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"'.encode())
            data_parts.append(f'Content-Type: {content_type}'.encode())
            data_parts.append(b'')
            data_parts.append(file_data)
            data_parts.append(f'--{boundary}--'.encode())
            body = b'\r\n'.join(data_parts)
            try:
                url = self._get_api_url(endpoint)
                req = urllib.request.Request(url, data=body)
                req.add_header('Content-Type', f'multipart/form-data; boundary={boundary}')
                req.add_header('Content-Length', str(len(body)))
                response = urllib.request.urlopen(req)
                result = json.loads(response.read())
                if isinstance(result, dict):
                    return result
                return {"name": str(result) if result else filename, "subfolder": subfolder, "type": "input"}
            except urllib.error.HTTPError as e:
                last_error = e
                continue
            except Exception as e:
                last_error = e
                continue
        
        # 所有端点均失败时抛出异常，便于调用方区分“未上传”与“已上传”
        err_msg = f"参考音频上传失败: 已尝试 {len(endpoint_and_field)} 个端点均未成功"
        if last_error is not None:
            err_msg += f"；最后错误: {last_error}"
        raise RuntimeError(err_msg)
    
    def validate_workflow(self, workflow: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        基本验证工作流格式
        
        Args:
            workflow: 工作流字典
            
        Returns:
            (是否有效, 错误列表)
        """
        errors = []
        
        if not isinstance(workflow, dict):
            errors.append("工作流必须是字典格式")
            return False, errors
        
        if len(workflow) == 0:
            errors.append("工作流不能为空")
            return False, errors
        
        # 检查每个节点
        for node_id, node_data in workflow.items():
            if not isinstance(node_data, dict):
                errors.append(f"节点 {node_id} 的数据格式不正确")
                continue
            
            if 'class_type' not in node_data:
                errors.append(f"节点 {node_id} 缺少 'class_type' 字段")
            
            if 'inputs' not in node_data:
                errors.append(f"节点 {node_id} 缺少 'inputs' 字段")
        
        return len(errors) == 0, errors
    
    def get_image(self, filename: str, subfolder: str = "", image_type: str = "output") -> bytes:
        """
        获取生成的图片
        
        Args:
            filename: 文件名
            subfolder: 子文件夹
            image_type: 图片类型
            
        Returns:
            图片字节数据
        """
        data = {"filename": filename, "subfolder": subfolder, "type": image_type}
        url_values = urllib.parse.urlencode(data)
        url = f"{self._get_api_url('view')}?{url_values}"
        
        req = urllib.request.Request(url)
        response = urllib.request.urlopen(req)
        return response.read()
    
    def get_audio(self, filename: str, subfolder: str = "", audio_type: str = "output") -> bytes:
        """
        获取生成的音频
        
        Args:
            filename: 文件名
            subfolder: 子文件夹
            audio_type: 音频类型
            
        Returns:
            音频字节数据
        """
        data = {"filename": filename, "subfolder": subfolder, "type": audio_type}
        url_values = urllib.parse.urlencode(data)
        url = f"{self._get_api_url('view')}?{url_values}"
        
        req = urllib.request.Request(url)
        response = urllib.request.urlopen(req)
        return response.read()


def main():
    """主函数示例"""
    import argparse
    import os
    
    parser = argparse.ArgumentParser(description='调用ComfyUI sonic-audio-workflow')
    parser.add_argument('--workflow', type=str, default='sonic-audio-workflow-api.json',
                        help='工作流JSON文件路径')
    parser.add_argument('--server', type=str, default='127.0.0.1:8188',
                        help='ComfyUI服务器地址 (默认: 127.0.0.1:8188)')
    parser.add_argument('--output-dir', type=str, default='./output',
                        help='输出目录 (默认: ./output)')
    parser.add_argument('--image', type=str, default=None,
                        help='图像文件路径（用于LoadImage节点）')
    parser.add_argument('--audio', type=str, default=None,
                        help='音频文件路径（用于LoadAudio节点）')
    parser.add_argument('--image-node-id', type=str, default=None,
                        help='LoadImage节点ID（如果指定，将只更新该节点）')
    parser.add_argument('--audio-node-id', type=str, default=None,
                        help='LoadAudio节点ID（如果指定，将只更新该节点）')
    parser.add_argument('--duration', type=float, default=None,
                        help='音频时长（秒，用于SONIC_PreData节点，默认使用工作流中的值）')
    parser.add_argument('--duration-node-id', type=str, default=None,
                        help='SONIC_PreData节点ID（如果指定，将只更新该节点）')
    parser.add_argument('--seed', type=int, default=None,
                        help='随机种子（用于SONICSampler节点）')
    parser.add_argument('--inference-steps', type=int, default=None,
                        help='推理步数（用于SONICSampler节点，默认25）')
    parser.add_argument('--fps', type=int, default=None,
                        help='帧率（用于SONICSampler节点，默认25）')
    parser.add_argument('--ip-audio-scale', type=float, default=None,
                        help='音频缩放系数（用于SONICTLoader节点，默认1.0）')
    parser.add_argument('--min-resolution', type=int, default=None,
                        help='最小分辨率（用于SONIC_PreData节点，默认256）')
    parser.add_argument('--expand-ratio', type=float, default=None,
                        help='扩展比例（用于SONIC_PreData节点，默认0.5）')
    parser.add_argument('--debug', action='store_true',
                        help='显示调试信息（包括提交的工作流JSON）')
    
    args = parser.parse_args()
    
    # 创建输出目录
    os.makedirs(args.output_dir, exist_ok=True)
    
    # 创建客户端
    client = ComfyUIClient(server_address=args.server)
    
    try:
        # 连接服务器
        print("正在连接ComfyUI服务器...")
        client.connect()
        
        # 加载工作流
        if not os.path.exists(args.workflow):
            print(f"错误: 工作流文件不存在: {args.workflow}")
            print("\n解决方案:")
            print("1. 从ComfyUI界面导出工作流:")
            print("   - 在ComfyUI中打开你的工作流")
            print("   - 点击菜单 -> Save (API Format)")
            print("   - 保存为JSON文件")
            print(f"2. 将工作流文件放到当前目录，或使用 --workflow 参数指定完整路径")
            print(f"3. 当前目录: {os.getcwd()}")
            print(f"4. 当前目录中的文件: {', '.join([f for f in os.listdir('.') if f.endswith('.json')]) if any(f.endswith('.json') for f in os.listdir('.')) else '无JSON文件'}")
            return
        
        print(f"正在加载工作流: {args.workflow}")
        workflow = client.load_workflow(args.workflow)
        
        # 更新图像文件路径
        if args.image:
            # 检查文件是否存在
            if not os.path.exists(args.image):
                print(f"错误: 图像文件不存在: {args.image}")
                print(f"  请确保文件路径正确，或使用绝对路径")
                return
            
            # 上传文件到ComfyUI
            try:
                print(f"正在上传图像文件: {args.image}")
                uploaded_result = client.upload_file(args.image, subfolder="input")
                uploaded_filename = uploaded_result.get('name', os.path.basename(args.image)) if isinstance(uploaded_result, dict) else uploaded_result
                print(f"  上传成功: {uploaded_filename}")
                image_path = uploaded_filename
            except Exception as e:
                print(f"警告: 上传文件失败: {e}")
                # 尝试只使用文件名（假设文件已经在ComfyUI的input目录中）
                filename_only = os.path.basename(args.image)
                print(f"  尝试使用文件名: {filename_only}")
                image_path = filename_only
            
            if args.image_node_id:
                # 使用指定的节点ID
                if client.update_workflow_input(workflow, args.image_node_id, 'image', image_path):
                    print(f"已更新图像文件: {image_path} (节点 {args.image_node_id})")
                else:
                    print(f"警告: 无法更新节点 {args.image_node_id} 的图像文件")
            else:
                # 自动查找LoadImage节点
                image_nodes = client.find_nodes_by_class_type(workflow, 'LoadImage')
                if image_nodes:
                    for node_id in image_nodes:
                        client.update_workflow_input(workflow, node_id, 'image', image_path)
                        print(f"已更新图像文件: {image_path} (节点 {node_id})")
                else:
                    print(f"警告: 未找到LoadImage节点，无法更新图像文件")
        
        # 更新音频文件路径
        if args.audio:
            # 检查文件是否存在
            if not os.path.exists(args.audio):
                print(f"错误: 音频文件不存在: {args.audio}")
                print(f"  请确保文件路径正确，或使用绝对路径")
                return
            
            # 上传文件到ComfyUI
            try:
                print(f"正在上传音频文件: {args.audio}")
                uploaded_result = client.upload_file(args.audio, subfolder="input")
                uploaded_filename = uploaded_result.get('name', os.path.basename(args.audio)) if isinstance(uploaded_result, dict) else uploaded_result
                print(f"  上传成功: {uploaded_filename}")
                audio_path = uploaded_filename
            except Exception as e:
                print(f"警告: 上传文件失败: {e}")
                # 尝试只使用文件名（假设文件已经在ComfyUI的input目录中）
                filename_only = os.path.basename(args.audio)
                print(f"  尝试使用文件名: {filename_only}")
                audio_path = filename_only
            
            if args.audio_node_id:
                # 使用指定的节点ID
                if client.update_workflow_input(workflow, args.audio_node_id, 'audio', audio_path):
                    print(f"已更新音频文件: {audio_path} (节点 {args.audio_node_id})")
                else:
                    print(f"警告: 无法更新节点 {args.audio_node_id} 的音频文件")
            else:
                # 自动查找LoadAudio节点
                audio_nodes = client.find_nodes_by_class_type(workflow, 'LoadAudio')
                if audio_nodes:
                    for node_id in audio_nodes:
                        client.update_workflow_input(workflow, node_id, 'audio', audio_path)
                        print(f"已更新音频文件: {audio_path} (节点 {node_id})")
                else:
                    print(f"警告: 未找到LoadAudio节点，无法更新音频文件")
        
        # 更新音频时长参数
        if args.duration is not None:
            if args.duration_node_id:
                # 使用指定的节点ID
                if client.update_workflow_input(workflow, args.duration_node_id, 'duration', args.duration):
                    print(f"已更新音频时长: {args.duration}秒 (节点 {args.duration_node_id})")
                else:
                    print(f"警告: 无法更新节点 {args.duration_node_id} 的音频时长")
            else:
                # 自动查找SONIC_PreData节点
                predata_nodes = client.find_nodes_by_class_type(workflow, 'SONIC_PreData')
                if predata_nodes:
                    for node_id in predata_nodes:
                        client.update_workflow_input(workflow, node_id, 'duration', args.duration)
                        print(f"已更新音频时长: {args.duration}秒 (节点 {node_id})")
                else:
                    print(f"警告: 未找到SONIC_PreData节点，无法更新音频时长")
        
        # 更新随机种子
        if args.seed is not None:
            sampler_nodes = client.find_nodes_by_class_type(workflow, 'SONICSampler')
            if sampler_nodes:
                for node_id in sampler_nodes:
                    client.update_workflow_input(workflow, node_id, 'seed', args.seed)
                    print(f"已更新随机种子: {args.seed} (节点 {node_id})")
            else:
                print(f"警告: 未找到SONICSampler节点，无法更新随机种子")
        
        # 更新推理步数
        if args.inference_steps is not None:
            sampler_nodes = client.find_nodes_by_class_type(workflow, 'SONICSampler')
            if sampler_nodes:
                for node_id in sampler_nodes:
                    client.update_workflow_input(workflow, node_id, 'inference_steps', args.inference_steps)
                    print(f"已更新推理步数: {args.inference_steps} (节点 {node_id})")
            else:
                print(f"警告: 未找到SONICSampler节点，无法更新推理步数")
        
        # 更新帧率
        if args.fps is not None:
            sampler_nodes = client.find_nodes_by_class_type(workflow, 'SONICSampler')
            if sampler_nodes:
                for node_id in sampler_nodes:
                    client.update_workflow_input(workflow, node_id, 'fps', args.fps)
                    print(f"已更新帧率: {args.fps} (节点 {node_id})")
            else:
                print(f"警告: 未找到SONICSampler节点，无法更新帧率")
        
        # 更新音频缩放系数
        if args.ip_audio_scale is not None:
            loader_nodes = client.find_nodes_by_class_type(workflow, 'SONICTLoader')
            if loader_nodes:
                for node_id in loader_nodes:
                    client.update_workflow_input(workflow, node_id, 'ip_audio_scale', args.ip_audio_scale)
                    print(f"已更新音频缩放系数: {args.ip_audio_scale} (节点 {node_id})")
            else:
                print(f"警告: 未找到SONICTLoader节点，无法更新音频缩放系数")
        
        # 更新最小分辨率
        if args.min_resolution is not None:
            predata_nodes = client.find_nodes_by_class_type(workflow, 'SONIC_PreData')
            if predata_nodes:
                for node_id in predata_nodes:
                    client.update_workflow_input(workflow, node_id, 'min_resolution', args.min_resolution)
                    print(f"已更新最小分辨率: {args.min_resolution} (节点 {node_id})")
            else:
                print(f"警告: 未找到SONIC_PreData节点，无法更新最小分辨率")
        
        # 更新扩展比例
        if args.expand_ratio is not None:
            predata_nodes = client.find_nodes_by_class_type(workflow, 'SONIC_PreData')
            if predata_nodes:
                for node_id in predata_nodes:
                    client.update_workflow_input(workflow, node_id, 'expand_ratio', args.expand_ratio)
                    print(f"已更新扩展比例: {args.expand_ratio} (节点 {node_id})")
            else:
                print(f"警告: 未找到SONIC_PreData节点，无法更新扩展比例")
        
        # 基本验证工作流
        is_valid, errors = client.validate_workflow(workflow)
        if not is_valid:
            print("\n工作流格式验证失败:")
            for error in errors:
                print(f"  - {error}")
            print("\n提示: 请从 ComfyUI 界面导出工作流（Save API Format）以确保格式正确")
            return
        
        # 调试模式：显示工作流内容
        if args.debug:
            print("\n调试信息 - 工作流内容:")
            print(json.dumps(workflow, indent=2, ensure_ascii=False))
            print("\n工作流中的节点:")
            for node_id, node_data in workflow.items():
                if isinstance(node_data, dict):
                    class_type = node_data.get('class_type', 'Unknown')
                    print(f"  节点 {node_id}: {class_type}")
        
        # 执行工作流
        print("正在执行工作流...")
        result = client.execute_workflow(workflow, wait=True)
        
        print(f"\n执行完成!")
        print(f"Prompt ID: {result['prompt_id']}")
        
        # 保存音频输出
        if result['audio']:
            print("\n保存音频文件...")
            for node_id, audio_info in result['audio'].items():
                audio_data = client.get_audio(
                    audio_info['filename'],
                    audio_info.get('subfolder', ''),
                    audio_info.get('type', 'output')
                )
                output_path = os.path.join(args.output_dir, audio_info['filename'])
                with open(output_path, 'wb') as f:
                    f.write(audio_data)
                print(f"  保存: {output_path}")
        
        # 保存图片输出（如果有）
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
        
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        client.disconnect()


if __name__ == "__main__":
    main()

