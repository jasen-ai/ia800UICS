#!/bin/bash

# UICS服务器启动脚本

echo "启动UICS服务器..."

# 检查Python版本
python3 --version || {
    echo "错误: 未找到Python3"
    exit 1
}

# 检查依赖
echo "检查依赖..."
pip3 install -r requirements.txt || {
    echo "错误: 依赖安装失败"
    exit 1
}

# 检查Excel文件是否存在
EXCEL_FILE="../all_episodes.xlsx"
if [ ! -f "$EXCEL_FILE" ]; then
    echo "警告: Excel文件不存在: $EXCEL_FILE"
    echo "请确保all_episodes.xlsx文件在项目根目录"
fi

# 创建必要的目录
mkdir -p uploads output

# 检查并停止占用端口的进程
echo "检查端口5000..."
if lsof -ti:5000 > /dev/null 2>&1; then
    echo "发现端口5000被占用，正在停止..."
    lsof -ti:5000 | xargs kill -9 2>/dev/null
    sleep 1
fi

# 启动服务器
echo "启动服务器..."
echo "使用uvicorn启动FastAPI服务器..."
uvicorn server:app --host 0.0.0.0 --port 5000 --reload

