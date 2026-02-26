"""缓存管理模块

基于 cachetools 实现的高效缓存系统
"""
import asyncio
from typing import Any, Optional, Dict
import cachetools
from loguru import logger


class CacheManager:
    """缓存管理器

    使用 cachetools.TTLCache 实现带过期时间的LRU缓存
    """

    def __init__(self, ttl: int = 300, maxsize: int = 1000, name: str = "cache"):
        """初始化缓存管理器

        Args:
            ttl: 缓存过期时间（秒）
            maxsize: 最大缓存条目数
            name: 缓存名称（用于日志）
        """
        self._cache = cachetools.TTLCache(maxsize=maxsize, ttl=ttl)
        self._hits = 0
        self._misses = 0
        self._name = name

    def get(self, key: str) -> Optional[Any]:
        """获取缓存值

        Args:
            key: 缓存键

        Returns:
            缓存值，如果不存在或已过期则返回 None
        """
        try:
            value = self._cache[key]
            self._hits += 1
            logger.debug(f"[{self._name}] 缓存命中: {key}")
            return value
        except KeyError:
            self._misses += 1
            logger.debug(f"[{self._name}] 缓存未命中: {key}")
            return None

    def set(self, key: str, value: Any) -> None:
        """设置缓存值

        Args:
            key: 缓存键
            value: 缓存值
        """
        self._cache[key] = value
        logger.debug(f"[{self._name}] 缓存设置: {key}")

    def delete(self, key: str) -> bool:
        """删除缓存值

        Args:
            key: 缓存键

        Returns:
            是否删除成功
        """
        try:
            del self._cache[key]
            logger.debug(f"[{self._name}] 缓存删除: {key}")
            return True
        except KeyError:
            return False

    def clear(self) -> None:
        """清空所有缓存"""
        size = len(self._cache)
        self._cache.clear()
        logger.info(f"[{self._name}] 缓存已清空: 删除 {size} 个条目")

    def stats(self) -> Dict[str, Any]:
        """获取缓存统计信息

        Returns:
            统计信息字典
        """
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0

        return {
            "name": self._name,
            "size": len(self._cache),
            "maxsize": self._cache.maxsize,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": f"{hit_rate:.2%}",
            "ttl": self._cache.ttl,
        }

    def size(self) -> int:
        """获取当前缓存大小"""
        return len(self._cache)


# 全局缓存实例
_access_token_cache: Optional[CacheManager] = None
_user_info_cache: Optional[CacheManager] = None
_dept_info_cache: Optional[CacheManager] = None


def init_cache(config):
    """初始化缓存系统

    Args:
        config: 配置对象，应包含 cache 属性
    """
    global _access_token_cache, _user_info_cache, _dept_info_cache

    # cache 是 Pydantic CacheConfig 对象，使用属性访问而非 .get()
    cache_config = getattr(config, 'cache', None)

    # 如果没有 cache 配置，使用默认值
    if cache_config is None:
        cache_config = type('CacheConfig', (), {
            'access_token_ttl': 7200,
            'access_token_max_size': 10,
            'user_info_ttl': 600,
            'user_info_max_size': 1000,
            'dept_info_ttl': 1800,
            'dept_info_max_size': 500,
            'enabled': True,
            'cleanup_interval': 300,
        })()

    # Access Token 缓存（默认2小时）
    _access_token_cache = CacheManager(
        ttl=cache_config.access_token_ttl,
        maxsize=cache_config.access_token_max_size,
        name="access_token"
    )

    # 用户信息缓存（默认10分钟）
    _user_info_cache = CacheManager(
        ttl=cache_config.user_info_ttl,
        maxsize=cache_config.user_info_max_size,
        name="user_info"
    )

    # 部门信息缓存（默认30分钟）
    _dept_info_cache = CacheManager(
        ttl=cache_config.dept_info_ttl,
        maxsize=cache_config.dept_info_max_size,
        name="dept_info"
    )

    logger.info("缓存系统初始化完成 (使用 cachetools)")
    logger.info(f"  - Access Token 缓存: TTL={_access_token_cache._cache.ttl}s, maxsize={_access_token_cache._cache.maxsize}")
    logger.info(f"  - 用户信息缓存: TTL={_user_info_cache._cache.ttl}s, maxsize={_user_info_cache._cache.maxsize}")
    logger.info(f"  - 部门信息缓存: TTL={_dept_info_cache._cache.ttl}s, maxsize={_dept_info_cache._cache.maxsize}")


def get_access_token_cache() -> CacheManager:
    """获取 Access Token 缓存实例"""
    global _access_token_cache
    if _access_token_cache is None:
        _access_token_cache = CacheManager(ttl=7200, maxsize=10, name="access_token")
    return _access_token_cache


def get_user_info_cache() -> CacheManager:
    """获取用户信息缓存实例"""
    global _user_info_cache
    if _user_info_cache is None:
        _user_info_cache = CacheManager(ttl=600, maxsize=1000, name="user_info")
    return _user_info_cache


def get_dept_info_cache() -> CacheManager:
    """获取部门信息缓存实例"""
    global _dept_info_cache
    if _dept_info_cache is None:
        _dept_info_cache = CacheManager(ttl=1800, maxsize=500, name="dept_info")
    return _dept_info_cache


def get_all_cache_stats() -> Dict[str, Any]:
    """获取所有缓存的统计信息"""
    return {
        "access_token": get_access_token_cache().stats(),
        "user_info": get_user_info_cache().stats(),
        "dept_info": get_dept_info_cache().stats(),
    }


def clear_all_cache() -> None:
    """清空所有缓存"""
    global _access_token_cache, _user_info_cache, _dept_info_cache

    if _access_token_cache:
        _access_token_cache.clear()
    if _user_info_cache:
        _user_info_cache.clear()
    if _dept_info_cache:
        _dept_info_cache.clear()

    logger.info("所有缓存已清空")


async def start_cache_cleanup_task(interval: int = 300):
    """启动缓存清理任务（定期打印统计信息）

    Args:
        interval: 清理间隔（秒）
    """
    while True:
        await asyncio.sleep(interval)

        # 打印缓存统计
        stats = get_all_cache_stats()
        logger.info("=" * 50)
        logger.info("缓存统计信息:")
        for cache_name, cache_stats in stats.items():
            logger.info(f"  [{cache_name}]")
            logger.info(f"    大小: {cache_stats['size']}/{cache_stats['maxsize']}")
            logger.info(f"    命中率: {cache_stats['hit_rate']}")
            logger.info(f"    命中/未命中: {cache_stats['hits']}/{cache_stats['misses']}")
            logger.info(f"    TTL: {cache_stats['ttl']}s")
        logger.info("=" * 50)
