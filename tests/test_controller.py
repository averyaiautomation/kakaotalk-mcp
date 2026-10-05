"""Mock-based unit tests for kakao_mcp.controller."""
import sys
import os
import pytest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from kakao_mcp import controller, config


@pytest.fixture(autouse=True)
def desktop():
    """No controller test may reach real desktop, clipboard or input APIs."""
    with (
        patch.object(controller, "_user32") as user32,
        patch.object(controller, "win32gui") as gui,
        patch.object(controller, "win32api") as api,
        patch.object(controller, "win32process") as process,
        patch.object(controller, "win32clipboard") as clipboard,
        patch.object(controller.time, "sleep"),
    ):
        yield {"user32": user32, "gui": gui, "api": api,
               "process": process, "clipboard": clipboard}


# ---------------------------------------------------------------------------
# is_kakaotalk_running
# ---------------------------------------------------------------------------

@patch("kakao_mcp.controller.win32process")
@patch("kakao_mcp.controller.win32gui")
def test_is_running_true(mock_gui, mock_proc):
    mock_gui.FindWindow.return_value = 12345
    mock_proc.GetWindowThreadProcessId.return_value = (0, 9876)
    result = controller.is_kakaotalk_running()
    assert result["running"] is True
    assert result["hwnd"] == 12345
    assert result["pid"] == 9876
    mock_gui.FindWindow.assert_called_once_with(
        config.KAKAO_MAIN_WINDOW_CLASS, config.KAKAO_MAIN_WINDOW_TITLE
    )


@patch("kakao_mcp.controller.win32gui")
def test_is_running_false(mock_gui):
    mock_gui.FindWindow.return_value = 0
    result = controller.is_kakaotalk_running()
    assert result["running"] is False
    assert result["hwnd"] is None


# ---------------------------------------------------------------------------
# find_chat_window
# ---------------------------------------------------------------------------

@patch("kakao_mcp.controller.win32gui")
def test_find_chat_window_found(mock_gui):
    # Simulate EnumWindows calling the callback with a matching window
    def enum_side_effect(callback, _):
        # Simulate a matching window
        mock_gui.IsWindowVisible.return_value = True
        mock_gui.GetClassName.return_value = config.KAKAO_CHAT_WINDOW_CLASS
        mock_gui.GetWindowText.return_value = "TestRoom"
        callback(99999, None)

    mock_gui.EnumWindows.side_effect = enum_side_effect
    result = controller.find_chat_window("TestRoom")
    assert result == 99999


@patch("kakao_mcp.controller.win32gui")
def test_find_chat_window_not_found(mock_gui):
    def enum_side_effect(callback, _):
        mock_gui.IsWindowVisible.return_value = True
        mock_gui.GetClassName.return_value = config.KAKAO_CHAT_WINDOW_CLASS
        mock_gui.GetWindowText.return_value = "OtherRoom"
        callback(99999, None)

    mock_gui.EnumWindows.side_effect = enum_side_effect
    result = controller.find_chat_window("TestRoom")
    assert result is None


# ---------------------------------------------------------------------------
# list_chat_windows
# ---------------------------------------------------------------------------

@patch("kakao_mcp.controller.win32gui")
def test_list_chat_windows(mock_gui):
    mock_gui.FindWindow.return_value = 10000  # main window

    call_count = [0]
    rooms_data = [
        (10000, config.KAKAO_MAIN_WINDOW_TITLE),  # main window — should be excluded
        (20001, "Room A"),
        (20002, "Room B"),
    ]

    def enum_side_effect(callback, _):
        for hwnd, title in rooms_data:
            mock_gui.IsWindowVisible.return_value = True
            mock_gui.GetClassName.return_value = config.KAKAO_CHAT_WINDOW_CLASS
            mock_gui.GetWindowText.return_value = title
            callback(hwnd, None)

    mock_gui.EnumWindows.side_effect = enum_side_effect
    result = controller.list_chat_windows()
    titles = [r["title"] for r in result]
    assert "Room A" in titles
    assert "Room B" in titles
    assert config.KAKAO_MAIN_WINDOW_TITLE not in titles


# ---------------------------------------------------------------------------
# send_message_to_room
# ---------------------------------------------------------------------------

@patch("kakao_mcp.controller.win32api")
@patch("kakao_mcp.controller.find_child_window_recursive")
@patch("kakao_mcp.controller.find_chat_window")
def test_send_message_success(mock_find, mock_child, mock_api):
    mock_find.return_value = 11111
    mock_child.return_value = 22222
    with patch.object(controller, "_ensure_foreground", return_value=True), \
            patch.object(controller, "_verify_expected_focus", return_value=True):
        result = controller.send_message_to_room("TestRoom", "Hello")
    assert result["success"] is True
    assert "sent" in result["message"].lower()


