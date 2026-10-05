"""Win32 API wrapper for KakaoTalk PC automation."""
import sys
import time
import ctypes
from ctypes import wintypes
from typing import Optional, List, Dict

import win32gui
import win32api
import win32clipboard
import win32process

from . import config


def _log(msg: str):
    """Write debug message to stderr (visible in MCP server logs)."""
    print(f"[kakao-controller] {msg}", file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# Window discovery
# ---------------------------------------------------------------------------

def is_kakaotalk_running() -> Dict:
    """Check if KakaoTalk main window exists.

    Returns:
        Dict with running (bool), hwnd (int|None), pid (int|None).
    """
    hwnd = win32gui.FindWindow(
        config.KAKAO_MAIN_WINDOW_CLASS, config.KAKAO_MAIN_WINDOW_TITLE
    )
    if hwnd == 0:
        return {"running": False, "hwnd": None, "pid": None}
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    return {"running": True, "hwnd": hwnd, "pid": pid}


def find_chat_window(room_name: str) -> Optional[int]:
    """Find a chat window by exact title (room name).

    Returns hwnd or None; raises ValueError for ambiguous exact matches.
    """
    main_hwnd = win32gui.FindWindow(
        config.KAKAO_MAIN_WINDOW_CLASS, config.KAKAO_MAIN_WINDOW_TITLE
    )
    results: List[int] = []

    def _cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            cls = win32gui.GetClassName(hwnd)
            title = win32gui.GetWindowText(hwnd)
            if hwnd != main_hwnd and cls == config.KAKAO_CHAT_WINDOW_CLASS and title == room_name:
                results.append(hwnd)
        return True

    win32gui.EnumWindows(_cb, None)
    if len(results) > 1:
        raise ValueError(f"Multiple open chat windows have the exact title '{room_name}'")
    return results[0] if results else None


def list_chat_windows() -> List[Dict]:
    """List all currently open KakaoTalk chat windows.

    Returns list of dicts with hwnd and title.
    """
    main_hwnd = win32gui.FindWindow(
        config.KAKAO_MAIN_WINDOW_CLASS, config.KAKAO_MAIN_WINDOW_TITLE
    )
    windows: List[Dict] = []

    def _cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            cls = win32gui.GetClassName(hwnd)
            title = win32gui.GetWindowText(hwnd)
            if (
                cls == config.KAKAO_CHAT_WINDOW_CLASS
                and hwnd != main_hwnd
                and title
                and title != config.KAKAO_MAIN_WINDOW_TITLE
            ):
                windows.append({"hwnd": hwnd, "title": title})
        return True

    win32gui.EnumWindows(_cb, None)
    return windows


def find_child_window_recursive(parent_hwnd: int, class_name: str) -> Optional[int]:
    """Recursively search for a child window by class name.

    Needed because RICHEDIT50W may be nested several levels deep.
    Returns hwnd or None.
    """
    found: List[int] = []

    def _cb(hwnd, _):
        if win32gui.GetClassName(hwnd) == class_name:
            found.append(hwnd)
            return False  # stop enumeration
        return True

    try:
        win32gui.EnumChildWindows(parent_hwnd, _cb, None)
    except Exception:
        pass
    return found[0] if found else None


def bring_window_to_front(hwnd: int):
    """Restore and bring a window to the foreground.

    Uses the existing Windows activation calls once. Callers verify focus;
    Windows may refuse activation, so visibility alone is not success.
    """
    SW_RESTORE = 9
    HWND_TOPMOST = -1
    HWND_NOTOPMOST = -2
    SWP_NOMOVE = 0x0002
    SWP_NOSIZE = 0x0001
    SWP_SHOWWINDOW = 0x0040

    _user32.ShowWindow(hwnd, SW_RESTORE)

    # Use ctypes SetForegroundWindow (returns 0 on fail, no exception)
    _user32.SetForegroundWindow(hwnd)

    # Also temporarily set topmost to ensure visibility
    _user32.SetWindowPos(
        hwnd, HWND_TOPMOST, 0, 0, 0, 0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW,
    )
    _user32.SetWindowPos(
        hwnd, HWND_NOTOPMOST, 0, 0, 0, 0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW,
    )


# ---------------------------------------------------------------------------
# Keyboard helpers
# ---------------------------------------------------------------------------

_user32 = ctypes.windll.user32


class _GUITHREADINFO(ctypes.Structure):
    """Windows GUI-thread information, including the actual focused control."""

    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hwndActive", wintypes.HWND),
        ("hwndFocus", wintypes.HWND),
        ("hwndCapture", wintypes.HWND),
        ("hwndMenuOwner", wintypes.HWND),
        ("hwndMoveSize", wintypes.HWND),
        ("hwndCaret", wintypes.HWND),
        ("rcCaret", wintypes.RECT),
    ]


