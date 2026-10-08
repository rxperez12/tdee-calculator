from unittest.mock import MagicMock

import tdee_calculator


def test_open_browser_when_server_responds(monkeypatch) -> None:
    response = MagicMock()
    response.__enter__.return_value = response
    open_browser = MagicMock()
    monkeypatch.setattr(tdee_calculator.request, "urlopen", lambda *args, **kwargs: response)
    monkeypatch.setattr(tdee_calculator.webbrowser, "open", open_browser)

    tdee_calculator._open_browser_when_ready("http://127.0.0.1:8000")

    open_browser.assert_called_once_with("http://127.0.0.1:8000")


def test_main_prepares_before_starting_server(monkeypatch, config) -> None:
    calls = []
    app = object()
    monkeypatch.setenv("TDEE_NO_BROWSER", "1")
    monkeypatch.setattr(tdee_calculator, "load_config", lambda: config)
    monkeypatch.setattr(tdee_calculator, "prepare", lambda current: calls.append(("prepare", current)))
    monkeypatch.setattr(tdee_calculator, "create_app", lambda current: app)
    monkeypatch.setattr(
        tdee_calculator.uvicorn,
        "run",
        lambda current, **options: calls.append(("run", current, options)),
    )

    tdee_calculator.main()

    assert calls == [
        ("prepare", config),
        ("run", app, {"host": config.host, "port": config.port}),
    ]


def test_open_browser_retries_after_connection_reset(monkeypatch) -> None:
    response = MagicMock()
    response.__enter__.return_value = response
    attempts = iter([ConnectionResetError(), response])
    open_browser = MagicMock()

    def urlopen(*args, **kwargs):
        result = next(attempts)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(tdee_calculator.request, "urlopen", urlopen)
    monkeypatch.setattr(tdee_calculator.webbrowser, "open", open_browser)

    tdee_calculator._open_browser_when_ready("http://127.0.0.1:8000", poll_interval=0)

    open_browser.assert_called_once_with("http://127.0.0.1:8000")
