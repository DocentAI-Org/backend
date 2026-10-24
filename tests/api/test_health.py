def test_health_reports_service_database_and_llm(client, llm) -> None:
    response = client.get("/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "DocentAI API"
    assert body["database"] == "ok"
    assert body["llm"] == "ok"


def test_health_reports_unreachable_llm_as_degraded(client, llm) -> None:
    llm.reachable = False

    body = client.get("/v1/health").json()

    assert body["llm"] == "error"
    assert body["status"] == "degraded"


def test_old_unversioned_endpoints_are_gone(client) -> None:
    assert client.get("/health").status_code == 404
    assert client.post("/chat", json={"message": "hola"}).status_code == 404
