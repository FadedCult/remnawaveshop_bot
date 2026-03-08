from app.web.app import create_web_app


def test_create_app():
    app = create_web_app()
    assert app is not None

