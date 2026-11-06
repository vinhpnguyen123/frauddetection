from app.main import create_app


def test_create_app_returns_named_app() -> None:
    assert create_app().title == "FinbudAI"
