"""
配置模块
- active_config: 运行时配置单例，供各模块通过 `from config import active_config` 使用
"""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from config.config_loader import ProjectConfig


class _ActiveConfig:
    """运行时配置单例，在 main.py 启动时初始化一次"""

    def __init__(self):
        self._config: "ProjectConfig | None" = None

    def set(self, config: "ProjectConfig") -> None:
        self._config = config

    def get(self) -> "ProjectConfig":
        if self._config is None:
            raise RuntimeError(
                "配置未初始化，请先在 main.py 中调用 active_config.set(config)。"
            )
        return self._config


active_config = _ActiveConfig()
