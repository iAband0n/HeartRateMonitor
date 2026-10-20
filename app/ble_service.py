"""BLE heart-rate service.

A single background asyncio loop owns all Bleak clients, so several watches
can be connected and monitored at the same time without blocking the UI.
Standard Heart Rate Service (0x180D / 0x2A37) notifications are parsed
according to the Bluetooth SIG specification.
"""

from __future__ import annotations

import asyncio
import logging
import random
import threading
import time
from dataclasses import dataclass, field

from PySide6.QtCore import QObject, QTimer, Signal

log = logging.getLogger(__name__)

HR_SERVICE_UUID = "0000180d-0000-1000-8000-00805f9b34fb"
HR_MEASUREMENT_UUID = "00002a37-0000-1000-8000-00805f9b34fb"
BATTERY_SERVICE_UUID = "0000180f-0000-1000-8000-00805f9b34fb"
BATTERY_LEVEL_UUID = "00002a19-0000-1000-8000-00805f9b34fb"

STATE_CONNECTING = "connecting"
STATE_CONNECTED = "connected"
STATE_DISCONNECTED = "disconnected"
STATE_RECONNECTING = "reconnecting"
STATE_ERROR = "error"


@dataclass
class DiscoveredDevice:
    address: str
    name: str
    rssi: int | None = None
    has_heart_rate: bool = False
    service_uuids: list[str] = field(default_factory=list)
    manufacturer: str = ""

    @property
    def key(self) -> str:
        return self.address.upper() if self.address else f"name:{self.name}"


def normalize_uuid(value: object) -> str:
    text = str(value or "").strip().lower()
    if text.startswith("{") and text.endswith("}"):
        text = text[1:-1]
    return text


def parse_heart_rate(data: bytes) -> tuple[int, int | None, int | None]:
    """Return (bpm, sensor_contact, first_rr_ms) for a 0x2A37 notification."""
    if not data:
        raise ValueError("empty heart-rate packet")
    flags = data[0]
    offset = 1
    is_u16 = bool(flags & 0x01)
    if is_u16:
        if len(data) < 3:
            raise ValueError("truncated uint16 heart rate")
        bpm = data[1] | (data[2] << 8)
        offset = 3
    else:
        if len(data) < 2:
            raise ValueError("truncated uint8 heart rate")
        bpm = data[1]
        offset = 2
    contact: int | None = (flags >> 1) & 0x03
    # Energy expended (bit 3) is a uint16.
    if flags & 0x08:
        offset += 2
    first_rr: int | None = None
    if flags & 0x10 and len(data) >= offset + 2:
        first_rr = data[offset] | (data[offset + 1] << 8)
    return int(bpm), contact, first_rr


