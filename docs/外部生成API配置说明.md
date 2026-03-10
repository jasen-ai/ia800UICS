# UICS 外部生成 API 配置说明（非 ComfyUI）

本文档说明当 UICS 在**非 ComfyUI** 模式下生成媒体时，涉及到的外部 API 与配置方式。

- **图片生成**（`generator_type=nanobanana`）：Nano Banana
- **视频生成**（`generator_type=sora`）：Sora
- **音频生成**（`generator_type=volcengine`）：火山引擎 TTS（WebSocket）

> 安全提示：以下配置文件通常包含密钥/Token，请勿提交到代码仓库；建议放在 `~` 目录或通过部署流程注入。

---

## 一、图片生成（Nano Banana）

### 1.1 生效条件

- 前端「媒体生成 → 图片生成 → 生成器类型」选择 **Nano Banana**
- 或调用接口 `POST /api/generate/image`，请求体中：
  - `generator_type: "nanobanana"`

### 1.2 必填配置

- **API Key**（必填）
- **Host**（可选，有默认值）

### 1.3 配置文件位置（按优先级）

`UICS/lib/nanobanana_client.py` 的读取顺序：

1. 你在代码/调用处显式传入 `api_key` / `host`（优先级最高）
2. 指定的配置文件路径（如果调用方支持传入 `config_path`）
3. 默认候选路径（依次尝试）：
   - `UICS/lib/nanobanana_config.json`
   - `~/.nanobanana_config.json`
   - `./nanobanana_config.json`（当前工作目录）

### 1.4 配置文件格式示例（`nanobanana_config.json`）

```json
{
  "api_key": "YOUR_API_KEY",
  "host": "https://grsai.dakka.com.cn"
}
```

### 1.5 字段名兼容

`api_key` 支持以下键名之一（任意一个即可）：

- `api_key`, `apikey`, `apiKey`, `API_KEY`, `APIKEY`

### 1.6 说明

- Host 默认值为 `https://grsai.dakka.com.cn`
- Nano Banana 的生成参数（model/aspect_ratio/image_size 等）由代码默认值/调用方决定，详情可参考 `UICS/lib/image_generator.py` 与 `UICS/lib/nanobanana_client.py`。

---

## 二、视频生成（Sora）

### 2.1 生效条件

- 前端「媒体生成 → 视频生成 → 生成器类型」选择 **Sora**
- 或调用接口 `POST /api/generate/video`，请求体中：
  - `generator_type: "sora"`

### 2.2 必填配置

- **API Key**（必填）
- **Host**（可选，有默认值）

### 2.3 配置文件位置（按优先级）

`UICS/lib/sora_video_client.py` 的读取顺序：

1. 你在代码/调用处显式传入 `api_key` / `host`
2. 指定的配置文件路径（如果调用方传入 `sora_config_path`）
3. 默认候选路径（依次尝试）：
   - `UICS/lib/sora_video_config.json`
   - `~/.sora_video_config.json`
   - `./sora_video_config.json`（当前工作目录）

### 2.4 配置文件格式示例（`sora_video_config.json`）

```json
{
  "api_key": "YOUR_API_KEY",
  "host": "https://grsai.dakka.com.cn"
}
```

### 2.5 字段名兼容

`api_key` 支持以下键名之一（任意一个即可）：

- `api_key`, `apikey`, `apiKey`, `API_KEY`, `APIKEY`

### 2.6 Providers（可选，高级用法）

Sora 客户端还支持一个“供应商配置”文件（可选），用于定义不同 provider 的 endpoints、鉴权 header 格式等。

默认候选路径（依次尝试）：

- `UICS/lib/sora_video_providers.json`
- `~/.sora_video_providers.json`
- `./sora_video_providers.json`

如果没有该文件，会使用内置默认 provider（host `https://grsai.dakka.com.cn`）。

---

## 三、音频生成（火山引擎 Volcengine TTS）

### 3.1 生效条件

- 前端「媒体生成 → 音频生成 → 生成器类型」选择 **火山引擎**
- 或调用接口 `POST /api/generate/audio`，请求体中：
  - `generator_type: "volcengine"`

### 3.2 必填配置

- **appid**（必填）
- **access_token**（必填）
- **endpoint**（可选，有默认值）

默认 endpoint（代码默认）：

- `wss://openspeech.bytedance.com/api/v1/tts/ws_binary`

### 3.3 配置文件位置（按优先级）

`UICS/lib/audio_generator.py` 的读取顺序：

1. 你在调用时显式传入（优先级最高）：`appid` / `access_token` / `endpoint`
2. 接口请求体里的 `config_path`（若提供）指向的 JSON 文件
3. 默认候选路径（依次尝试）：
   - `UICS/lib/audio_generator_config.json`
   - `~/.audio_generator_config.json`
   - `./audio_generator_config.json`（当前工作目录）

### 3.4 配置文件格式示例（`audio_generator_config.json`）

```json
{
  "appid": "YOUR_APPID",
  "access_token": "YOUR_ACCESS_TOKEN",
  "endpoint": "wss://openspeech.bytedance.com/api/v1/tts/ws_binary"
}
```

### 3.5 字段名兼容（更宽松）

`appid` 兼容键名：

- `appid`, `app_id`, `APPID`, `APP_ID`

`access_token` 兼容键名：

- `access_token`, `accessToken`, `ACCESS_TOKEN`, `token`, `TOKEN`

`endpoint` 兼容键名：

- `endpoint`, `ENDPOINT`, `ws_endpoint`, `wsEndpoint`

---

## 四、接口传参覆盖规则（总结）

- **显式参数优先**：如果代码/接口传入了 key（如 appid、api_key），会覆盖配置文件中的值。
- **配置文件兜底**：未显式传入时才会读配置文件。
- **默认值最后**：host/endpoint 若仍缺失，会使用代码默认值。

---

## 五、快速自检

1. **确认生成器类型**：页面选择/接口参数是否为非 ComfyUI 模式（nanobanana/sora/volcengine）。
2. **确认密钥读取路径**：把配置文件放在上述默认候选路径之一，或在接口中传入对应 `config_path`。
3. **确认 host 可访问**：部署环境能访问配置的 host（网络、代理、TLS）。
4. **任务报错定位**：任务详情里的错误信息会包含“缺少 api_key/appid/access_token”等关键字时，优先检查配置文件是否被读取。

