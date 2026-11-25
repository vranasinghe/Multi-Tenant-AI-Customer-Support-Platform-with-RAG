import pytest

from app.services.widget_domains import origin


@pytest.mark.parametrize(
    "value",
    [
        "https://*.test",
        "https://example.com/path",
        "https://user:pass@example.com",
        "https://example.com;evil",
        "http://example.com",
        "https://127.0.0.1",
        "https://example.com?x=1",
    ],
)
def test_bad_origins_rejected(value: str) -> None:
    with pytest.raises(ValueError, match=r"."):
        origin(value)


def test_canonical_origin() -> None:
    assert origin("https://EXAMPLE.com:443/") == "https://example.com"
    assert origin("http://localhost:3000", True) == "http://localhost:3000"
