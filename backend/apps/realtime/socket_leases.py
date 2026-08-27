import time
from typing import cast

import redis
from django.conf import settings


def _client() -> redis.Redis:
    return redis.Redis.from_url(settings.REALTIME_REDIS_URL, decode_responses=True)


def reserve_socket(user_id: int, connection_id: str) -> bool:
    now = int(time.time())
    expires = now + settings.REALTIME_SOCKET_LEASE_SECONDS
    script = _client().register_script(
        """
        redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ARGV[1])
        if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[3]) then
            return 0
        end
        redis.call('ZADD', KEYS[1], ARGV[2], ARGV[4])
        redis.call('EXPIRE', KEYS[1], ARGV[5])
        return 1
        """
    )
    result = script(
        keys=[f"realtime:sockets:user:{user_id}"],
        args=[
            now,
            expires,
            settings.REALTIME_MAX_SOCKETS_PER_USER,
            connection_id,
            settings.REALTIME_SOCKET_LEASE_SECONDS + 30,
        ],
    )
    return bool(result)


def release_socket(user_id: int, connection_id: str) -> None:
    _client().zrem(f"realtime:sockets:user:{user_id}", connection_id)


def active_socket_count(user_id: int) -> int:
    now = int(time.time())
    key = f"realtime:sockets:user:{user_id}"
    client = _client()
    client.zremrangebyscore(key, "-inf", now)
    return cast(int, client.zcard(key))


def total_active_socket_count() -> int:
    now = int(time.time())
    client = _client()
    total = 0
    for key in client.scan_iter(match="realtime:sockets:user:*", count=100):
        client.zremrangebyscore(key, "-inf", now)
        total += cast(int, client.zcard(key))
    return total


def touch_presence(user_id: int, connection_id: str) -> None:
    _client().set(f"realtime:presence:{user_id}:{connection_id}", "1", ex=70)


def remove_presence(user_id: int, connection_id: str) -> None:
    _client().delete(f"realtime:presence:{user_id}:{connection_id}")


def set_typing(user_id: int, conversation_id: str, connection_id: str, active: bool) -> None:
    key = f"realtime:typing:{conversation_id}:{user_id}:{connection_id}"
    if active:
        _client().set(key, "1", ex=5)
    else:
        _client().delete(key)
