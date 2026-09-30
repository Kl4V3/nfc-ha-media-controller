"""
Unit tests for Version 0.4.0 UI/UX modern redesign, Dual-Theme system, and ENVIRONMENT configuration.
"""

import os
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from app import __version__
from app.config import AppConfig, ServerConfig, load_config
from app.main import app

client = TestClient(app)


def test_v40_version():
    """Verify system version is bumped to 0.4.0."""
    assert __version__ == "0.4.0"


def test_v40_config_environment_defaults():
    """Verify environment default is 'production' and is_debug_mode is False by default."""
    cfg = AppConfig()
    assert cfg.server.environment == "production"
    assert cfg.server.log_level == "INFO"
    assert cfg.is_debug_mode is False


def test_v40_config_is_debug_mode_detection():
    """Verify is_debug_mode returns True under various test/debug conditions."""
    # 1. Environment set to test
    cfg_test = AppConfig(server=ServerConfig(environment="test"))
    assert cfg_test.is_debug_mode is True

    # 2. Log level set to DEBUG
    cfg_debug = AppConfig(server=ServerConfig(log_level="DEBUG"))
    assert cfg_debug.is_debug_mode is True

    # 3. Environment set to dev or debug
    cfg_dev = AppConfig(server=ServerConfig(environment="dev"))
    assert cfg_dev.is_debug_mode is True

    # 4. OS env DEBUG=true
    with patch.dict(os.environ, {"DEBUG": "true"}):
        cfg_env = AppConfig()
        assert cfg_env.is_debug_mode is True


def test_v40_load_config_environment_override():
    """Verify ENVIRONMENT env var overrides server.environment."""
    with patch.dict(os.environ, {"ENVIRONMENT": "test"}):
        cfg = load_config()
        assert cfg.server.environment == "test"
        assert cfg.is_debug_mode is True


def test_v40_index_page_elements_production():
    """Verify index template in production contains modern UI/UX components."""
    with patch.object(app.state.config, "server", ServerConfig(environment="production", log_level="INFO")):
        resp = client.get("/")
        assert resp.status_code == 200
        html = resp.text

        # Font verification: Ubuntu & JetBrains Mono
        assert "family=Ubuntu" in html
        assert "family=JetBrains+Mono" in html

        # Theme & Container verification
        assert 'data-env="production"' in html
        assert "class=\"dark\"" in html or "class=\"dark \"" in html or "class=\"dark\"" in html
        assert "TEST / DEBUG MODE" not in html
        assert "id=\"btn-theme-toggle\"" in html
        assert "id=\"mobile-fab\"" in html
        assert "id=\"tags-mobile-list\"" in html
        assert "id=\"readers-mobile-list\"" in html
        assert "id=\"live-scan-banner\"" in html


def test_v40_index_page_elements_test_mode():
    """Verify index template in test mode activates Crimson Noir debug markers."""
    with patch.object(app.state.config, "server", ServerConfig(environment="test", log_level="DEBUG")):
        resp = client.get("/")
        assert resp.status_code == 200
        html = resp.text

        # Debug mode markers
        assert 'data-env="test"' in html
        assert "debug-mode" in html
        assert "TEST / DEBUG MODE" in html
