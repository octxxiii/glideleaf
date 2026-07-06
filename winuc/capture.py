"""Windows のグローバル入力キャプチャ。

方式 (PowerToys Mouse Without Borders / deskflow と同系だが、
移動量の取得に Raw Input を使う点が異なる):

- WH_MOUSE_LL / WH_KEYBOARD_LL 低レベルフック:
    キャプチャ中はイベントを飲み込み (return 1)、ローカルアプリに渡さない。
    ボタン・ホイール・キーはここから取得する。
- Raw Input (WM_INPUT, RIDEV_INPUTSINK):
    フックが飲み込んでいても加速前の相対移動量 (デバイスカウント) が届く。
    突き抜け量の計測と iPad へ転送する移動量はこちらを使う。
    (iPad 側が独自のポインタ加速を掛けるため、非加速の生デルタを送るのが正しい)
- カーソルのピン留め/隠蔽は ClipCursor(1x1) で行う。

フックコールバックは LowLevelHooksTimeout (最大 1000ms) を超えると
Windows に黙って外されるため、コールバック内の処理は最小限に保つこと。
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import logging
import threading
import time
from typing import Callable

from .edge import EdgeStateMachine, PushResult, State

logger = logging.getLogger(__name__)

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# --- Win32 定数 ---
WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14

WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_MBUTTONDOWN = 0x0207
WM_MBUTTONUP = 0x0208
WM_MOUSEWHEEL = 0x020A
WM_XBUTTONDOWN = 0x020B
WM_XBUTTONUP = 0x020C
WM_MOUSEHWHEEL = 0x020E
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_INPUT = 0x00FF
WM_QUIT = 0x0012
WM_DISPLAYCHANGE = 0x007E

LLMHF_INJECTED = 0x00000001
LLKHF_INJECTED = 0x00000010
LLKHF_UP = 0x00000080
LLKHF_EXTENDED = 0x00000001

RIDEV_INPUTSINK = 0x00000100
RIM_TYPEMOUSE = 0
RID_INPUT = 0x10000003
MOUSE_MOVE_ABSOLUTE = 0x0001

KEYEVENTF_KEYUP = 0x0002
INPUT_KEYBOARD = 1

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

ULONG_PTR = ctypes.c_size_t
LRESULT = ctypes.c_ssize_t

_MOUSE_BUTTON_MESSAGES = {
    WM_LBUTTONDOWN: (0, True),
    WM_LBUTTONUP: (0, False),
    WM_RBUTTONDOWN: (1, True),
    WM_RBUTTONUP: (1, False),
    WM_MBUTTONDOWN: (2, True),
    WM_MBUTTONUP: (2, False),
}

BUTTON_NAMES = {"left": 0, "right": 1, "middle": 2, "x1": 3, "x2": 4}

# 自分が SendInput したイベントの目印 (dwExtraInfo)
MAGIC_EXTRA_INFO = 0x57696E55  # "WinU"

_MODIFIER_VKS = {
    0xA0, 0xA1,  # L/R Shift
    0xA2, 0xA3,  # L/R Ctrl
    0xA4, 0xA5,  # L/R Alt
    0x5B, 0x5C,  # L/R Win
}


# --- 構造体 ---
class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", wt.POINT),
        ("mouseData", wt.DWORD),
        ("flags", wt.DWORD),
        ("time", wt.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wt.DWORD),
        ("scanCode", wt.DWORD),
        ("flags", wt.DWORD),
        ("time", wt.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [
        ("dwType", wt.DWORD),
        ("dwSize", wt.DWORD),
        ("hDevice", wt.HANDLE),
        ("wParam", wt.WPARAM),
    ]


class RAWMOUSE(ctypes.Structure):
    _fields_ = [
        ("usFlags", wt.USHORT),
        ("usButtonFlags", wt.USHORT),
        ("usButtonData", wt.USHORT),
        ("ulRawButtons", wt.ULONG),
        ("lLastX", wt.LONG),
        ("lLastY", wt.LONG),
        ("ulExtraInformation", wt.ULONG),
    ]


class RAWINPUT(ctypes.Structure):
    _fields_ = [("header", RAWINPUTHEADER), ("mouse", RAWMOUSE)]


class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [
        ("usUsagePage", wt.USHORT),
        ("usUsage", wt.USHORT),
        ("dwFlags", wt.DWORD),
        ("hwndTarget", wt.HWND),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wt.WORD),
        ("wScan", wt.WORD),
        ("dwFlags", wt.DWORD),
        ("time", wt.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("padding", ctypes.c_byte * 32)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wt.DWORD), ("union", _INPUT_UNION)]


HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wt.WPARAM, wt.LPARAM)
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)

# 64bit 環境でポインタ/ハンドルが 32bit int に切り詰められないよう、
# 使用する Win32 API すべてに引数型・戻り値型を明示する。
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wt.HINSTANCE, wt.DWORD]
user32.SetWindowsHookExW.restype = wt.HHOOK
user32.UnhookWindowsHookEx.argtypes = [wt.HHOOK]
user32.UnhookWindowsHookEx.restype = wt.BOOL
user32.CallNextHookEx.argtypes = [wt.HHOOK, ctypes.c_int, wt.WPARAM, wt.LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.GetMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT]
user32.GetMessageW.restype = ctypes.c_int
user32.TranslateMessage.argtypes = [ctypes.POINTER(wt.MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wt.MSG)]
user32.DispatchMessageW.restype = LRESULT
user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.CreateWindowExW.argtypes = [
    wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID,
]
user32.CreateWindowExW.restype = wt.HWND
user32.RegisterRawInputDevices.argtypes = [ctypes.c_void_p, wt.UINT, wt.UINT]
user32.RegisterRawInputDevices.restype = wt.BOOL
user32.GetRawInputData.argtypes = [
    wt.LPARAM, wt.UINT, ctypes.c_void_p, ctypes.POINTER(wt.UINT), wt.UINT
]
user32.GetRawInputData.restype = wt.UINT
user32.PostThreadMessageW.argtypes = [wt.DWORD, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.PostThreadMessageW.restype = wt.BOOL
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
user32.SetCursorPos.restype = wt.BOOL
user32.ClipCursor.argtypes = [ctypes.c_void_p]
user32.ClipCursor.restype = wt.BOOL
user32.SendInput.argtypes = [wt.UINT, ctypes.c_void_p, ctypes.c_int]
user32.SendInput.restype = wt.UINT
user32.GetSystemMetrics.argtypes = [ctypes.c_int]
user32.GetSystemMetrics.restype = ctypes.c_int
kernel32.GetModuleHandleW.argtypes = [wt.LPCWSTR]
kernel32.GetModuleHandleW.restype = wt.HMODULE
kernel32.GetCurrentThreadId.restype = wt.DWORD


def enable_dpi_awareness() -> None:
    """Per-Monitor V2 DPI awareness。混在 DPI 環境でのエッジ座標のずれを防ぐ。"""
    try:
        DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)
        user32.SetProcessDpiAwarenessContext(
            DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        )
    except (AttributeError, OSError):
        try:
            user32.SetProcessDPIAware()
        except OSError:
            pass


def parse_hotkey(spec: str) -> tuple[frozenset[str], int]:
    """"ctrl+alt+q" → (修飾キー集合, キーの VK)。"""
    parts = [p.strip().lower() for p in spec.split("+") if p.strip()]
    mods = frozenset(p for p in parts if p in ("ctrl", "alt", "shift", "win"))
    keys = [p for p in parts if p not in mods]
    vk = ord(keys[0].upper()) if keys else 0
    return mods, vk


class MonitorInfo:
    """モニタ配置から、設定されたエッジの最外周セグメントを求める。"""

    @staticmethod
    def get_monitor_rects() -> list[tuple[int, int, int, int]]:
        rects: list[tuple[int, int, int, int]] = []

        MONITORENUMPROC = ctypes.WINFUNCTYPE(
            wt.BOOL, wt.HMONITOR, wt.HDC, ctypes.POINTER(wt.RECT), wt.LPARAM
        )

        def callback(_hmon, _hdc, rect_ptr, _lparam):
            r = rect_ptr.contents
            rects.append((r.left, r.top, r.right, r.bottom))
            return True

        user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(callback), 0)
        return rects

    @staticmethod
    def edge_geometry(edge: str) -> tuple[int, int, int]:
        """(エッジ固定座標, 範囲lo, 範囲hi) を返す。"""
        rects = MonitorInfo.get_monitor_rects()
        if not rects:  # フォールバック: プライマリのみ
            w = user32.GetSystemMetrics(0)
            h = user32.GetSystemMetrics(1)
            rects = [(0, 0, w, h)]
        if edge == "right":
            coord = max(r[2] for r in rects) - 1
            touching = [r for r in rects if r[2] - 1 == coord]
            return coord, min(r[1] for r in touching), max(r[3] for r in touching) - 1
        if edge == "left":
            coord = min(r[0] for r in rects)
            touching = [r for r in rects if r[0] == coord]
            return coord, min(r[1] for r in touching), max(r[3] for r in touching) - 1
        if edge == "top":
            coord = min(r[1] for r in rects)
            touching = [r for r in rects if r[1] == coord]
            return coord, min(r[0] for r in touching), max(r[2] for r in touching) - 1
        coord = max(r[3] for r in rects) - 1
        touching = [r for r in rects if r[3] - 1 == coord]
        return coord, min(r[0] for r in touching), max(r[2] for r in touching) - 1


class InputCapture(threading.Thread):
    """フック + Raw Input を動かすスレッド。

    emit(event) はフックスレッドから呼ばれる。イベント:
      ("state", "remote" | "local")
      ("move", dx, dy)                 raw 相対移動 (REMOTE 中のみ)
      ("button", index, down)          0=左 1=右 2=中 3=X1 4=X2
      ("wheel", v_delta, h_delta)      ±120 単位
      ("key", vk, scan, extended, down)
    """

    def __init__(
        self,
        machine: EdgeStateMachine,
        emit: Callable[[tuple], None],
        release_hotkey: str = "ctrl+alt+q",
        forward_injected: bool = True,
        passthrough_buttons: tuple[str, ...] = (),
    ) -> None:
        super().__init__(name="winuc-capture", daemon=True)
        self.machine = machine
        self.emit = emit
        self.armed = False  # BLE 接続済みのときだけ True (app が設定)
        # X-Mouse Button Control 等が SendInput したイベントも転送する
        self.forward_injected = forward_injected
        # REMOTE 中もフックチェーンの下流 (XMBC 等) へ通すボタン。
        # 通したボタンは XMBC が変換・注入し、注入イベント側を転送する。
        self.passthrough_buttons = frozenset(
            BUTTON_NAMES[name] for name in passthrough_buttons if name in BUTTON_NAMES
        )
        self._hotkey_mods, self._hotkey_vk = parse_hotkey(release_hotkey)
        self._thread_id = 0
        self._mouse_hook = None
        self._keyboard_hook = None
        self._hwnd = None
        self._down_vks: set[int] = set()
        self._lock = threading.Lock()
        self._started_event = threading.Event()
        # コールバックを GC から守るため参照を保持
        self._mouse_proc = HOOKPROC(self._mouse_hook_proc)
        self._keyboard_proc = HOOKPROC(self._keyboard_hook_proc)
        self._wnd_proc = WNDPROC(self._window_proc)

    # ----------------------------------------------------------- lifecycle

    def run(self) -> None:
        self._thread_id = kernel32.GetCurrentThreadId()
        self._create_raw_input_window()
        self._mouse_hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self._mouse_proc, None, 0)
        self._keyboard_hook = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, self._keyboard_proc, None, 0
        )
        if not self._mouse_hook or not self._keyboard_hook:
            logger.error("フックのインストールに失敗しました (エラー %d)", kernel32.GetLastError())
        self._update_edge_geometry()
        self._started_event.set()
        logger.info("入力キャプチャ開始 (edge=%s)", self.machine.edge)

        msg = wt.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        if self._mouse_hook:
            user32.UnhookWindowsHookEx(self._mouse_hook)
        if self._keyboard_hook:
            user32.UnhookWindowsHookEx(self._keyboard_hook)
        user32.ClipCursor(None)

    def wait_started(self, timeout: float = 5.0) -> bool:
        return self._started_event.wait(timeout)

    def stop(self) -> None:
        self.force_release()
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)

    def force_release(self) -> None:
        """任意のスレッドから安全に呼べる: 即座に Windows へ制御を戻す。"""
        with self._lock:
            if self.machine.state == State.LOCAL:
                return
            x, y = self.machine.force_local()
        user32.ClipCursor(None)
        self._set_cursor_inward(x, y)
        self.emit(("state", "local"))

    # -------------------------------------------------------------- window

    def _create_raw_input_window(self) -> None:
        WNDCLASS = type(
            "WNDCLASS",
            (ctypes.Structure,),
            {
                "_fields_": [
                    ("style", wt.UINT),
                    ("lpfnWndProc", WNDPROC),
                    ("cbClsExtra", ctypes.c_int),
                    ("cbWndExtra", ctypes.c_int),
                    ("hInstance", wt.HINSTANCE),
                    ("hIcon", wt.HICON),
                    ("hCursor", wt.HANDLE),
                    ("hbrBackground", wt.HBRUSH),
                    ("lpszMenuName", wt.LPCWSTR),
                    ("lpszClassName", wt.LPCWSTR),
                ]
            },
        )
        hinstance = kernel32.GetModuleHandleW(None)
        wc = WNDCLASS()
        wc.lpfnWndProc = self._wnd_proc
        wc.hInstance = hinstance
        wc.lpszClassName = "WinUCRawInput"
        if not user32.RegisterClassW(ctypes.byref(wc)):
            logger.error("RegisterClassW 失敗 (%d)", kernel32.GetLastError())
        # Raw Input は message-only window には届かないため、非表示のトップレベル窓を使う
        self._hwnd = user32.CreateWindowExW(
            0, "WinUCRawInput", "WinUC", 0, 0, 0, 0, 0, None, None, hinstance, None
        )
        rid = RAWINPUTDEVICE(0x01, 0x02, RIDEV_INPUTSINK, self._hwnd)
        if not user32.RegisterRawInputDevices(
            ctypes.byref(rid), 1, ctypes.sizeof(RAWINPUTDEVICE)
        ):
            logger.error("RegisterRawInputDevices 失敗 (%d)", kernel32.GetLastError())

    def _window_proc(self, hwnd, msg, wparam, lparam) -> int:
        if msg == WM_INPUT:
            self._on_raw_input(lparam)
            return 0
        if msg == WM_DISPLAYCHANGE:
            self._update_edge_geometry()
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _update_edge_geometry(self) -> None:
        coord, lo, hi = MonitorInfo.edge_geometry(self.machine.edge)
        self.machine.set_edge_geometry(coord, lo, hi)
        logger.info("エッジ座標: %s=%d, 範囲 %d..%d", self.machine.edge, coord, lo, hi)

    # ----------------------------------------------------------- raw input

    def _on_raw_input(self, lparam: int) -> None:
        state = self.machine.state
        if state == State.LOCAL:
            return
        raw = RAWINPUT()
        size = wt.UINT(ctypes.sizeof(RAWINPUT))
        got = user32.GetRawInputData(
            lparam,
            RID_INPUT,
            ctypes.byref(raw),
            ctypes.byref(size),
            ctypes.sizeof(RAWINPUTHEADER),
        )
        if got in (0, 0xFFFFFFFF) or raw.header.dwType != RIM_TYPEMOUSE:
            return
        if raw.mouse.usFlags & MOUSE_MOVE_ABSOLUTE:
            return  # タブレット等の絶対座標デバイスは対象外
        dx, dy = raw.mouse.lLastX, raw.mouse.lLastY
        if dx == 0 and dy == 0:
            return

        if state == State.PUSHING:
            result = self.machine.on_push_delta(dx, dy, time.monotonic() * 1000)
            if result == PushResult.CROSS:
                self._enter_remote()
            elif result == PushResult.CANCEL:
                self._cancel_push()
        elif state == State.REMOTE:
            motion = self.machine.on_remote_delta(dx, dy)
            if motion.exited:
                self._exit_remote(motion.exit_point)
            elif motion.dx or motion.dy:
                self.emit(("move", motion.dx, motion.dy))

    # -------------------------------------------------------- transitions

    def _pin_cursor(self, x: int, y: int) -> None:
        rect = wt.RECT(x, y, x + 1, y + 1)
        user32.SetCursorPos(x, y)
        user32.ClipCursor(ctypes.byref(rect))

    def _set_cursor_inward(self, x: int, y: int, inset: int = 2) -> None:
        edge = self.machine.edge
        if edge == "right":
            x -= inset
        elif edge == "left":
            x += inset
        elif edge == "top":
            y += inset
        else:
            y -= inset
        user32.SetCursorPos(x, y)

    def _begin_push(self, x: int, y: int) -> None:
        self.machine.begin_push(x, y, time.monotonic() * 1000)
        self._pin_cursor(x, y)

    def _cancel_push(self) -> None:
        user32.ClipCursor(None)
        x, y = self.machine.entry_point
        self._set_cursor_inward(x, y)

    def _enter_remote(self) -> None:
        # 押しっぱなしの修飾キーを Windows 側で解放して stuck を防ぐ
        for vk in list(self._down_vks & _MODIFIER_VKS):
            self._inject_key_up(vk)
        self._down_vks.clear()
        # カーソルをエッジの隅に退避して見えなくする
        edge = self.machine.edge
        if edge in ("right", "left"):
            hide_x = self.machine._edge_coord
            hide_y = self.machine._edge_hi
        else:
            hide_x = self.machine._edge_hi
            hide_y = self.machine._edge_coord
        self._pin_cursor(hide_x, hide_y)
        self.emit(("state", "remote"))
        logger.info("→ iPad へ移動")

    def _exit_remote(self, exit_point: tuple[int, int] | None) -> None:
        user32.ClipCursor(None)
        if exit_point is not None:
            self._set_cursor_inward(*exit_point)
        self.emit(("state", "local"))
        logger.info("← Windows へ復帰")

    @staticmethod
    def _inject_key_up(vk: int) -> None:
        inp = INPUT()
        inp.type = INPUT_KEYBOARD
        inp.union.ki = KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP, 0, MAGIC_EXTRA_INFO)
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    # ---------------------------------------------------------- mouse hook

    def _mouse_hook_proc(self, ncode: int, wparam: int, lparam: int) -> int:
        if ncode < 0:
            return user32.CallNextHookEx(None, ncode, wparam, lparam)
        info = ctypes.cast(lparam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
        injected = bool(info.flags & LLMHF_INJECTED)
        ours = injected and info.dwExtraInfo == MAGIC_EXTRA_INFO

        state = self.machine.state

        if state == State.LOCAL:
            if (
                wparam == WM_MOUSEMOVE
                and not injected
                and self.armed
                and self.machine.hits_edge(info.pt.x, info.pt.y)
            ):
                self._begin_push(info.pt.x, info.pt.y)
            return user32.CallNextHookEx(None, ncode, wparam, lparam)

        if state == State.PUSHING:
            if injected:
                return user32.CallNextHookEx(None, ncode, wparam, lparam)
            # 押し込み中にクリック等をしたらキャンセルしてローカルに渡す
            if wparam != WM_MOUSEMOVE:
                self.machine.cancel_push()
                self._cancel_push()
                return user32.CallNextHookEx(None, ncode, wparam, lparam)
            return 1  # 移動は飲み込む (計測は Raw Input 側)

        # ---- REMOTE ----
        # 自分の SetCursorPos/SendInput、および転送しない設定の注入イベントは素通し
        if ours or (injected and not self.forward_injected):
            return user32.CallNextHookEx(None, ncode, wparam, lparam)
        # 移動: 物理入力は Raw Input 側で計測するので飲み込む。注入移動は素通し。
        if wparam == WM_MOUSEMOVE:
            if injected:
                return user32.CallNextHookEx(None, ncode, wparam, lparam)
            return 1

        if wparam in _MOUSE_BUTTON_MESSAGES:
            index, down = _MOUSE_BUTTON_MESSAGES[wparam]
        elif wparam in (WM_XBUTTONDOWN, WM_XBUTTONUP):
            xbutton = (info.mouseData >> 16) & 0xFFFF
            index = 3 if xbutton == 1 else 4
            down = wparam == WM_XBUTTONDOWN
        elif wparam == WM_MOUSEWHEEL:
            delta = ctypes.c_short((info.mouseData >> 16) & 0xFFFF).value
            self.emit(("wheel", delta, 0))
            return 1
        elif wparam == WM_MOUSEHWHEEL:
            delta = ctypes.c_short((info.mouseData >> 16) & 0xFFFF).value
            self.emit(("wheel", 0, delta))
            return 1
        else:
            return 1

        # 物理ボタンのうち素通し指定のものはフックチェーンの下流 (XMBC 等) に渡し、
        # XMBC が注入する変換後イベントを転送する
        if not injected and index in self.passthrough_buttons:
            return user32.CallNextHookEx(None, ncode, wparam, lparam)
        self.emit(("button", index, down))
        return 1

    # ------------------------------------------------------- keyboard hook

    def _keyboard_hook_proc(self, ncode: int, wparam: int, lparam: int) -> int:
        if ncode < 0:
            return user32.CallNextHookEx(None, ncode, wparam, lparam)
        info = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
        if info.flags & LLKHF_INJECTED:
            ours = info.dwExtraInfo == MAGIC_EXTRA_INFO
            if (
                ours
                or not self.forward_injected
                or self.machine.state != State.REMOTE
            ):
                return user32.CallNextHookEx(None, ncode, wparam, lparam)
            # XMBC/AutoHotkey 等が注入したキーも REMOTE 中は転送対象

        down = not (info.flags & LLKHF_UP)
        vk = info.vkCode

        if self.machine.state != State.REMOTE:
            # LOCAL/PUSHING: 押下状態だけ追跡してそのまま通す
            if down:
                self._down_vks.add(vk)
            else:
                self._down_vks.discard(vk)
            return user32.CallNextHookEx(None, ncode, wparam, lparam)

        # REMOTE: 解放ホットキーの判定
        if down:
            self._down_vks.add(vk)
        else:
            self._down_vks.discard(vk)
        if down and vk == self._hotkey_vk and self._hotkey_matches():
            self.force_release()
            return 1

        extended = bool(info.flags & LLKHF_EXTENDED)
        self.emit(("key", vk, info.scanCode, extended, down))
        return 1

    def _hotkey_matches(self) -> bool:
        down = self._down_vks
        checks = {
            "ctrl": {0xA2, 0xA3, 0x11},
            "alt": {0xA4, 0xA5, 0x12},
            "shift": {0xA0, 0xA1, 0x10},
            "win": {0x5B, 0x5C},
        }
        return all(down & checks[m] for m in self._hotkey_mods)
