# UICS 系统架构文档

> **说明**：功能与模块的完整说明已迁移至 [docs/系统说明.md](docs/系统说明.md)。本文档保留架构图与部分设计说明，技术栈已更新为当前实现（FastAPI + 原生 WebSocket）。

## 系统概述

UICS（Unified Intelligent Content System）是基于 **FastAPI** 的 Web 应用，提供多用户 Excel 编辑与图片/视频/音频（含数字人视频与数字人声）的批量生成与任务管理。

## 技术栈

### 后端
- **FastAPI**: Web 框架、REST API
- **Uvicorn**: ASGI 服务器
- **WebSocket**: 原生 WebSocket，实时任务与 Excel 更新
- **Pandas / OpenPyXL**: Excel 读写
- **Passlib / python-jose**: 认证与密码

### 前端
- **Vue.js 3**: 前端框架
- **Handsontable**: Excel 表格编辑
- **原生 WebSocket**: 与后端长连接
- **原生 CSS**: 样式

## 系统架构

```
┌─────────────────┐
│   Web Browser   │
│   (Vue.js App)  │
└────────┬────────┘
         │ HTTP / WebSocket
         │
┌────────▼────────┐
│ FastAPI Server  │
│  (server.py)    │
└────────┬────────┘
         │
    ┌────┴────┬──────────┬──────────┬────────────┐
    │         │          │          │            │
┌───▼───┐ ┌──▼───┐ ┌────▼────┐ ┌───▼────┐  ┌───▼────┐
│ Excel │ │Image │ │ Video   │ │ Audio  │  │ 数字人  │
│Reader │ │Gen.  │ │ Gen.    │ │ Gen.   │  │ 视频/声 │
└───────┘ └──────┘ └────────┘ └────────┘  └────────┘
```

## 核心模块

### 1. 服务器模块 (server.py)

#### 认证模块
- `login()`: 用户登录
- `register()`: 用户注册
- `logout()`: 用户登出
- `require_auth`: 认证装饰器

#### Excel模块
- `read_excel()`: 读取Excel文件
- `write_excel()`: 写入Excel单元格
- `add_row()`: 添加新行
- `delete_row()`: 删除行

#### 生成模块
- `generate_image()`: 创建图片生成任务
- `generate_video()`: 创建视频生成任务
- `generate_audio()`: 创建音频生成任务

#### 任务管理模块
- `TaskManager`: 任务管理器类
  - `create_task()`: 创建任务
  - `update_task()`: 更新任务状态
  - `get_task()`: 获取任务信息
  - `list_tasks()`: 列出任务

#### WebSocket模块
- `handle_connect()`: 处理客户端连接
- `handle_disconnect()`: 处理客户端断开
- `handle_join_task()`: 加入任务房间
- `handle_leave_task()`: 离开任务房间

### 2. 前端模块

#### 认证组件
- 登录表单
- 注册表单
- 会话管理

#### Excel编辑组件
- Handsontable表格
- 工作表切换
- 实时保存

#### 媒体生成组件
- 图片生成配置
- 视频生成配置
- 音频生成配置

#### 任务管理组件
- 任务列表
- 进度显示
- 状态更新

## 数据流

### Excel编辑流程

```
用户编辑表格
    ↓
前端发送更新请求 (POST /api/excel/write)
    ↓
服务器更新Excel文件
    ↓
服务器广播更新事件 (WebSocket)
    ↓
所有客户端接收更新并刷新
```

### 媒体生成流程

```
用户提交生成请求
    ↓
服务器创建任务 (POST /api/generate/*)
    ↓
后台线程执行生成任务
    ↓
任务状态更新 (WebSocket)
    ↓
客户端实时显示进度
    ↓
任务完成，显示结果
```

## 安全机制

### 认证
- 基于会话的认证
- Session ID存储在客户端localStorage
- 每个API请求需要Session ID

### 权限控制
- Admin角色：可以查看所有任务
- User角色：只能查看自己的任务

### 数据验证
- Excel写入前验证参数
- 任务创建前验证权限
- 输入数据清理和验证

## 文件结构

详见 [docs/系统说明.md](docs/系统说明.md) 中的「目录与文件结构」一节。概要：

```
UICS/
├── server.py              # FastAPI 主程序
├── requirements.txt       # Python 依赖
├── start.sh               # 启动脚本
├── lib/                   # 运行依赖（copy_deps 生成，单独部署用）
├── scripts/copy_deps.py   # 复制依赖到 lib
├── templates/index.html
├── static/css/, static/js/
├── uploads/               # 上传目录
├── output/                # 生成输出
├── docs/
│   ├── 安装与运行.md
│   └── 系统说明.md        # 功能与模块完整说明
└── README.md, QUICKSTART.md, DEPLOY.md, ARCHITECTURE.md
```

## API设计

### RESTful API

所有API遵循RESTful设计原则：

- `GET /api/*`: 获取资源
- `POST /api/*`: 创建资源
- `PUT /api/*`: 更新资源（未实现）
- `DELETE /api/*`: 删除资源（部分实现）

### WebSocket事件

#### 客户端 → 服务器
- `join_task`: 加入任务房间
- `leave_task`: 离开任务房间

#### 服务器 → 客户端
- `connected`: 连接成功
- `excel_updated`: Excel更新通知
- `task_update`: 任务状态更新

## 扩展性

### 添加新的生成器

1. 在`server.py`中导入生成器模块
2. 创建新的生成任务函数
3. 添加对应的API端点
4. 在前端添加配置界面

### 添加新的Excel工作表

系统自动支持Excel中的所有工作表，无需修改代码。

### 添加新的用户角色

1. 修改用户数据结构
2. 更新权限检查逻辑
3. 更新前端界面

## 性能优化建议

1. **数据库**: 使用数据库替代内存存储（用户、任务）
2. **任务队列**: 使用Celery处理长时间任务
3. **缓存**: 使用Redis缓存Excel数据
4. **CDN**: 静态文件使用CDN加速
5. **负载均衡**: 多实例部署时使用负载均衡

## 部署建议

安装与运行步骤见 [docs/安装与运行.md](docs/安装与运行.md)；单独拷贝部署见 [DEPLOY.md](DEPLOY.md)。

### 开发环境
```bash
cd UICS && python server.py
# 或: uvicorn server:app --host 0.0.0.0 --port 5000 --reload
```

### 生产环境
```bash
cd UICS
uvicorn server:app --host 0.0.0.0 --port 5000 --workers 1
```
（多 worker 时注意任务状态存储方式；当前为单进程内存任务列表。）

## 监控和日志

- 使用Python logging模块记录日志
- 建议集成日志收集系统（如ELK）
- 监控任务执行时间和成功率
- 监控API响应时间

## 未来改进

- [ ] 数据库集成（SQLite/PostgreSQL）
- [ ] Redis缓存支持
- [ ] Celery任务队列
- [ ] 文件上传功能
- [ ] 批量操作功能
- [ ] 数据导入/导出
- [ ] 操作日志记录
- [ ] 用户权限细化
- [ ] API文档（Swagger）
- [ ] 单元测试和集成测试

