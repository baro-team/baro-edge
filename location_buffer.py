"""
연결 끊김 구간의 telemetry 데이터를 보관하는 버퍼
재연결 시 vehicles/{id}/telemetry/buffered 토픽으로 일괄 전송
"""

from collections import deque
from config import BUFFER_MAX_SIZE


class LocationBuffer:

    def __init__(self, vehicle_id: str):
        self.vehicle_id = vehicle_id
        self._buffer = deque(maxlen=BUFFER_MAX_SIZE)

    def add(self, telemetry: dict):
        """연결 끊김 중 telemetry 버퍼에 적재"""
        self._buffer.append(telemetry)

    def flush(self) -> list:
        """버퍼 전체 반환 후 초기화"""
        data = list(self._buffer)
        self._buffer.clear()
        return data

    def is_empty(self) -> bool:
        return len(self._buffer) == 0

    def size(self) -> int:
        return len(self._buffer)
