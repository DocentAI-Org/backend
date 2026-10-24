from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.errors import ApiError, register_error_handlers
from app.core.pagination import Page, Pagination


class Item(BaseModel):
    value: int


def _app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/boom")
    def boom() -> None:
        raise ApiError(409, "topic_name_taken", "Duplicate.", {"name": "x"})

    @app.get("/items")
    def items(page: Pagination) -> Page[Item]:
        values = list(range(50))[page.offset : page.offset + page.limit]
        return Page[Item](
            items=[Item(value=v) for v in values],
            total=50,
            limit=page.limit,
            offset=page.offset,
        )

    return app


def test_api_error_uses_the_single_error_schema() -> None:
    response = TestClient(_app()).get("/boom")

    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "topic_name_taken",
            "message": "Duplicate.",
            "details": {"name": "x"},
        }
    }


def test_unknown_route_and_validation_errors_use_codes() -> None:
    client = TestClient(_app())

    assert client.get("/missing").json()["error"]["code"] == "not_found"
    invalid = client.get("/items?limit=500")
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "validation_error"
    assert invalid.json()["error"]["details"]["fields"][0]["loc"] == ["query", "limit"]


def test_pagination_defaults_and_bounds() -> None:
    body = TestClient(_app()).get("/items?offset=45").json()

    assert body["limit"] == 20
    assert body["offset"] == 45
    assert body["total"] == 50
    assert [item["value"] for item in body["items"]] == [45, 46, 47, 48, 49]
