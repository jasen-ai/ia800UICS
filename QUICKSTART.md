# UICS 快速启动指南

## 快速开始

### 1. 安装依赖

```bash
cd UICS
pip install -r requirements.txt
```

### 2. 启动服务器

```bash
# 方式1: 直接运行
python server.py

# 方式2: 使用 uvicorn
uvicorn server:app --host 0.0.0.0 --port 5000

# 方式3: 使用启动脚本（Linux/macOS）
./start.sh
```

### 3. 访问系统

在浏览器中打开：**http://localhost:5000**

### 4. 登录

- 用户名: `admin`
- 密码: `admin123`

## 基本使用流程

### 编辑 Excel

1. 登录后，点击「Excel 编辑」标签页
2. 点击「加载 Excel」按钮
3. 选择要编辑的工作表（如：音频汇总、角色汇总等）
4. 在表格中直接编辑数据
5. 修改会自动保存

### 生成媒体

1. 点击「媒体生成」标签页
2. 选择要生成的内容类型：
   - **图片生成**：基于图像提示词与参考图生成
   - **视频生成**：ComfyUI（i2v/i2vse）或 Sora
   - **音频生成**：火山引擎或 ComfyUI (Qwen3-TTS)
   - **数字人声生成**：ComfyUI Qwen3-TTS
3. 配置参数（输出目录、剧集/分镜过滤等）
   - 使用 **ComfyUI** 时，需要先启动 ComfyUI，并在页面填写「ComfyUI 服务器」（例如 `127.0.0.1:8188` 或 `192.168.1.100:8188`）。
   - ComfyUI 的启动方式、API 监听与模型准备见：[docs/ComfyUI工作流与模型.md](docs/ComfyUI工作流与模型.md)
4. 点击对应「开始生成」按钮
5. 在「任务管理」中查看进度与结果

### 查看任务

1. 点击「任务管理」标签页
2. 查看任务列表与实时进度
3. 查看任务结果或错误信息

## 常见问题

### Q: 无法启动服务器？

检查：Python 版本（建议 3.8+）、依赖是否安装完整、端口 5000 是否被占用。

### Q: Excel 文件加载失败？

默认使用 `UICS/all_episodes.xlsx`。请确认文件存在、路径正确且可读。

### Q: 生成任务失败？

检查：ComfyUI/Sora 等后端是否已启动、页面中生成器地址与端口是否正确、任务详情中的报错信息。

### Q: 如何单独部署到其他机器？

在项目根目录执行 `python UICS/scripts/copy_deps.py`，再将整个 UICS 目录拷贝到目标机并安装依赖。详见 [DEPLOY.md](DEPLOY.md)。

## 下一步

- 安装与运行详情：[docs/安装与运行.md](docs/安装与运行.md)
- 系统功能与结构说明：[docs/系统说明.md](docs/系统说明.md)
- 完整说明与文档索引：[README.md](README.md)

