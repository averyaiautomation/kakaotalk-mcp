"""Central configuration for KakaoTalk MCP Server."""

# KakaoTalk window class names
KAKAO_MAIN_WINDOW_CLASS = "EVA_Window_Dblclk"
KAKAO_MAIN_WINDOW_TITLE = "카카오톡"
KAKAO_CHAT_WINDOW_CLASS = "EVA_Window_Dblclk"
KAKAO_LIST_CONTROL_CLASS = "EVA_VH_ListControl_Dblclk"
KAKAO_EDIT_CLASS = "RICHEDIT50W"

# Win32 message constants
WM_CHAR = 0x0102
VK_RETURN = 0x0D
VK_CONTROL = 0x11
VK_A = 0x41
VK_C = 0x43
KEYEVENTF_KEYUP = 0x0002

# Timeouts and intervals
CLIPBOARD_MAX_RETRIES = 5
CLIPBOARD_RETRY_INTERVAL_SEC = 0.1
KEY_COMBO_WAIT_SEC = 0.15  # Was 0.3 — Ctrl+A/C combo wait

# Window and focus timing
WINDOW_ACTIVATE_WAIT_SEC = 0.15  # Was 0.2 — after bring_window_to_front
EDIT_CLICK_WAIT_SEC = 0.08  # Was 0.1 — after clicking edit control
CLIPBOARD_PASTE_WAIT_SEC = 0.03  # Was 0.05 — after clipboard set, before Ctrl+V
AFTER_PASTE_WAIT_SEC = 0.05  # Was 0.1 — after Ctrl+V, before Enter

# Search and open room timing
SEARCH_ACTIVATE_WAIT_SEC = 0.3  # Was 0.5 — after Ctrl+F
SEARCH_CHAR_INTERVAL_SEC = 0.02  # Per-character typing delay
SEARCH_RESULTS_WAIT_SEC = 0.8  # Was 1.5 — wait for search results
SEARCH_OPEN_WAIT_SEC = 0.5  # Was 1.0 — after Enter to open room
