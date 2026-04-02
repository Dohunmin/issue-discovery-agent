"""실행 단위 로그 모듈.

매 실행(task)마다 logs/ 폴더에 별도 로그 파일을 생성한다.
파일명: logs/YYYY-MM-DD_HHMMSS.log
stdout과 파일에 동시에 기록한다.
"""

import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

KST = timedelta(hours=9)
LOGS_DIR = Path(__file__).parent.parent / "logs"


class TaskLogger:
    def __init__(self):
        LOGS_DIR.mkdir(exist_ok=True)
        now = datetime.now(timezone(KST))
        filename = now.strftime("%Y-%m-%d_%H%M%S") + ".log"
        self.log_path = LOGS_DIR / filename
        self._file = open(self.log_path, "w", encoding="utf-8")
        self._start_time = now
        self.log(f"=== Task started at {now.strftime('%Y-%m-%d %H:%M:%S KST')} ===")

    def log(self, message: str) -> None:
        print(message)
        self._file.write(message + "\n")
        self._file.flush()

    def close(self) -> None:
        now = datetime.now(timezone(KST))
        elapsed = (now - self._start_time).total_seconds()
        self.log(f"\n=== Task finished at {now.strftime('%Y-%m-%d %H:%M:%S KST')} (elapsed: {elapsed:.1f}s) ===")
        self._file.close()


# 모듈 레벨 싱글턴
_logger: TaskLogger | None = None


def init_logger() -> TaskLogger:
    global _logger
    _logger = TaskLogger()
    return _logger


def get_logger() -> TaskLogger:
    global _logger
    if _logger is None:
        _logger = TaskLogger()
    return _logger


def log(message: str) -> None:
    get_logger().log(message)
