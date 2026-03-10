# UICS 单独部署说明

为便于将 UICS 整体移动到其他机器部署，运行依赖已支持全部落在 UICS 目录内。  
常规安装与运行步骤见 [docs/安装与运行.md](docs/安装与运行.md)。

## 1. 在开发机上准备（首次或依赖有更新时）

在**项目根目录**（050tool）执行：

```bash
python UICS/scripts/copy_deps.py
```

会将以下内容复制到 `UICS/lib/`：

- **Python 模块**：excel_reader, image_generator, video_generator, audio_generator, comfyui_client, z_image_client, nanobanana_client, qwen3_tts_client, sora_video_client
- **工作流 JSON**：图生视频 i2v/i2vse/s2v、图编辑、Qwen3-TTS 等所用工作流

## 2. 部署到目标机器

- 将整个 **UICS** 目录（含 `lib/`、`templates/`、`static/`、`output/`、`all_episodes.xlsx` 等）拷贝到目标机。
- 在目标机安装 Python 依赖（与开发机一致），例如：
  - `pandas`, `fastapi`, `uvicorn`, `python-multipart`, `passlib`, `websockets` 等
- 在 **UICS 目录**下启动服务，例如：
  - `uvicorn server:app --host 0.0.0.0 --port 5000`
  - 或使用项目内的启动脚本（若有）

## 3. 运行逻辑说明

- 若存在 `UICS/lib/` 且其中有 `excel_reader.py`，服务会**优先从 `UICS/lib` 加载**上述模块和工作流，不再依赖项目根目录。
- 若未执行过 `copy_deps.py`（即没有 `lib` 或其中没有 `excel_reader.py`），则仍从项目根目录加载（与原有行为一致）。

这样 UICS 目录即可单独拷贝、单独部署。
