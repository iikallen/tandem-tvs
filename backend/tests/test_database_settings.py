from config.settings.base import database_config, postgres_config


def test_database_url_decodes_credentials_and_preserves_options():
    config = database_config(
        "postgresql://user%40tenant:p%40ss@db.example:5433/tandem%2Ddb"
        "?sslmode=require&options=-csearch_path%3Dportal"
    )

    assert config == {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "tandem-db",
        "USER": "user@tenant",
        "PASSWORD": "p@ss",
        "HOST": "db.example",
        "PORT": "5433",
        "CONN_MAX_AGE": 60,
        "OPTIONS": {"sslmode": "require", "options": "-csearch_path=portal"},
    }


def test_separate_postgres_settings_preserve_reserved_password_characters():
    config = postgres_config(
        name="tandem",
        user="portal-user",
        password="p@ss:/%word",
        host="postgres",
        port="5432",
    )

    assert config["PASSWORD"] == "p@ss:/%word"