class BleService(QObject):
    """Threaded BLE backend emitting Qt signals to the UI thread."""

    scan_started = Signal()
    scan_progress = Signal(object)  # DiscoveredDevice
    scan_finished = Signal(object)  # list[DiscoveredDevice]
    scan_error = Signal(str)
    connection_state = Signal(str, str, str)  # key, state, message
    heart_rate = Signal(str, int, float, object)  # key, bpm, timestamp, extra
    battery = Signal(str, int)
    log = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.is_demo = False
        self._thread = threading.Thread(target=self._run_loop, name="ble-loop", daemon=True)
        self._ready = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._clients: dict[str, object] = {}
        self._desired: dict[str, tuple[str, str, bool]] = {}
        self._manual_disconnect: set[str] = set()
        self._reconnect_tasks: dict[str, asyncio.Task] = {}
        self._connect_tasks: dict[str, asyncio.Task] = {}
        self._battery_tasks: dict[str, asyncio.Task] = {}
        self._closing = False
        self._scanning = False
        self._scan_stop = threading.Event()
        self._started = False

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._thread.start()
        self._ready.wait(timeout=2.0)

    def shutdown(self) -> None:
        self._closing = True
        self._scan_stop.set()
        loop = self._loop
        if loop is not None and loop.is_running():
            try:
                future = asyncio.run_coroutine_threadsafe(self._shutdown_coro(), loop)
                future.result(timeout=4.0)
            except Exception:
                log.debug("BLE shutdown coroutine did not finish cleanly", exc_info=True)
            loop.call_soon_threadsafe(loop.stop)
        if self._thread.is_alive():
            self._thread.join(timeout=3.0)

    def _run_loop(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        self._ready.set()
        try:
            loop.run_forever()
        finally:
            pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
            for task in pending:
                task.cancel()
            if pending:
                try:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                except Exception:
                    pass
            loop.close()
            log.info("BLE loop stopped")

    async def _shutdown_coro(self) -> None:
        for key, task in list(self._reconnect_tasks.items()):
            task.cancel()
        for key, task in list(self._connect_tasks.items()):
            task.cancel()
        for key, task in list(self._battery_tasks.items()):
            task.cancel()
        clients = list(self._clients.items())
        for key, client in clients:
            try:
                await asyncio.wait_for(client.disconnect(), timeout=1.2)
            except Exception:
                pass
            self.connection_state.emit(key, STATE_DISCONNECTED, "程序退出")
        self._clients.clear()

    def _submit(self, coro) -> None:
        loop = self._loop
        if loop is None or not loop.is_running():
            log.warning("BLE loop is not running; dropping request")
            try:
                coro.close()
            except Exception:
                pass
            return
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        future.add_done_callback(self._on_future_done)

    @staticmethod
    def _on_future_done(future) -> None:
        try:
            future.result()
        except asyncio.CancelledError:
            pass
        except Exception:
            log.exception("BLE background task failed")

    # -- scanning ----------------------------------------------------------
    def scan(self, duration: float = 10.0) -> None:
        if self._scanning:
            return
        self._scan_stop.clear()
        self._submit(self._scan_coro(max(3.0, float(duration))))

    def stop_scan(self) -> None:
        self._scan_stop.set()

    async def _scan_coro(self, duration: float) -> None:
        if self._closing:
            return
        self._scanning = True
        self.scan_started.emit()
        scanner = None
        found: dict[str, DiscoveredDevice] = {}
        try:
            from bleak import BleakScanner

            def callback(device, advertisement_data) -> None:
                try:
                    address = str(getattr(device, "address", "") or "").strip()
                    if not address:
                        return
                    address_key = address.upper()
                    name = (
                        getattr(device, "name", None)
                        or getattr(advertisement_data, "local_name", None)
                        or ""
                    )
                    uuids = [
                        normalize_uuid(u)
                        for u in (getattr(advertisement_data, "service_uuids", None) or [])
                    ]
                    has_hr = HR_SERVICE_UUID in uuids
                    rssi = getattr(advertisement_data, "rssi", None)
                    previous = found.get(address_key)
                    info = DiscoveredDevice(
                        address=address,
                        name=name or (previous.name if previous else ""),
                        rssi=int(rssi) if rssi is not None else None,
                        has_heart_rate=has_hr or (previous.has_heart_rate if previous else False),
                        service_uuids=uuids or (previous.service_uuids if previous else []),
                    )
                    if (
                        previous is None
                        or previous.name != info.name
                        or previous.rssi != info.rssi
                        or previous.has_heart_rate != info.has_heart_rate
                    ):
                        found[address_key] = info
                        self.scan_progress.emit(info)
                except Exception:
                    log.debug("Scan callback failed", exc_info=True)

            self.log.emit("正在扫描附近的蓝牙设备…")
            scanner = BleakScanner(detection_callback=callback)
            await scanner.start()
            deadline = time.monotonic() + duration
            while time.monotonic() < deadline and not self._scan_stop.is_set():
                await asyncio.sleep(0.2)
            await scanner.stop()
            scanner = None
            self.scan_finished.emit(list(found.values()))
            self.log.emit(f"扫描完成，发现 {len(found)} 个蓝牙设备")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.exception("BLE scan failed")
            self.scan_error.emit(self._friendly_ble_error(exc))
        finally:
            if scanner is not None:
                try:
                    await scanner.stop()
                except Exception:
                    pass
            self._scanning = False

    # -- connections -------------------------------------------------------
    def connect_device(
        self, key: str, address: str, name: str = "", auto_reconnect: bool = True
    ) -> None:
        if not address:
            self.connection_state.emit(key, STATE_ERROR, "设备地址为空，无法连接")
            return
        self._manual_disconnect.discard(key)
        self._desired[key] = (address, name, bool(auto_reconnect))
        self._submit(self._connect_coro(key, address, name, attempt=0))

    async def _connect_coro(self, key: str, address: str, name: str, attempt: int = 0) -> None:
        if self._closing:
            return
        if key in self._clients:
            return
        existing_task = self._connect_tasks.get(key)
        current = asyncio.current_task()
        if existing_task is not None and existing_task is not current and not existing_task.done():
            return
        task = current
        if task is not None:
            self._connect_tasks[key] = task
        self.connection_state.emit(key, STATE_CONNECTING, "正在连接…")
        self.log.emit(f"正在连接 {name or address} ({address})…")
        try:
            from bleak import BleakClient

            def disconnected_callback(client) -> None:
                self._loop_soon(self._handle_disconnected, key, client)

            client = BleakClient(address, disconnected_callback=disconnected_callback, timeout=20.0)
            await client.connect()
            if self._closing or key not in self._desired:
                await client.disconnect()
                return
            self._clients[key] = client
            services = client.services
            if not services:
                try:
                    services = await client.get_services()
                except AttributeError:
                    pass
            hr_char = self._find_hr_characteristic(services)
            if hr_char is None:
                raise RuntimeError("该设备没有提供标准心率服务 (0x180D)，请确认设备已开启心率广播")
            await asyncio.wait_for(client.start_notify(hr_char, self._make_hr_callback(key)), timeout=10.0)
            self.connection_state.emit(key, STATE_CONNECTED, "已连接 · 正在接收心率")
            self.log.emit(f"已连接 {name or address}，心率通知已开启")
            self._battery_tasks[key] = asyncio.create_task(self._battery_loop(key, client))
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.exception("Could not connect to %s", address)
            message = self._friendly_ble_error(exc)
            self.connection_state.emit(key, STATE_ERROR, message)
            self.log.emit(f"连接 {name or address} 失败：{message}")
            client = self._clients.pop(key, None)
            if client is not None:
                try:
                    await client.disconnect()
                except Exception:
                    pass
            if key in self._desired and self._desired[key][2] and not self._closing:
                self._schedule_reconnect(key, attempt + 1)
        finally:
            if self._connect_tasks.get(key) is asyncio.current_task():
                self._connect_tasks.pop(key, None)

    def _find_hr_characteristic(self, services):
        try:
            service_list = list(services)
        except Exception:
            service_list = []
        for service in service_list:
            if normalize_uuid(getattr(service, "uuid", "")) == HR_SERVICE_UUID:
                for char in getattr(service, "characteristics", []):
                    if normalize_uuid(getattr(char, "uuid", "")) == HR_MEASUREMENT_UUID:
                        return char
        for service in service_list:
            for char in getattr(service, "characteristics", []):
                if normalize_uuid(getattr(char, "uuid", "")) == HR_MEASUREMENT_UUID:
                    return char
        return None

    def _make_hr_callback(self, key: str):
        def callback(characteristic, data) -> None:
            try:
                bpm, contact, rr = parse_heart_rate(bytes(data))
                if 20 <= bpm <= 300:
                    extra = {"contact": contact, "rr": rr}
                    self.heart_rate.emit(key, bpm, time.time(), extra)
            except Exception:
                log.debug("Could not parse HR packet: %s", bytes(data).hex(), exc_info=True)

        return callback

    async def _battery_loop(self, key: str, client) -> None:
        while not self._closing:
            try:
                battery_char = None
                for service in client.services:
                    if normalize_uuid(getattr(service, "uuid", "")) == BATTERY_SERVICE_UUID:
                        for char in getattr(service, "characteristics", []):
                            if normalize_uuid(getattr(char, "uuid", "")) == BATTERY_LEVEL_UUID:
                                battery_char = char
                                break
                if battery_char is not None:
                    data = await client.read_gatt_char(battery_char)
                    if data:
                        self.battery.emit(key, int(data[0]))
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
            await asyncio.sleep(120)

    def disconnect_device(self, key: str) -> None:
        self._manual_disconnect.add(key)
        self._desired.pop(key, None)
        task = self._reconnect_tasks.pop(key, None)
        if task is not None:
            task.cancel()
        self._submit(self._disconnect_coro(key))

    async def _disconnect_coro(self, key: str) -> None:
        client = self._clients.pop(key, None)
        battery_task = self._battery_tasks.pop(key, None)
        if battery_task is not None:
            battery_task.cancel()
        if client is not None:
            try:
                await asyncio.wait_for(client.disconnect(), timeout=3.0)
            except Exception:
                pass
        self.connection_state.emit(key, STATE_DISCONNECTED, "已断开连接")

    def _loop_soon(self, callback, *args) -> None:
        loop = self._loop
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(callback, *args)

    def _handle_disconnected(self, key: str, client) -> None:
        if self._closing:
            return
        # A late callback from an old client must not tear down the new client
        # created by an automatic reconnect.
        if self._clients.get(key) is not client:
            return
        self._clients.pop(key, None)
        battery_task = self._battery_tasks.pop(key, None)
        if battery_task is not None:
            battery_task.cancel()
        if client is None:
            return
        self.connection_state.emit(key, STATE_DISCONNECTED, "设备连接已断开")
        self.log.emit("设备连接已断开")
        if key in self._desired and key not in self._manual_disconnect:
            self._schedule_reconnect(key, 1)

    def _schedule_reconnect(self, key: str, attempt: int) -> None:
        if key in self._reconnect_tasks:
            return
        self._reconnect_tasks[key] = asyncio.create_task(self._reconnect_loop(key, attempt))

    async def _reconnect_loop(self, key: str, attempt: int) -> None:
        try:
            while not self._closing and key in self._desired and key not in self._manual_disconnect:
                if attempt > 8:
                    self.connection_state.emit(key, STATE_ERROR, "自动重连失败，请手动重新连接")
                    return
                delay = min(30.0, 2.0 * attempt)
                self.connection_state.emit(
                    key, STATE_RECONNECTING, f"{int(delay)} 秒后重连（第 {attempt} 次）"
                )
                await asyncio.sleep(delay)
                if key not in self._desired:
                    return
                address, name, auto = self._desired[key]
                await self._connect_coro(key, address, name, attempt=attempt)
                if key in self._clients:
                    return
                attempt += 1
        except asyncio.CancelledError:
            raise
        finally:
            self._reconnect_tasks.pop(key, None)

    def _parse_and_emit(self, key: str, data: bytes) -> None:
        try:
            bpm, contact, rr = parse_heart_rate(data)
            self.heart_rate.emit(key, bpm, time.time(), {"contact": contact, "rr": rr})
        except Exception:
            pass

    @staticmethod
    def _friendly_ble_error(exc: Exception) -> str:
        text = str(exc) or exc.__class__.__name__
        lowered = text.lower()
        if "bluetooth" in lowered and ("off" in lowered or "disabled" in lowered):
            return "蓝牙未开启，请在系统设置中打开蓝牙"
        if "not found" in lowered:
            return "未找到设备，请确认设备已开机且在附近"
        if "access is denied" in lowered or "denied" in lowered:
            return "蓝牙访问被拒绝，请检查系统蓝牙权限"
        if "timeout" in lowered or "timed out" in lowered:
            return "连接超时，请靠近设备后重试"
        return text[:180]


class DemoBleService(QObject):
    """Canned BLE source used by --demo and by the screenshot tool."""

    scan_started = Signal()
    scan_progress = Signal(object)
    scan_finished = Signal(object)
    scan_error = Signal(str)
    connection_state = Signal(str, str, str)
    heart_rate = Signal(str, int, float, object)
    battery = Signal(str, int)
    log = Signal(str)

    DEMO_DEVICES = [
        DiscoveredDevice("C8:47:8D:12:34:56", "Mi Band 8", -48, True, [HR_SERVICE_UUID]),
        DiscoveredDevice("A0:9E:1A:22:33:44", "Polar H10", -61, True, [HR_SERVICE_UUID]),
        DiscoveredDevice("F4:12:FA:99:88:77", "HUAWEI WATCH GT", -72, True, [HR_SERVICE_UUID]),
        DiscoveredDevice("7C:9E:BD:55:66:77", "WH-1000XM5", -66, False, []),
    ]

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.is_demo = True
        self._scan_timer = QTimer(self)
        self._scan_timer.setSingleShot(True)
        self._scan_timer.timeout.connect(self._finish_scan)
        self._scan_index = 0
        self._scan_step = QTimer(self)
        self._scan_step.timeout.connect(self._emit_next_device)
        self._connections: dict[str, dict] = {}
        self._closed = False

    def start(self) -> None:
        pass

    def shutdown(self) -> None:
        self._closed = True
        self._scan_timer.stop()
        self._scan_step.stop()
        for state in self._connections.values():
            timer = state.get("timer")
            if timer is not None:
                timer.stop()
        self._connections.clear()

    def scan(self, duration: float = 10.0) -> None:
        if self._scan_step.isActive():
            return
        self.scan_started.emit()
        self.log.emit("演示模式：正在扫描附近的蓝牙设备…")
        self._scan_index = 0
        self._scan_step.start(260)
        self._scan_timer.start(int(max(2.0, min(duration, 8.0)) * 1000))

    def stop_scan(self) -> None:
        self._scan_step.stop()
        self._scan_timer.stop()
        self._finish_scan()

    def _emit_next_device(self) -> None:
        if self._scan_index >= len(self.DEMO_DEVICES):
            self._scan_step.stop()
            return
        self.scan_progress.emit(self.DEMO_DEVICES[self._scan_index])
        self._scan_index += 1

    def _finish_scan(self) -> None:
        self._scan_step.stop()
        self._scan_timer.stop()
        self.scan_finished.emit(list(self.DEMO_DEVICES))

    def connect_device(self, key: str, address: str, name: str = "", auto_reconnect: bool = True) -> None:
        if key in self._connections:
            return
        self.connection_state.emit(key, STATE_CONNECTING, "正在连接…")
        self.log.emit(f"演示模式：正在连接 {name or address}…")

        def connected() -> None:
            if self._closed or key not in self._connections:
                return
            self.connection_state.emit(key, STATE_CONNECTED, "已连接 · 正在接收心率")
            self.battery.emit(key, 78 if "Mi Band" in name else 92)
            timer = QTimer(self)
            timer.setInterval(1000)
            timer.timeout.connect(lambda: self._emit_hr(key))
            timer.start()
            self._connections[key]["timer"] = timer
            self.log.emit(f"演示模式：{name or address} 已连接")

        self._connections[key] = {"timer": None, "started": time.time()}
        QTimer.singleShot(650, connected)

    def _emit_hr(self, key: str) -> None:
        state = self._connections.get(key)
        if not state:
            return
        elapsed = time.time() - state["started"]
        # Slow warm-up, a little variability, with a workout bump after 40s.
        base = 72 if "Mi Band" in key else 78
        if "Polar" in key or "A0:9E" in key:
            base = 88
        if "F4:12" in key:
            base = 66
        drift = 7 * __import__("math").sin(elapsed / 13.0)
        workout = 18 if elapsed > 40 else 0
        bpm = int(base + drift + workout + random.uniform(-2.5, 2.5))
        self.heart_rate.emit(key, bpm, time.time(), {"contact": 2, "rr": None})

    def disconnect_device(self, key: str) -> None:
        state = self._connections.pop(key, None)
        if state and state.get("timer") is not None:
            state["timer"].stop()
        self.connection_state.emit(key, STATE_DISCONNECTED, "已断开连接")

    def _parse_and_emit(self, key: str, data: bytes) -> None:
        pass


def create_ble_service(demo: bool = False, parent: QObject | None = None):
    return DemoBleService(parent) if demo else BleService(parent)
