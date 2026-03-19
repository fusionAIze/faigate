from __future__ import annotations

import runpy
import sys

import pytest

import faigate.main as main_module


def test_main_uses_explicit_config_arg(monkeypatch):
    captured: dict[str, object] = {}

    def _fake_load_config():
        class _Cfg:
            server = {"host": "127.0.0.1", "port": 9011, "log_level": "warning"}

        captured["config_env"] = main_module.os.environ.get("FAIGATE_CONFIG_FILE")
        return _Cfg()

    def _fake_uvicorn_run(app, **kwargs):
        captured["app"] = app
        captured["kwargs"] = kwargs

    monkeypatch.setattr(main_module, "load_config", _fake_load_config)
    monkeypatch.setattr("uvicorn.run", _fake_uvicorn_run)
    monkeypatch.setattr(main_module, "__version__", "1.1.0-test")
    monkeypatch.setattr(
        main_module.argparse.ArgumentParser,
        "parse_args",
        lambda self: type("Args", (), {"config": "/tmp/faigate-config.yaml"})(),
    )

    main_module.main()

    assert captured["config_env"] == "/tmp/faigate-config.yaml"
    assert captured["app"] == "faigate.main:app"
    assert captured["kwargs"] == {
        "host": "127.0.0.1",
        "port": 9011,
        "log_level": "warning",
        "reload": False,
    }


def test_main_supports_version_flag(monkeypatch, capsys):
    monkeypatch.setattr(main_module, "__version__", "1.2.3")

    parser_parse_args = main_module.argparse.ArgumentParser.parse_args

    def _parse_args(self):
        return parser_parse_args(self, ["--version"])

    monkeypatch.setattr(main_module.argparse.ArgumentParser, "parse_args", _parse_args)

    with pytest.raises(SystemExit) as exc:
        main_module.main()

    assert exc.value.code == 0
    assert "1.2.3" in capsys.readouterr().out


def test_main_module_executes_main(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["faigate", "--version"])

    with pytest.raises(SystemExit) as exc:
        runpy.run_module("faigate.main", run_name="__main__")

    assert exc.value.code == 0
    assert "faigate" in capsys.readouterr().out