# Preserve pointer-sized HWND values in the retained activation/focus calls.
_user32.GetForegroundWindow.argtypes = []
_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.GetGUIThreadInfo.argtypes = [wintypes.DWORD, ctypes.POINTER(_GUITHREADINFO)]
_user32.GetGUIThreadInfo.restype = wintypes.BOOL
_user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.ShowWindow.restype = wintypes.BOOL
_user32.SetForegroundWindow.argtypes = [wintypes.HWND]
_user32.SetForegroundWindow.restype = wintypes.BOOL
_user32.SetWindowPos.argtypes = [
    wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
    ctypes.c_int, ctypes.c_int, wintypes.UINT,
]
_user32.SetWindowPos.restype = wintypes.BOOL


def _verify_expected_focus(hwnd: int, control_hwnd: Optional[int] = None) -> bool:
    """Check once; never inject input, retry activation, or guess on failure."""
    try:
        if _user32.GetForegroundWindow() != hwnd:
            return False
        if control_hwnd is None:
            return True
        if not win32gui.IsChild(hwnd, control_hwnd):
            return False
        thread_id, _ = win32process.GetWindowThreadProcessId(hwnd)
        if not thread_id:
            return False
        info = _GUITHREADINFO()
        info.cbSize = ctypes.sizeof(info)
        if not _user32.GetGUIThreadInfo(thread_id, ctypes.byref(info)):
            return False
        return info.hwndActive == hwnd and info.hwndFocus == control_hwnd
    except Exception:
        return False


def _send_ctrl_key_combo(vk_key: int):
    """Send Ctrl+<key> combo using keybd_event (requires foreground focus)."""
    _user32.keybd_event(config.VK_CONTROL, 0, 0, 0)
    time.sleep(0.02)
    _user32.keybd_event(vk_key, 0, 0, 0)
    time.sleep(0.02)
    _user32.keybd_event(vk_key, 0, config.KEYEVENTF_KEYUP, 0)
    time.sleep(0.02)
    _user32.keybd_event(config.VK_CONTROL, 0, config.KEYEVENTF_KEYUP, 0)


# ---------------------------------------------------------------------------
# Clipboard helpers
# ---------------------------------------------------------------------------

def _read_clipboard_text(max_retries: int = None, interval_sec: float = None) -> str:
    """Read text from clipboard with retry logic."""
    if max_retries is None:
        max_retries = config.CLIPBOARD_MAX_RETRIES
    if interval_sec is None:
        interval_sec = config.CLIPBOARD_RETRY_INTERVAL_SEC

    for _ in range(max_retries):
        try:
            win32clipboard.OpenClipboard()
            try:
                data = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
                return data if data else ""
            finally:
                win32clipboard.CloseClipboard()
        except Exception:
            time.sleep(interval_sec)
    return ""


# ---------------------------------------------------------------------------
# Message sending
# ---------------------------------------------------------------------------

def send_message_to_room(room_name: str, text: str) -> Dict:
    """Send a text message to a KakaoTalk chat room.

    Pastes text via clipboard into RICHEDIT50W and sends with keybd_event Enter.
    NOTE: This briefly brings the chat window to the foreground.

    Returns:
        Dict with success (bool) and message or error.
    """
    hwnd = find_chat_window(room_name)
    if hwnd is None:
        return {"success": False, "error": f"Chat window '{room_name}' not found"}

    edit_hwnd = find_child_window_recursive(hwnd, config.KAKAO_EDIT_CLASS)
    if edit_hwnd is None:
        return {"success": False, "error": f"Edit control not found in '{room_name}'"}

    # Bring window to foreground and focus the edit control
    if not _ensure_foreground(hwnd):
        return {"success": False, "error": f"Cannot activate chat window '{room_name}'"}

    # Click on the edit control to ensure focus
    try:
        rect = win32gui.GetWindowRect(edit_hwnd)
        cx = (rect[0] + rect[2]) // 2
        cy = (rect[1] + rect[3]) // 2
        if not _user32.SetCursorPos(cx, cy):
            return {"success": False, "error": f"Cannot focus edit control in '{room_name}'"}
        _user32.mouse_event(0x0002, 0, 0, 0, 0)  # LEFTDOWN
        _user32.mouse_event(0x0004, 0, 0, 0, 0)  # LEFTUP
        time.sleep(config.EDIT_CLICK_WAIT_SEC)
    except Exception as e:
        return {"success": False, "error": f"Cannot focus edit control in '{room_name}': {e}"}

    if not _verify_expected_focus(hwnd, edit_hwnd):
        return {"success": False, "error": f"Expected editor in '{room_name}' is not focused"}

    # Paste text via clipboard (handles Korean correctly, unlike WM_SETTEXT on some versions)
    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
    win32clipboard.CloseClipboard()
    time.sleep(config.CLIPBOARD_PASTE_WAIT_SEC)
    _send_ctrl_key_combo(0x56)  # Ctrl+V
    time.sleep(config.AFTER_PASTE_WAIT_SEC)

    # Press Enter using keybd_event (not WM_KEYDOWN — WM_KEYDOWN inserts newline in RICHEDIT)
    if not _verify_expected_focus(hwnd, edit_hwnd):
        return {"success": False, "error": "Focus changed after paste; Enter was not sent. Text may remain in the editor."}
    _user32.keybd_event(config.VK_RETURN, 0, 0, 0)
    _user32.keybd_event(config.VK_RETURN, 0, config.KEYEVENTF_KEYUP, 0)

    return {"success": True, "message": f"Message sent to '{room_name}'"}


