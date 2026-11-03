"""Pruebas de la configuración del Analysis Worker (contrato, sección 17.5)."""

from __future__ import annotations

import pytest

from app.config import Settings

ENV_NAMES = (
    "PORT",
    "LOG_LEVEL",
    "GATEWAY_INTERNAL_URL",
    "RABBITMQ_URL",
    "MONGO_ANALYSIS_URL",
    "MONGO_ANALYSIS_DATABASE",
    "ANALYSIS_DEPTH_MAX",
    "ANALYSIS_MAX_RETRIES",
    "ANALYSIS_INACCURACY_CP",
    "ANALYSIS_MISTAKE_CP",
    "ANALYSIS_BLUNDER_CP",
    "POLL_INTERVAL_SECONDS",
    "ANALYSIS_STALE_MINUTES",
    "HTTP_TIMEOUT",
    "WORKER_ID",
)


@pytest.fixture
def clean_env(monkeypatch):
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_contract_defaults(clean_env):
    settings = Settings.from_env()

    assert settings.port == 8089
    assert settings.gateway_internal_url == "http://api-gateway-component:8080"
    assert settings.mongo_analysis_database == "insightful_analysis"
    assert settings.rabbitmq_url == "amqp://guest:guest@rabbitmq:5672/"
    assert settings.analysis_depth_max == 18
    assert settings.analysis_max_retries == 5
    assert settings.analysis_inaccuracy_cp == 50
    assert settings.analysis_mistake_cp == 100
    assert settings.analysis_blunder_cp == 300
    assert settings.poll_interval_seconds == 5.0
    assert settings.analysis_stale_minutes == 5.0
    assert settings.http_timeout == 15.0
    assert settings.log_level == "INFO"
    assert settings.worker_id


def test_environment_overrides(clean_env):
    clean_env.setenv("PORT", "9000")
    clean_env.setenv("LOG_LEVEL", "debug")
    clean_env.setenv("GATEWAY_INTERNAL_URL", "http://gateway.test/")
    clean_env.setenv("MONGO_ANALYSIS_URL", "mongodb://mongo.test:27017")
    clean_env.setenv("MONGO_ANALYSIS_DATABASE", "analysis_test")
    clean_env.setenv("RABBITMQ_URL", "amqp://guest:guest@rabbit.test:5672/")
    clean_env.setenv("ANALYSIS_DEPTH_MAX", "20")
    clean_env.setenv("ANALYSIS_MAX_RETRIES", "7")
    clean_env.setenv("ANALYSIS_INACCURACY_CP", "40")
    clean_env.setenv("ANALYSIS_MISTAKE_CP", "90")
    clean_env.setenv("ANALYSIS_BLUNDER_CP", "250")
    clean_env.setenv("POLL_INTERVAL_SECONDS", "2.5")
    clean_env.setenv("ANALYSIS_STALE_MINUTES", "9")
    clean_env.setenv("HTTP_TIMEOUT", "7.5")
    clean_env.setenv("WORKER_ID", "worker-1")

    settings = Settings.from_env()

    assert settings.port == 9000
    assert settings.log_level == "DEBUG"
    assert settings.gateway_internal_url == "http://gateway.test"
    assert settings.mongo_analysis_url == "mongodb://mongo.test:27017"
    assert settings.mongo_analysis_database == "analysis_test"
    assert settings.rabbitmq_url == "amqp://guest:guest@rabbit.test:5672/"
    assert settings.analysis_depth_max == 20
    assert settings.analysis_max_retries == 7
    assert settings.analysis_inaccuracy_cp == 40
    assert settings.analysis_mistake_cp == 90
    assert settings.analysis_blunder_cp == 250
    assert settings.poll_interval_seconds == 2.5
    assert settings.analysis_stale_minutes == 9.0
    assert settings.http_timeout == 7.5
    assert settings.worker_id == "worker-1"


def test_blank_values_fall_back_to_defaults(clean_env):
    clean_env.setenv("PORT", "   ")
    clean_env.setenv("WORKER_ID", "   ")

    settings = Settings.from_env()

    assert settings.port == 8089
    assert settings.worker_id


def test_renewal_interval_is_one_third_of_the_lease(clean_env):
    clean_env.setenv("ANALYSIS_STALE_MINUTES", "9")

    settings = Settings.from_env()

    assert settings.stale_seconds == 540.0
    assert settings.renewal_interval_seconds == 180.0


@pytest.mark.parametrize(
    "name,value",
    [
        ("PORT", "0"),
        ("PORT", "70000"),
        ("ANALYSIS_DEPTH_MAX", "0"),
        ("ANALYSIS_MAX_RETRIES", "0"),
        ("POLL_INTERVAL_SECONDS", "0"),
        ("ANALYSIS_STALE_MINUTES", "0"),
        ("HTTP_TIMEOUT", "0"),
    ],
)
def test_invalid_numeric_values_are_rejected(clean_env, name, value):
    clean_env.setenv(name, value)

    with pytest.raises(ValueError):
        Settings.from_env()


@pytest.mark.parametrize(
    "name,value",
    [
        ("PORT", "no-es-numero"),
        ("POLL_INTERVAL_SECONDS", "no-es-numero"),
    ],
)
def test_non_numeric_values_are_rejected(clean_env, name, value):
    clean_env.setenv(name, value)

    with pytest.raises(ValueError):
        Settings.from_env()


@pytest.mark.parametrize(
    "inaccuracy,mistake,blunder",
    [
        ("50", "50", "300"),
        ("100", "50", "300"),
        ("50", "300", "100"),
        ("-1", "100", "300"),
    ],
)
def test_inconsistent_thresholds_are_rejected(
    clean_env, inaccuracy, mistake, blunder
):
    clean_env.setenv("ANALYSIS_INACCURACY_CP", inaccuracy)
    clean_env.setenv("ANALYSIS_MISTAKE_CP", mistake)
    clean_env.setenv("ANALYSIS_BLUNDER_CP", blunder)

    with pytest.raises(ValueError):
        Settings.from_env()
