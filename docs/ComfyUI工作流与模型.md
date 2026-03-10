# UICS 中使用的 ComfyUI 工作流与模型

## 1. 总览

UICS 侧与 ComfyUI 集成时，主要依赖以下几类工作流 JSON：

- **图生图 / 图像编辑**
- **图生视频（单图 / 首末双图）**
- **图 + 音频 → 数字人视频**
- **Qwen3-TTS 语音克隆（数字人声）**

所有工作流 JSON 默认放在项目根目录（050tool），通过 `UICS/scripts/copy_deps.py` 复制到 `UICS/lib/`，UICS 运行时优先从 `lib/` 目录加载。

## 2. 如何开启 ComfyUI API 服务

UICS 通过 **HTTP + WebSocket** 调用 ComfyUI：提交工作流（`/prompt`）、上传文件（`/upload/image` 等）、通过 WebSocket 接收执行进度与结果。需先在运行 ComfyUI 的机器上启动 ComfyUI 并开放 API 与端口。

### 2.1 基本启动（本机使用）

- 进入 ComfyUI 项目目录，执行：
  ```bash
  python main.py
  ```
- 默认监听 **127.0.0.1:8188**。仅在本机访问时，UICS 中「ComfyUI 服务器」填写 **127.0.0.1:8188** 即可。

### 2.2 允许其他机器访问（UICS 与 ComfyUI 不在同一台机）

- 启动时加 **`--listen`**，让 ComfyUI 监听所有网卡（0.0.0.0）：
  ```bash
  python main.py --listen
  ```
- 仍为端口 **8188**。在 UICS 的「ComfyUI 服务器」中填写 **`<ComfyUI 所在机器的 IP>:8188`**（例如 `192.168.1.100:8188`）。

### 2.3 自定义端口

- 若 8188 被占用或需多实例，可指定端口，例如 9000：
  ```bash
  python main.py --port 9000
  # 或同时允许外网访问：
  python main.py --listen --port 9000
  ```
- UICS 中对应填写 **`<IP>:9000`**。

### 2.4 启动前检查

- 已安装 ComfyUI 及所需依赖（含本工作流用到的自定义节点，若有）。
- 已将本文档第 3～5 节所列**模型文件**放到 ComfyUI 的 `models` 对应子目录下，避免运行时报缺模型。
- 防火墙已放行 8188（或自选端口），以便 UICS 所在机可访问 ComfyUI。

### 2.5 验证 API 是否可用

- 浏览器打开 `http://<ComfyUI_IP>:8188`，能打开 ComfyUI 页面即说明服务已启。
- UICS 发起图片/视频/音频生成后，在「任务管理」中若任务能进入 running 并完成，即表示 API 与 WebSocket 工作正常；若报连接失败，请检查地址、端口与防火墙。

## 3. 图像相关工作流与模型

### 3.1 `z_image_workflow.json`

- **用途**：基础图像生成/编辑工作流，支持样式前缀、分辨率、随机种子等参数。
- **主要代码位置**：`z_image_client.py`（类 `ZImageClient`）。
- **典型调用场景**：
  - 批量图片生成（UICS 「图片生成」中选择 ComfyUI 方案时）。
  - 脚本级单次图像生成调试。
- **关键特性**：
  - 通过节点 ID 更新提示词、风格、Seed、Steps、CFG、分辨率、保存文件名前缀。
- **主要模型文件**（从工作流 JSON 中解析，需提前放入 ComfyUI 对应目录）：
  - `models/checkpoints/z_image_turbo_bf16.safetensors`
  - `models/clip/qwen_3_4b.safetensors`
  - `models/vae/ae.safetensors`

### 3.2 `act_02_qwen_Image_edit-aigc-3-api.json`

- **用途**：Qwen Image Edit 三参考图工作流，支持 1～3 张参考图编辑生成。
- **主要代码位置**：`z_image_client.py`（`load_qwen_image_edit_workflow` / `generate_image_edit` 等）。
- **说明**：
  - 支持按「1 张 / 2 张 / 3 张」参考图输入，不足 3 张时自动填充。
  - 参考图会先通过 ComfyUI `upload_file` 上传，再将生成的文件名写回工作流。
  - 正提示词、输出文件名前缀、采样参数（seed/steps/cfg）均支持代码侧动态控制。
- **主要模型文件**：与 `z_image_workflow.json` 相同（同一套 Qwen3 + z-image-turbo 组合）。

## 4. 视频相关工作流与模型

### 4.1 `act_video_wan2_2_14B_i2v-aigc-api.json`（单图图生视频 i2v）

- **用途**：单张首帧图像 + 提示词 → Wan2.2 14B 图生视频。
- **默认常量**：`DEFAULT_COMFYUI_VIDEO_WORKFLOW`。
- **主要代码位置**：
  - `video_generator.py` 中 `ComfyUIVideoGenerator` / `BatchVideoGenerator`。
  - UICS `server.py` 中普通视频生成任务（`mode != 'digital'`）。
- **典型调用场景**：
  - 命令行 `--generate-videos` 时的默认工作流。
  - UICS 「视频生成」中，只有首帧参考图（无末帧）的图生视频任务。
