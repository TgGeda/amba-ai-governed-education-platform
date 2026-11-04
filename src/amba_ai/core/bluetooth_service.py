# src/amba_ai/core/bluetooth_service.py
from __future__ import annotations

import asyncio
import platform
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Literal

from amba_ai.logger import logger


# ---------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------

BluetoothErrorType = Literal[
    "unavailable",
    "timeout",
    "backend_error",
    "connection_error",
    "cancelled",
]


@dataclass(frozen=True)
class BluetoothDevice:
    name: str
    address: str
    rssi: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BluetoothScanResult:
    devices: list[BluetoothDevice]
    duration: float
    error_type: BluetoothErrorType | None = None


@dataclass(frozen=True)
class BluetoothReachabilityResult:
    address: str
    reachable: bool
    latency_ms: float | None = None
    error_type: BluetoothErrorType | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class BluetoothUnavailableError(RuntimeError):
    """Raised when Bluetooth or bleak is unavailable."""


# ---------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------


class BluetoothService:
    """
    Cross-platform Bluetooth service using bleak.

    Guarantees:
    - Safe async + sync usage
    - Structured results (no raw booleans)
    - Graceful degradation when Bluetooth is unavailable
    """

    def __init__(self) -> None:
        self._bleak: Any | None = None
        self._platform = platform.system().lower()

        try:
            import bleak  # type: ignore

            self._bleak = bleak
        except Exception:
            self._bleak = None

        if self._bleak is None:
            logger.warning(
                "Bluetooth backend unavailable",
                extra={
                    "context": {
                        "operation": "init",
                        "platform": self._platform,
                        "reason": "bleak_not_installed",
                    }
                },
            )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        return self._bleak is not None

    def _check_available(self) -> None:
        if self._bleak is None:
            raise BluetoothUnavailableError(
                "Bluetooth is unavailable (bleak not installed or unsupported platform)."
            )

    # ------------------------------------------------------------------
    # Event loop helpers
    # ------------------------------------------------------------------

    def _run_async(self, coro):
        """
        Safely run async code from sync context.
        """
        try:
            return asyncio.run(coro)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                return loop.run_until_complete(coro)
            finally:
                loop.close()

    # ------------------------------------------------------------------
    # Scan
    # ------------------------------------------------------------------

    async def scan_async(
        self,
        *,
        timeout: float = 5.0,
        cancel_event: asyncio.Event | None = None,
    ) -> BluetoothScanResult:
        start = time.perf_counter()

        logger.info(
            "Bluetooth scan started",
            extra={
                "context": {
                    "operation": "scan_async",
                    "timeout": timeout,
                }
            },
        )

        if self._bleak is None:
            return BluetoothScanResult(
                devices=[],
                duration=0.0,
                error_type="unavailable",
            )

        try:
            if cancel_event and cancel_event.is_set():
                raise asyncio.CancelledError()

            devices = await asyncio.wait_for(
                self._bleak.BleakScanner.discover(timeout=timeout),
                timeout=timeout + 1,
            )

            result: list[BluetoothDevice] = []

            for d in devices:
                result.append(
                    BluetoothDevice(
                        name=d.name or "Unknown",
                        address=d.address,
                        rssi=getattr(d, "rssi", None),
                        metadata={
                            "manufacturer_data": getattr(d, "metadata", {}).get(
                                "manufacturer_data"
                            ),
                            "service_uuids": getattr(d, "metadata", {}).get(
                                "uuids"
                            ),
                        },
                    )
                )

            result.sort(key=lambda x: (x.name.lower(), x.address))

            duration = round(time.perf_counter() - start, 4)

            logger.info(
                "Bluetooth scan completed",
                extra={
                    "context": {
                        "operation": "scan_async",
                        "device_count": len(result),
                        "duration": duration,
                    }
                },
            )

            return BluetoothScanResult(
                devices=result,
                duration=duration,
            )

        except asyncio.TimeoutError:
            logger.warning(
                "Bluetooth scan timed out",
                extra={"context": {"operation": "scan_async"}},
            )
            return BluetoothScanResult(
                devices=[],
                duration=round(time.perf_counter() - start, 4),
                error_type="timeout",
            )

        except asyncio.CancelledError:
            logger.warning(
                "Bluetooth scan cancelled",
                extra={"context": {"operation": "scan_async"}},
            )
            return BluetoothScanResult(
                devices=[],
                duration=round(time.perf_counter() - start, 4),
                error_type="cancelled",
            )

        except Exception as exc:
            logger.exception(
                "Bluetooth scan failed",
                extra={
                    "context": {
                        "operation": "scan_async",
                        "error": str(exc),
                        "traceback": traceback.format_exc(),
                    }
                },
            )
            return BluetoothScanResult(
                devices=[],
                duration=round(time.perf_counter() - start, 4),
                error_type="backend_error",
            )

    def scan(self, *, timeout: float = 5.0) -> BluetoothScanResult:
        try:
            return self._run_async(self.scan_async(timeout=timeout))
        except BluetoothUnavailableError:
            return BluetoothScanResult(
                devices=[],
                duration=0.0,
                error_type="unavailable",
            )

    # ------------------------------------------------------------------
    # Reachability
    # ------------------------------------------------------------------

    async def is_reachable_async(
        self,
        address: str,
        *,
        timeout: float = 5.0,
        retries: int = 1,
    ) -> BluetoothReachabilityResult:
        start = time.perf_counter()

        if not address:
            return BluetoothReachabilityResult(
                address=address,
                reachable=False,
                error_type="validation_error",
            )

        if self._bleak is None:
            return BluetoothReachabilityResult(
                address=address,
                reachable=False,
                error_type="unavailable",
            )

        for attempt in range(1, retries + 2):
            try:
                attempt_start = time.perf_counter()

                async with self._bleak.BleakClient(
                    address,
                    timeout=timeout,
                ) as client:
                    reachable = bool(client.is_connected)

                latency_ms = round(
                    (time.perf_counter() - attempt_start) * 1000, 2
                )

                logger.info(
                    "Bluetooth reachability check completed",
                    extra={
                        "context": {
                            "operation": "is_reachable_async",
                            "address": address,
                            "reachable": reachable,
                            "latency_ms": latency_ms,
                        }
                    },
                )

                return BluetoothReachabilityResult(
                    address=address,
                    reachable=reachable,
                    latency_ms=latency_ms,
                )

            except Exception as exc:
                if attempt > retries:
                    logger.exception(
                        "Bluetooth reachability failed",
                        extra={
                            "context": {
                                "operation": "is_reachable_async",
                                "address": address,
                                "attempt": attempt,
                                "error": str(exc),
                                "traceback": traceback.format_exc(),
                            }
                        },
                    )
                    return BluetoothReachabilityResult(
                        address=address,
                        reachable=False,
                        error_type="connection_error",
                        metadata={
                            "attempts": attempt,
                        },
                    )

                await asyncio.sleep(0.3 * (2 ** (attempt - 1)))

        return BluetoothReachabilityResult(
            address=address,
            reachable=False,
            error_type="backend_error",
        )

    def is_reachable(
        self,
        address: str,
        *,
        timeout: float = 5.0,
        retries: int = 1,
    ) -> BluetoothReachabilityResult:
        try:
            return self._run_async(
                self.is_reachable_async(
                    address,
                    timeout=timeout,
                    retries=retries,
                )
            )
        except BluetoothUnavailableError:
            return BluetoothReachabilityResult(
                address=address,
                reachable=False,
                error_type="unavailable",
            )
