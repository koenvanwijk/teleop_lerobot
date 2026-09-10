#!/usr/bin/env python3
"""Reachy Mini target adapter for EPAOA Motion Compatibility.

The adapter consumes a target-native expressive-head command produced by a
Motion Compatibility Profile and drives the official Reachy Mini SDK.

The same adapter works against:
- a local Reachy Mini Lite daemon,
- a local Reachy Mini MuJoCo daemon,
- a network Reachy Mini Wireless daemon.
"""

from __future__ import annotations

import os
import threading
from typing import Any, Mapping


class ReachyMiniTargetError(RuntimeError):
    pass


_REQUIRED = (
    "head_yaw",
    "head_pitch",
    "head_roll",
    "head_z",
    "right_antenna",
    "left_antenna",
)


def build_reachy_target(values: Mapping[str, Any]) -> dict[str, Any]:
    """Validate/normalize the profile output without importing reachy-mini."""

    missing = [name for name in _REQUIRED if name not in values]
    if missing:
        raise ReachyMiniTargetError(
            "missing Reachy Mini target fields: " + ", ".join(missing)
        )

    numeric = {}
    for name in _REQUIRED:
        try:
            numeric[name] = float(values[name])
        except (TypeError, ValueError) as exc:
            raise ReachyMiniTargetError(f"{name} must be numeric") from exc

    return {
        "head": {
            "x_m": 0.0,
            "y_m": 0.0,
            "z_m": numeric["head_z"],
            "roll_rad": numeric["head_roll"],
            "pitch_rad": numeric["head_pitch"],
            "yaw_rad": numeric["head_yaw"],
        },
        # Reachy Mini SDK order is [right, left].
        "antennas_rad": [
            numeric["right_antenna"],
            numeric["left_antenna"],
        ],
    }


class ReachyMiniTargetAdapter:
    """Lazy, thread-safe connection to the official Reachy Mini SDK."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._mini = None

    @property
    def connected(self) -> bool:
        return self._mini is not None

    def _connect(self):
        if self._mini is not None:
            return self._mini

        try:
            from reachy_mini import ReachyMini
        except ImportError as exc:
            raise ReachyMiniTargetError(
                "reachy-mini is not installed; run: pip install reachy-mini"
            ) from exc

        host = os.getenv("REACHY_MINI_HOST", "localhost")
        port = int(os.getenv("REACHY_MINI_PORT", "8000"))
        mode = os.getenv(
            "REACHY_MINI_CONNECTION_MODE",
            "localhost_only" if host in {"localhost", "127.0.0.1"} else "network",
        )

        self._mini = ReachyMini(
            host=host,
            port=port,
            connection_mode=mode,
            media_backend="no_media",
            automatic_body_yaw=False,
        )
        return self._mini

    def apply(self, values: Mapping[str, Any]) -> dict[str, Any]:
        target = build_reachy_target(values)

        try:
            from reachy_mini.utils import create_head_pose
        except ImportError as exc:
            raise ReachyMiniTargetError(
                "reachy-mini is not installed; run: pip install reachy-mini"
            ) from exc

        head = target["head"]
        pose = create_head_pose(
            x=head["x_m"],
            y=head["y_m"],
            z=head["z_m"],
            roll=head["roll_rad"],
            pitch=head["pitch_rad"],
            yaw=head["yaw_rad"],
            degrees=False,
            mm=False,
        )

        with self._lock:
            mini = self._connect()
            mini.set_target(
                head=pose,
                antennas=target["antennas_rad"],
            )

        return target

    def close(self) -> None:
        with self._lock:
            mini = self._mini
            self._mini = None
            if mini is None:
                return
            try:
                mini.__exit__(None, None, None)
            except Exception:
                client = getattr(mini, "client", None)
                if client is not None and hasattr(client, "disconnect"):
                    client.disconnect()
