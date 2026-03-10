#!/bin/bash

# 停止UICS服务器脚本

echo "查找运行中的UICS服务器进程..."

# 查找占用5000端口的进程
PID=$(lsof -ti:5000 2>/dev/null)

if [ -z "$PID" ]; then
    echo "没有找到占用5000端口的进程"
    exit 0
fi

echo "找到进程 PID: $PID"
ps -p $PID -o pid,cmd

read -p "是否要停止这个进程? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    kill $PID
    sleep 1
    if kill -0 $PID 2>/dev/null; then
        echo "进程仍在运行，强制停止..."
        kill -9 $PID
    fi
    echo "进程已停止"
else
    echo "取消操作"
fi

