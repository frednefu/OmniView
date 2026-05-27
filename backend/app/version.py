"""统一版本号管理 — 从 VERSION 文件读取。"""
import os


def get_version() -> str:
    """读取 VERSION 文件，返回版本号字符串（如 1.0.0）。"""
    # 优先从环境变量读取（允许运行时覆盖）
    env_version = os.environ.get("OMNIVIEW_VERSION", "").strip()
    if env_version:
        return env_version

    # 尝试多个路径：相对于本文件的 backend/VERSION，兼容不同部署方式
    candidates = [
        os.path.join(os.path.dirname(__file__), "..", "VERSION"),
        os.path.join(os.path.dirname(__file__), "..", "..", "VERSION"),
        "VERSION",
    ]
    for p in candidates:
        try:
            norm = os.path.normpath(os.path.abspath(p))
            with open(norm, "r", encoding="utf-8") as f:
                version = f.read().strip()
                if version:
                    return version
        except (FileNotFoundError, OSError):
            continue

    return "1.0.0"
