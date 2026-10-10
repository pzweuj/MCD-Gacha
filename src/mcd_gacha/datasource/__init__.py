"""数据源包：mock（内置快照）与 mcp（真实麦当劳 MCP）双实现。"""

from .base import MenuDataSource, OrderNotSupportedError
from .mock import MockDataSource

__all__ = [
    "MenuDataSource",
    "MockDataSource",
    "OrderNotSupportedError",
    "create_datasource",
]


def create_datasource(mode: str = "mock", **kwargs):
    """工厂：按模式创建数据源（"mcp" 实现为懒加载，避免 mock 用户安装 mcp 依赖）。"""
    if mode == "mcp":
        from .mcp import McpDataSource

        return McpDataSource(**kwargs)
    return MockDataSource(**kwargs)
