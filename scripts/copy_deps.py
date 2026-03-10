#!/usr/bin/env python3
"""
将 UICS 运行所需的依赖从项目根目录复制到 UICS/lib/，
便于将 UICS 目录整体移动部署到其他机器。
运行方式：在项目根目录执行 python UICS/scripts/copy_deps.py
或在 UICS 目录执行 python scripts/copy_deps.py
"""
import os
import shutil

# 项目根目录（050tool）
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
UICS_DIR = os.path.dirname(SCRIPT_DIR)
PROJECT_ROOT = os.path.dirname(UICS_DIR)

# 目标：UICS/lib/
LIB_DIR = os.path.join(UICS_DIR, "lib")

# 需要复制的 .py 模块（与 server / excel_reader 的导入链一致）
PY_DEPS = [
    "excel_reader.py",
    "image_generator.py",
    "video_generator.py",
    "audio_generator.py",
    "comfyui_client.py",
    "z_image_client.py",
    "nanobanana_client.py",
    "qwen3_tts_client.py",
    "sora_video_client.py",
]

# 需要复制的工作流/配置 JSON（与 video_generator / image_generator / qwen3 使用的一致）
JSON_DEPS = [
    "act_video_wan2_2_14B_i2v-aigc-api.json",
    "act_video_wan2_2_14B_i2vse-aigc-api.json",
    "act_video_wan2_2_14B_s2v-aigc-api.json",
    "act_02_qwen_Image_edit-aigc-3-api.json",
    "z_image_workflow.json",
    "Qwen3-TTSVoiceCloneAPI.json",
]


def main():
    os.makedirs(LIB_DIR, exist_ok=True)
    copied = []
    for name in PY_DEPS + JSON_DEPS:
        src = os.path.join(PROJECT_ROOT, name)
        dst = os.path.join(LIB_DIR, name)
        if os.path.isfile(src):
            shutil.copy2(src, dst)
            copied.append(name)
            print(f"  已复制: {name}")
        else:
            print(f"  跳过(不存在): {name}")
    print(f"\n共复制 {len(copied)} 个文件到 {LIB_DIR}")
    print("UICS 可单独部署：将整个 UICS 目录拷贝到目标机器后，从 UICS 目录运行 server 即可。")


if __name__ == "__main__":
    main()
