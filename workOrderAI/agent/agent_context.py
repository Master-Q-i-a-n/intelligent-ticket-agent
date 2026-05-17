from contextvars import ContextVar


_current_username = ContextVar("current_username", default="")
_tool_trace = ContextVar("tool_trace", default=None)


def set_current_username(username: str | None):
    return _current_username.set(str(username or "").strip())


def reset_current_username(token) -> None:
    _current_username.reset(token)


def get_current_username_value() -> str:
    return _current_username.get() or ""


def start_tool_trace():
    return _tool_trace.set([])


def reset_tool_trace(token) -> None:
    _tool_trace.reset(token)


def record_tool_call(name: str, args: dict | None, output: object = "") -> None:
    trace = _tool_trace.get()
    if trace is None:
        return
    trace.append(
        {
            "name": str(name or ""),
            "args": dict(args or {}),
            "output": _normalize_tool_output(output),
        }
    )


def get_tool_trace() -> list[dict]:
    trace = _tool_trace.get()
    return list(trace or [])


def _normalize_tool_output(output: object) -> str:
    content = getattr(output, "content", output)
    if content is None:
        return ""
    return str(content)