# Message reading and room search

def read_chat_messages(room_name: str) -> Dict:
    """Read messages from a KakaoTalk chat room via Ctrl+A → Ctrl+C.

    NOTE: This briefly brings the chat window to the foreground.

    Returns:
        Dict with success (bool), raw_text (str), and error if failed.
    """
    hwnd = find_chat_window(room_name)
    if hwnd is None:
        return {"success": False, "error": f"Chat window '{room_name}' not found", "raw_text": ""}

    list_hwnd = find_child_window_recursive(hwnd, config.KAKAO_LIST_CONTROL_CLASS)
    if list_hwnd is None:
        return {
            "success": False,
            "error": f"List control not found in '{room_name}'",
            "raw_text": "",
        }

    # Bring the chat window to foreground — required for keybd_event
    if not _ensure_foreground(hwnd):
        return {"success": False, "error": f"Cannot activate chat window '{room_name}'", "raw_text": ""}

    # Click on the list control to ensure it has focus
    try:
        rect = win32gui.GetWindowRect(list_hwnd)
        cx = (rect[0] + rect[2]) // 2
        cy = (rect[1] + rect[3]) // 2
        if not _user32.SetCursorPos(cx, cy):
            return {"success": False, "error": f"Cannot focus message list in '{room_name}'", "raw_text": ""}
        _user32.mouse_event(0x0002, 0, 0, 0, 0)  # MOUSEEVENTF_LEFTDOWN
        _user32.mouse_event(0x0004, 0, 0, 0, 0)  # MOUSEEVENTF_LEFTUP
        time.sleep(config.EDIT_CLICK_WAIT_SEC)
    except Exception as e:
        return {"success": False, "error": f"Cannot focus message list in '{room_name}': {e}", "raw_text": ""}

    if not _verify_expected_focus(hwnd, list_hwnd):
        return {"success": False, "error": f"Expected message list in '{room_name}' is not focused", "raw_text": ""}

    # Ctrl+A (select all)
    _send_ctrl_key_combo(config.VK_A)
    time.sleep(config.KEY_COMBO_WAIT_SEC)

    # Ctrl+C (copy)
    _send_ctrl_key_combo(config.VK_C)
    time.sleep(config.KEY_COMBO_WAIT_SEC)

    # Read clipboard
    raw_text = _read_clipboard_text()

    return {"success": True, "raw_text": raw_text}


# ---------------------------------------------------------------------------
# Room search/open
# ---------------------------------------------------------------------------

def _find_chat_list_view(main_hwnd: int) -> Optional[int]:
    """Find the ChatRoomListView window inside the main window."""
    chat_list_view = None

    def _find_view(hwnd, _):
        nonlocal chat_list_view
        cls = win32gui.GetClassName(hwnd)
        text = win32gui.GetWindowText(hwnd)
        if cls == "EVA_Window" and "ChatRoomListView" in text:
            chat_list_view = hwnd
            return False
        return True

    try:
        win32gui.EnumChildWindows(main_hwnd, _find_view, None)
    except Exception:
        pass
    return chat_list_view


