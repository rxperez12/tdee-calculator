from unittest.mock import MagicMock

import pytest

import tdee_calculator


def test_open_browser_when_server_responds(monkeypatch) -> None:
    response = MagicMock()
    response.__enter__.return_value = response
    open_browser = MagicMock()
    monkeypatch.setattr(
        tdee_calculator.request, "urlopen", lambda *args, **kwargs: response
    )
    monkeypatch.setattr(tdee_calculator.webbrowser, "open", open_browser)

    tdee_calculator._open_browser_when_ready("http://127.0.0.1:8000")

    open_browser.assert_called_once_with("http://127.0.0.1:8000")


@pytest.mark.parametrize("no_browser", [True, False])
def test_main_prepares_before_starting_server(monkeypatch, config, no_browser) -> None:
    calls = []
    app = object()
    monkeypatch.setenv("TDEE_NO_BROWSER", "1" if no_browser else "0")
    thread = MagicMock()
    monkeypatch.setattr(tdee_calculator.threading, "Thread", thread)
    monkeypatch.setattr(tdee_calculator, "load_config", lambda: config)
    monkeypatch.setattr(
        tdee_calculator, "prepare", lambda current: calls.append(("prepare", current))
    )
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
    if no_browser:
        thread.assert_not_called()
    else:
        thread.assert_called_once_with(
            target=tdee_calculator._open_browser_when_ready,
            args=(f"http://{config.host}:{config.port}",),
            daemon=True,
        )
        thread.return_value.start.assert_called_once_with()


def test_open_browser_timeout_prints_manual_url(monkeypatch, capsys) -> None:
    open_browser = MagicMock()
    monkeypatch.setattr(tdee_calculator.webbrowser, "open", open_browser)

    tdee_calculator._open_browser_when_ready("http://127.0.0.1:8000", timeout=0)

    assert capsys.readouterr().err == "Open http://127.0.0.1:8000 in your browser.\n"
    open_browser.assert_not_called()


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