- **主要模型文件**（从工作流 JSON 中解析，需提前放入 ComfyUI 对应目录）：
  - `models/clip/umt5_xxl_fp8_e4m3fn_scaled.safetensors`
  - `models/vae/wan_2.1_vae.safetensors`
  - `models/unet/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors`
  - `models/unet/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors`
  - `models/lora/wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors`
  - `models/lora/wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors`

### 4.2 `act_video_wan2_2_14B_i2vse-aigc-api.json`（首末双图 i2vse）

- **用途**：首帧 + 末帧双图 → Wan2.2 14B 首末双图生视频。
- **默认常量**：`DEFAULT_COMFYUI_VIDEO_WORKFLOW_I2VSE`。
- **主要代码位置**：
  - `video_generator.py` 中 `ComfyUIVideoGenerator.generate_video(end_image_path=...)`。
  - `BatchVideoGenerator.generate_from_prompts`（检测「末帧图」并自动切换到 i2vse）。
- **关键逻辑**：
  - 根据工作流内 `WanFirstLastFrameToVideo` 节点，自动找到首帧/末帧对应的 `LoadImage` 节点，并分别填入上传后的文件名。
  - 在 UICS 中，当分镜存在首帧+末帧图片时，自动使用该工作流。
- **主要模型文件**：与 `act_video_wan2_2_14B_i2v-aigc-api.json` 相同（同一套 Wan2.2 i2v 14B 模型 + LoRA + VAE + CLIP）。

### 4.3 `act_video_wan2_2_14B_s2v-aigc-api.json`（图 + 音频 → 数字人视频 s2v）

- **用途**：单张角色形象图 + 对应音频（同分镜 ID） → 数字人视频（口型驱动）。
- **默认常量**：`DEFAULT_COMFYUI_VIDEO_WORKFLOW_S2V`，等待超时时间 `COMFYUI_S2V_WAIT_TIMEOUT_SECONDS`（默认 1800 秒）。
- **主要代码位置**：
  - `video_generator.py` 中 ComfyUI s2v 相关逻辑。
  - UICS `server.py` 中 `_generate_video_task`，`mode='digital'` 时强制使用该工作流。
- **典型调用场景**：
  - UICS 「媒体生成」中数字人视频生成（前端会传 `mode='digital'`、`generator_type='comfyui'`）。
- **主要模型文件**（从工作流 JSON 中解析，需提前放入 ComfyUI 对应目录）：
  - `models/clip/umt5_xxl_fp8_e4m3fn_scaled.safetensors`
  - `models/vae/wan_2.1_vae.safetensors`
  - `models/unet/wan2.2_s2v_14B_fp8_scaled.safetensors`
  - `models/audio/wav2vec2_large_english_fp16.safetensors`

## 5. 音频相关工作流与模型（ComfyUI）

### 5.1 `Qwen3-TTSVoiceCloneAPI.json`

- **用途**：Qwen3-TTS 语音克隆（数字人声）工作流。
- **主要代码位置**：
  - `qwen3_tts_client.py`（类 `Qwen3TTSClient`）。
  - UICS `server.py` 中数字人声生成接口 `POST /api/generate/audio_digital`（`GenerateDigitalAudioRequest`）。
- **关键点**：
  - 通过 `LoadAudio` 节点加载参考音频，`Qwen3TTSVoiceClone` 节点设置 `target_text` 等参数。
  - 通过 `SaveAudio` 节点的 `filename_prefix` 控制输出文件名。
  - UICS 前端中「数字人声生成」按钮固定调用该工作流（`generator_type='comfyui'`）。
  - **主要模型文件**（从工作流 JSON 中解析）：
    - `Qwen/Qwen3-TTS-12Hz-0.6B-Base`（由 `Qwen3TTSLoader` 自动从 ModelScope 下载）
    - `iic/SenseVoiceSmall`（ASR 模型，自动下载）
  - 这两个模型默认由节点自动从线上下载，但在**无法联网的环境**下，可提前在有网络的机器上通过 ComfyUI 下载好，对应目录整体拷贝到离线环境。

## 6. 配置与部署说明

- 所有上述 JSON 文件在开发环境下位于项目根目录（`050tool/`）。
- 运行 `python UICS/scripts/copy_deps.py` 后，这些 JSON 会被复制到 `UICS/lib/`，UICS 在有 `lib/` 时优先从其中加载工作流。
- 若需要更新 ComfyUI 工作流（例如在 ComfyUI 内调整节点或模型）：
  - 在 ComfyUI 中修改并导出新的 JSON。
  - 覆盖项目根目录下对应的 JSON 文件。
  - 重新执行一次 `python UICS/scripts/copy_deps.py`，同步到 `UICS/lib/`。
  - 重启 UICS 服务，使新工作流生效。

> **提示**：模型文件的具体目录结构以本地 ComfyUI 配置为准，上述路径为 ComfyUI 默认习惯（`models/checkpoints`、`models/clip`、`models/vae`、`models/unet` 等）。如果工作流中字段名不同（例如已手动改过路径），以工作流 JSON 中的 `*_name` 字段为准，将对应模型文件放到相应位置即可。

