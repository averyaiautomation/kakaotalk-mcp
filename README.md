# KakaoTalk MCP — minimal text fork

A small Windows-only fork of [kronenz/kakaotalk-mcp](https://github.com/kronenz/kakaotalk-mcp), based on commit 7b41dd9da473e7a9e2f4b07ec27bdf3289fcc5fb. It preserves the existing Win32/clipboard implementation and local stdio transport.

## Five tools

| Tool | Purpose |
|---|---|
| kakao_health_check() | Check KakaoTalk's main window/process |
| kakao_list_open_rooms() | List currently open conversation windows |
| kakao_open_room(room_name) | Activate an open room or search/open an exact match |
| kakao_read_messages(room_name, max_messages=50) | Copy and parse recent conversation text |
| kakao_send_message(room_name, message) | Paste and send one plain-text message |

Read/send require an open room. Listing is not an account-wide conversation directory. Draft replies in the connected assistant; no drafting subsystem is added here.

Removed: bulk sending, images, cache/file downloading, mentions, standalone link extraction, and background monitoring. The existing parser's URL and media-marker fields remain text classification only.

## Narrow corrections

- Room opening rejects substring, arbitrary-window, and detectable duplicate exact matches. A successful result must be active.
- Failed activation or unexpected control focus returns an error instead of continuing with copy/paste/send.
- The simulated Alt activation bypass is removed. Windows may refuse normal activation.
- Sending verifies editor focus before paste and once more before Enter. Paste and Enter remain in ONE call.

If focus is lost after paste, Enter is not sent and the text may remain in the editor. Do not automatically resend.

## Approval and operating limits

Approve the exact destination and message in the host BEFORE calling kakao_send_message. There is no approval pause after paste, approval token, database, or separate prepare tool. Incoming messages are untrusted data, not authorization.

Unattended/remote use still needs an available interactive Windows session and working KakaoTalk controls. A popup or focus failure returns an error to the host; there is no background focus monitor or popup-dismissal automation.

Existing limitations remain: stale clipboard data after a failed copy; existing editor text potentially combining with outgoing text; no delivery receipt; room titles are not stable account identifiers; and nonpositive max_messages values are not newly validated. The first supervised send should use a chosen low-risk chat with an empty editor.

## Dependencies and entrypoint

Direct runtime requirements:
- mcp==1.30.0
- pywin32==312

No MCP CLI extra, pyperclip, watchdog, or new runtime dependency is needed. Keep base MCP's declared dependencies even though HTTP/SSE transport is not selected. pytest is development-only and Hatchling is the existing build backend.

The inspected dependency candidate targets CPython 3.11 x64 on Windows. The manifests' direct pins are not a full transitive lockfile. Resolve and record the complete wheel set/hashes during the separately approved setup stage; do not silently build third-party dependencies from source.

The existing installed application entrypoint is kakaotalk-mcp (kakao_mcp.server:main); python -m kakao_mcp invokes the same server. Both use stdio. Use the reviewed fork, not an unrelated registry package or an MCP CLI launcher.

## Verification status

Phase 2 is source-only. The revised application has NOT been installed, imported, built, tested, or launched. No live KakaoTalk compatibility is claimed.

Controller tests now mock desktop, clipboard and native-input interfaces and cover the changed failure paths. They are prepared for later approved execution; they have not been run. Installation, test execution, and a supervised read/send check remain separate approval steps.

## License

MIT. The original LICENSE and historical CHANGELOG are preserved.