@patch("kakao_mcp.controller.find_chat_window")
def test_send_message_room_not_found(mock_find):
    mock_find.return_value = None
    result = controller.send_message_to_room("NoRoom", "Hello")
    assert result["success"] is False
    assert "not found" in result["error"]


@patch("kakao_mcp.controller.find_child_window_recursive")
@patch("kakao_mcp.controller.find_chat_window")
def test_send_message_no_edit_control(mock_find, mock_child):
    mock_find.return_value = 11111
    mock_child.return_value = None
    result = controller.send_message_to_room("TestRoom", "Hello")
    assert result["success"] is False
    assert "edit control" in result["error"].lower()


# ---------------------------------------------------------------------------
# read_chat_messages
# ---------------------------------------------------------------------------

@patch("kakao_mcp.controller._read_clipboard_text")
@patch("kakao_mcp.controller._send_ctrl_key_combo")
@patch("kakao_mcp.controller._user32")
@patch("kakao_mcp.controller.win32gui")
@patch("kakao_mcp.controller.find_child_window_recursive")
@patch("kakao_mcp.controller.find_chat_window")
def test_read_messages_success(mock_find, mock_child, mock_gui, mock_user32, mock_ctrl, mock_clip):
    mock_find.return_value = 11111
    mock_child.return_value = 33333
    mock_gui.GetWindowRect.return_value = (0, 0, 100, 100)
    mock_clip.return_value = "[Room] [대화상대 2명]\n[A] [오전 10:00] Hello"
    with patch.object(controller, "_ensure_foreground", return_value=True), \
            patch.object(controller, "_verify_expected_focus", return_value=True):
        result = controller.read_chat_messages("Room")
    assert result["success"] is True
    assert "Hello" in result["raw_text"]


@patch("kakao_mcp.controller.find_chat_window")
def test_read_messages_room_not_found(mock_find):
    mock_find.return_value = None
    result = controller.read_chat_messages("NoRoom")
    assert result["success"] is False


def test_duplicate_exact_titles_raise_instead_of_selecting_first(desktop):
    gui = desktop["gui"]
    gui.IsWindowVisible.return_value = True
    gui.GetClassName.return_value = config.KAKAO_CHAT_WINDOW_CLASS
    gui.GetWindowText.return_value = "Room"
    gui.EnumWindows.side_effect = lambda callback, _: [
        callback(100, None), callback(200, None)
    ]
    with pytest.raises(ValueError, match="Multiple open chat windows"):
        controller.find_chat_window("Room")


def test_focus_query_checks_the_other_gui_thread(desktop):
    desktop["user32"].GetForegroundWindow.return_value = 100
    desktop["gui"].IsChild.return_value = True
    desktop["process"].GetWindowThreadProcessId.return_value = (7, 99)

    def fill_focus(thread_id, info_pointer):
        assert thread_id == 7
        info = info_pointer._obj
        assert info.cbSize == controller.ctypes.sizeof(controller._GUITHREADINFO)
        info.hwndActive = 100
        info.hwndFocus = 101
        return 1

    desktop["user32"].GetGUIThreadInfo.side_effect = fill_focus
    assert controller._verify_expected_focus(100, 101) is True
    assert controller._verify_expected_focus(100, 102) is False
    desktop["user32"].keybd_event.assert_not_called()


def test_focus_query_failure_aborts(desktop):
    desktop["user32"].GetForegroundWindow.return_value = 100
    desktop["gui"].IsChild.return_value = True
    desktop["process"].GetWindowThreadProcessId.return_value = (7, 99)
    desktop["user32"].GetGUIThreadInfo.return_value = 0
    assert controller._verify_expected_focus(100, 101) is False


def test_activation_does_not_inject_alt(desktop):
    desktop["user32"].GetForegroundWindow.return_value = 999
    assert controller._ensure_foreground(100) is False
    desktop["user32"].SetForegroundWindow.assert_called_once_with(100)
    desktop["user32"].keybd_event.assert_not_called()


def test_send_failed_activation_has_no_clipboard_or_input(desktop):
    with patch.object(controller, "find_chat_window", return_value=100), \
            patch.object(controller, "find_child_window_recursive", return_value=101), \
            patch.object(controller, "_ensure_foreground", return_value=False):
        result = controller.send_message_to_room("Room", "Hello")
    assert result["success"] is False
    desktop["clipboard"].OpenClipboard.assert_not_called()
    desktop["user32"].mouse_event.assert_not_called()
    desktop["user32"].keybd_event.assert_not_called()


