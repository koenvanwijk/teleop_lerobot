#!/usr/bin/env python3
"""Leader-only EPAOA motion source manager.

This is intentionally separate from TeleoperationManager, which owns a
leader+follower pair.  A MotionSourceManager owns only the source and streams
source-native values through a Motion Compatibility Profile into any target
adapter selected by that profile.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from lerobot.teleoperators.so_leader import SO101Leader, SO101LeaderConfig

from motion_compatibility import MotionCompatibilityRegistry


class MotionSourceManager:
    def __init__(self, profile_directory: Path | str):
        self.registry = MotionCompatibilityRegistry(profile_directory)
        self.source: Optional[SO101Leader] = None
        self.thread: Optional[threading.Thread] = None
        self.running = False
        self.profile_id: Optional[str] = None
        self.port: Optional[str] = None
        self.source_id: Optional[str] = None
        self.fps = 50
        self.actual_fps = 0.0
        self.last_error: Optional[str] = None
        self.latest_values: Dict[str, float] = {}
        self.latest_resolved: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._dispatch: Optional[Callable[[Dict[str, Any]], Any]] = None

    def start(
        self,
        *,
        port: str,
        source_id: str,
        profile_id: str,
        dispatch: Callable[[Dict[str, Any]], Any],
        fps: int = 50,
    ) -> None:
        if self.running:
            raise RuntimeError("motion source is already running")

        profile = self.registry.get(profile_id)
        if profile["source"]["input_schema_id"] != "teleopworks.so101.normalized-joints.v1":
            raise RuntimeError(
                f"profile {profile_id} does not accept the SO101 normalized source schema"
            )

        source = SO101Leader(
            SO101LeaderConfig(
                port=port,
                id=source_id,
                use_degrees=False,
            )
        )
        try:
            source.connect(calibrate=False)
            if not source.calibration:
                raise RuntimeError(f"SO101 leader {source_id} has no calibration")
            if not source.is_calibrated:
                raise RuntimeError(
                    f"SO101 leader {source_id} calibration does not match the connected hardware"
                )
        except BaseException:
            try:
                source.disconnect()
            except Exception:
                pass
            raise

        self.source = source
        self.profile_id = profile_id
        self.port = port
        self.source_id = source_id
        self.fps = max(1, min(int(fps), 100))
        self.actual_fps = 0.0
        self.last_error = None
        self._dispatch = dispatch
        self.running = True
        self.thread = threading.Thread(
            target=self._loop,
            name="epaoa-motion-source",
            daemon=True,
        )
        self.thread.start()

    def _loop(self) -> None:
        assert self.source is not None
        assert self.profile_id is not None
        assert self._dispatch is not None

        period = 1.0 / self.fps
        window_start = time.perf_counter()
        window_count = 0

        try:
            while self.running:
                started = time.perf_counter()
                raw_action = self.source.get_action()
                values = {
                    str(key).removesuffix(".pos"): float(value)
                    for key, value in raw_action.items()
                    if str(key).endswith(".pos")
                }

                resolved = self.registry.resolve(self.profile_id, values)
                self._dispatch(resolved)

                with self._lock:
                    self.latest_values = dict(values)
                    self.latest_resolved = {
                        "compatibility_id": resolved["compatibility_id"],
                        "profile_digest": resolved["profile_digest"],
                        "canonical_command": dict(resolved["canonical_command"]),
                        "target_native_command": dict(resolved["target_native_command"]),
                    }

                window_count += 1
                now = time.perf_counter()
                if now - window_start >= 1.0:
                    self.actual_fps = window_count / (now - window_start)
                    window_start = now
                    window_count = 0

                remaining = period - (time.perf_counter() - started)
                if remaining > 0:
                    time.sleep(remaining)
        except BaseException as exc:
            self.last_error = str(exc)
            logging.error("Leader-only motion source stopped: %s", exc, exc_info=True)
        finally:
            self.running = False

    def stop(self) -> None:
        self.running = False
        thread = self.thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        self.thread = None

        source = self.source
        self.source = None
        if source is not None:
            try:
                source.disconnect()
            except Exception as exc:
                logging.warning("Error disconnecting SO101 motion source: %s", exc)

    def status(self) -> Dict[str, Any]:
        with self._lock:
            values = dict(self.latest_values)
            resolved = dict(self.latest_resolved)
        return {
            "running": self.running,
            "profile_id": self.profile_id,
            "port": self.port,
            "source_id": self.source_id,
            "target_fps": self.fps,
            "actual_fps": round(self.actual_fps, 1),
            "last_error": self.last_error,
            "latest_values": values,
            "latest_resolved": resolved,
        }
