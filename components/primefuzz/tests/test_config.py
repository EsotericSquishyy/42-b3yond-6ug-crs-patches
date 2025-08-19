import os
import pytest
from pathlib import Path
from modules.config import Config

@pytest.fixture
def mock_env_with_database_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", 
        "postgresql://jPbQIckk:Jt-N%2BP2erV%3D%7B2fvV@b3yond-postgres-dev.postgres.database.azure.com:5432/b3yond-db-dev")

@pytest.fixture
def mock_env_with_individual_vars(monkeypatch):
    monkeypatch.setenv("PG_CONNECTION_STRING", "postgresql://localhost:5432/testdb")
    monkeypatch.setenv("PG_USER", "test_user")
    monkeypatch.setenv("PG_PASSWORD", "test_pass")

def test_parse_database_url():
    url = "postgresql://jPbQIckk:Jt-N%2BP2erV%3D%7B2fvV@b3yond-postgres-dev.postgres.database.azure.com:5432/b3yond-db-dev"
    conn_string, user, password = Config.parse_database_url(url)
    
    assert "b3yond-postgres-dev.postgres.database.azure.com:5432/b3yond-db-dev" in conn_string
    assert user == "jPbQIckk"
    assert password == "Jt-N%2BP2erV%3D%7B2fvV"

def test_config_from_env_with_database_url(mock_env_with_database_url):
    config = Config.from_env()
    
    assert "b3yond-postgres-dev.postgres.database.azure.com" in config.pg_connection_string
    assert config.pg_user == "jPbQIckk"
    assert config.pg_password == "Jt-N%2BP2erV%3D%7B2fvV"

def test_config_from_env_with_individual_vars(mock_env_with_individual_vars):
    config = Config.from_env()
    
    assert config.pg_connection_string == "postgresql://localhost:5432/testdb"
    assert config.pg_user == "test_user"
    assert config.pg_password == "test_pass"

def test_config_default_values():
    config = Config.from_env()
    
    assert config.rabbitmq_host == "localhost"
    assert config.rabbitmq_port == 5672
    assert config.queue_name == "general_fuzzing_queue"
    assert config.oss_fuzz_path == Path("./fuzz-tooling")
    assert config.metrics_interval == 60