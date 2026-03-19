from __future__ import annotations

from pathlib import Path

from foundrygate.wizard import (
    build_initial_config,
    detect_wizard_providers,
    render_initial_config_yaml,
)


def test_detect_wizard_providers_uses_env_file(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "DEEPSEEK_API_KEY=sk-demo",
                "OPENAI_API_KEY=sk-openai",
                "ANTHROPIC_API_KEY=sk-anthropic",
            ]
        ),
        encoding="utf-8",
    )

    assert detect_wizard_providers(env_file=env_file) == [
        "deepseek-chat",
        "deepseek-reasoner",
        "openai-gpt4o",
        "openai-images",
        "anthropic-claude",
    ]


def test_build_initial_config_adds_modes_shortcuts_and_profile_defaults(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "DEEPSEEK_API_KEY=sk-demo",
                "GEMINI_API_KEY=gm-demo",
                "OPENROUTER_API_KEY=or-demo",
                "KILOCODE_API_KEY=kilo-demo",
                "BLACKBOX_API_KEY=bb-demo",
            ]
        ),
        encoding="utf-8",
    )

    config = build_initial_config(env_file=env_file, purpose="free")

    assert config["routing_modes"]["enabled"] is True
    assert config["routing_modes"]["default"] == "free"
    assert "free" in config["routing_modes"]["modes"]
    assert config["model_shortcuts"]["enabled"] is True
    assert config["model_shortcuts"]["shortcuts"]["deepseek-chat"]["target"] == "deepseek-chat"
    assert config["client_profiles"]["profiles"]["n8n"]["routing_mode"] == "eco"
    assert config["client_profiles"]["profiles"]["opencode"]["routing_mode"] == "auto"
    assert config["fallback_chain"][0] == "kilocode"


def test_render_initial_config_yaml_includes_custom_sections(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=sk-openai\n", encoding="utf-8")

    rendered = render_initial_config_yaml(env_file=env_file, purpose="quality")

    assert "routing_modes:" in rendered
    assert "model_shortcuts:" in rendered
    assert "openai-images:" in rendered
    assert "default: premium" in rendered