def test_send_wrong_editor_focus_does_not_paste(desktop):
    desktop["gui"].GetWindowRect.return_value = (0, 0, 100, 100)
    with patch.object(controller, "find_chat_window", return_value=100), \
            patch.object(controller, "find_child_window_recursive", return_value=101), \
            patch.object(controller, "_ensure_foreground", return_value=True), \
            patch.object(controller, "_verify_expected_focus", return_value=False):
        result = controller.send_message_to_room("Room", "Hello")
    assert result["success"] is False
    desktop["clipboard"].OpenClipboard.assert_not_called()
    desktop["user32"].keybd_event.assert_not_called()


def test_send_focus_lost_after_paste_never_presses_enter(desktop):
    desktop["gui"].GetWindowRect.return_value = (0, 0, 100, 100)
    with patch.object(controller, "find_chat_window", return_value=100), \
            patch.object(controller, "find_child_window_recursive", return_value=101), \
            patch.object(controller, "_ensure_foreground", return_value=True), \
            patch.object(controller, "_verify_expected_focus", side_effect=[True, False]), \
            patch.object(controller, "_send_ctrl_key_combo") as combo:
        result = controller.send_message_to_room("Room", "Hello")
    assert result["success"] is False
    assert "Enter was not sent" in result["error"]
    desktop["clipboard"].SetClipboardText.assert_called_once_with(
        "Hello", controller.win32clipboard.CF_UNICODETEXT
    )
    combo.assert_called_once_with(0x56)
    desktop["user32"].keybd_event.assert_not_called()


def test_read_wrong_control_focus_never_copies(desktop):
    desktop["gui"].GetWindowRect.return_value = (0, 0, 100, 100)
    with patch.object(controller, "find_chat_window", return_value=100), \
            patch.object(controller, "find_child_window_recursive", return_value=101), \
            patch.object(controller, "_ensure_foreground", return_value=True), \
            patch.object(controller, "_verify_expected_focus", return_value=False):
        result = controller.read_chat_messages("Room")
    assert result["success"] is False
    desktop["user32"].keybd_event.assert_not_called()
    desktop["clipboard"].OpenClipboard.assert_not_called()


@pytest.mark.parametrize("rooms", [
    [],
    [{"title": "Other", "hwnd": 200}],
    [{"title": "Room extra", "hwnd": 200}],
    [{"title": "Room", "hwnd": 200}, {"title": "Room", "hwnd": 201}],
])
def test_search_rejects_missing_partial_and_ambiguous_matches(desktop, rooms):
    with patch.object(controller, "_ensure_foreground", return_value=True), \
            patch.object(controller, "_activate_search_and_get_edit", return_value=101), \
            patch.object(controller, "_verify_expected_focus", return_value=True), \
            patch.object(controller, "list_chat_windows", return_value=rooms):
        result = controller.search_and_open_room("Room")
    assert result["success"] is False


@pytest.mark.parametrize("active", [True, False])
def test_search_exact_match_must_be_active(desktop, active):
    with patch.object(controller, "_ensure_foreground", return_value=True), \
            patch.object(controller, "_activate_search_and_get_edit", return_value=101), \
            patch.object(controller, "_verify_expected_focus", side_effect=[True, True, active]), \
            patch.object(controller, "list_chat_windows", return_value=[{"title": "Room", "hwnd": 200}]):
        result = controller.search_and_open_room("Room")
    assert result["success"] is active


def test_search_activation_failure_never_sends_input(desktop):
    with patch.object(controller, "_ensure_foreground", return_value=False):
        result = controller.search_and_open_room("Room")
    assert result["success"] is False
    desktop["api"].SendMessage.assert_not_called()
    desktop["user32"].keybd_event.assert_not_called()


def test_open_existing_room_activation_failure_is_an_error(desktop):
    from kakao_mcp.server import kakao_open_room

    with patch.object(controller, "find_chat_window", return_value=100), \
            patch.object(controller, "_ensure_foreground", return_value=False), \
            patch.object(controller, "search_and_open_room") as search:
        result = kakao_open_room("Room")
    assert "error" in result
    search.assert_not_called()


def test_open_ambiguous_room_does_not_fall_back_to_search(desktop):
    from kakao_mcp.server import kakao_open_room

    with patch.object(controller, "find_chat_window", side_effect=ValueError("Ambiguous room")), \
            patch.object(controller, "search_and_open_room") as search:
        result = kakao_open_room("Room")
    assert "error" in result
    search.assert_not_called()