def _activate_search_and_get_edit(main_hwnd: int) -> Optional[int]:
    """Activate the chat search bar using Ctrl+F and return the Edit hwnd.

    KakaoTalk PC uses Ctrl+F to open the search bar in the chat list view.
    After Ctrl+F, the Edit control becomes visible and focused.
    """
    chat_list_view = _find_chat_list_view(main_hwnd)
    _log(f"ChatRoomListView hwnd: {chat_list_view}")
    if chat_list_view is None:
        return None

    # Press Ctrl+F to activate search
    _send_ctrl_key_combo(0x46)  # 0x46 = 'F'
    time.sleep(config.SEARCH_ACTIVATE_WAIT_SEC)

    # Find the Edit control — should now be visible and focused
    edit_hwnd = find_child_window_recursive(chat_list_view, "Edit")
    if edit_hwnd:
        vis = win32gui.IsWindowVisible(edit_hwnd)
        _log(f"Edit hwnd after Ctrl+F: {edit_hwnd}, visible: {vis}")
    else:
        _log("Edit not found after Ctrl+F")
    return edit_hwnd


def _ensure_foreground(hwnd: int) -> bool:
    """Ensure a window is in the foreground. Returns True if successful."""
    bring_window_to_front(hwnd)
    time.sleep(config.WINDOW_ACTIVATE_WAIT_SEC)
    return _verify_expected_focus(hwnd)


def search_and_open_room(room_name: str) -> Dict:
    """Search for a chat room in KakaoTalk main window and open it.

    Uses WM_CHAR in the search Edit box, then Enter on the first result.
    Reports success only for an exact, unambiguous active chat window.

    Returns:
        Dict with success (bool) and message or error.
    """
    main_hwnd = win32gui.FindWindow(
        config.KAKAO_MAIN_WINDOW_CLASS, config.KAKAO_MAIN_WINDOW_TITLE
    )
    if main_hwnd == 0:
        return {"success": False, "error": "KakaoTalk main window not found"}

    # Ensure KakaoTalk is in the foreground before sending keyboard events
    if not _ensure_foreground(main_hwnd):
        return {"success": False, "error": "Cannot activate KakaoTalk main window"}

    # Ctrl+F activates the search bar (Edit becomes visible and focused)
    edit_hwnd = _activate_search_and_get_edit(main_hwnd)
    if edit_hwnd is None:
        return {"success": False, "error": "Search box not found in KakaoTalk main window"}

    if not _verify_expected_focus(main_hwnd, edit_hwnd):
        return {"success": False, "error": "Expected KakaoTalk search box is not focused"}

    # Clear any existing text in the Edit using EM_SETSEL + WM_CLEAR
    EM_SETSEL = 0x00B1
    WM_CLEAR = 0x0303
    win32api.SendMessage(edit_hwnd, EM_SETSEL, 0, -1)  # Select all
    win32api.SendMessage(edit_hwnd, WM_CLEAR, 0, 0)     # Delete selected
    time.sleep(config.EDIT_CLICK_WAIT_SEC)

    # Type search text character by character using WM_CHAR
    # This goes directly to the Edit control — no focus or clipboard needed
    for ch in room_name:
        win32api.SendMessage(edit_hwnd, config.WM_CHAR, ord(ch), 0)
        time.sleep(config.SEARCH_CHAR_INTERVAL_SEC)
    _log(f"Typed '{room_name}' into Edit via WM_CHAR")
    time.sleep(config.SEARCH_RESULTS_WAIT_SEC)  # Wait for search results to populate

    # Press Enter to open the first search result (already selected by default)
    if not _verify_expected_focus(main_hwnd, edit_hwnd):
        return {"success": False, "error": "KakaoTalk search box lost focus; Enter was not sent"}
    _log("Pressing Enter to open first search result")
    _user32.keybd_event(config.VK_RETURN, 0, 0, 0)
    _user32.keybd_event(config.VK_RETURN, 0, config.KEYEVENTF_KEYUP, 0)
    time.sleep(config.SEARCH_OPEN_WAIT_SEC)

    # Do NOT press Escape here — it would close the newly opened chat window

    # Look for opened chat windows
    all_windows = list_chat_windows()
    _log(f"Open windows after search: {[w['title'] for w in all_windows]}")
    matches = [w for w in all_windows if w["title"] == room_name]
    if len(matches) > 1:
        return {"success": False, "error": f"Multiple open chat windows have the exact title '{room_name}'"}
    if matches:
        hwnd = matches[0]["hwnd"]
        if not _verify_expected_focus(hwnd):
            return {"success": False, "error": f"Exact chat window '{room_name}' is not active"}
        return {"success": True, "message": f"Opened chat room '{room_name}'", "hwnd": hwnd}

    return {
        "success": False,
        "error": f"Chat room '{room_name}' not found after search. "
                 "The exact room name may differ from search results.",
    }
