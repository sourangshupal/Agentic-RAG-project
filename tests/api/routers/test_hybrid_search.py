import pytest


async def test_search_endpoint_basic(client):
    response = await client.post("/api/v1/hybrid-search/", json={"query": "neural networks", "size": 5})

    assert response.status_code == 200
    data = response.json()

    assert "query" in data
    assert "total" in data
    assert "hits" in data
    assert "size" in data
    assert "from" in data

    assert data["query"] == "neural networks"
    assert isinstance(data["total"], int)
    assert isinstance(data["hits"], list)


async def test_search_endpoint_with_latest_papers(client):
    response = await client.post(
        "/api/v1/hybrid-search/", json={"query": "machine learning", "size": 3, "latest_papers": True, "use_hybrid": False}
    )

    assert response.status_code == 200
    data = response.json()

    assert data["query"] == "machine learning"


async def test_search_endpoint_with_categories(client):
    response = await client.post(
        "/api/v1/hybrid-search/",
        json={"query": "deep learning", "size": 5, "categories": ["cs.AI", "cs.LG"], "latest_papers": False, "use_hybrid": False},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["query"] == "deep learning"


async def test_search_endpoint_validation_errors(client):
    response = await client.post("/api/v1/hybrid-search/", json={"query": ""})
    assert response.status_code == 422

    response = await client.post("/api/v1/hybrid-search/", json={"query": "test", "size": 0})
    assert response.status_code == 422

    response = await client.post("/api/v1/hybrid-search/", json={"size": 10})
    assert response.status_code == 422


async def test_search_endpoint_pagination(client):
    response = await client.post("/api/v1/hybrid-search/", json={"query": "artificial intelligence", "size": 5, "from": 10})

    assert response.status_code == 200
    data = response.json()

    assert data["query"] == "artificial intelligence"


async def test_search_endpoint_all_parameters(client):
    response = await client.post(
        "/api/v1/hybrid-search/",
        json={
            "query": "transformers attention mechanism",
            "size": 8,
            "from": 5,
            "categories": ["cs.AI"],
            "latest_papers": True,
            "use_hybrid": False,
        },
    )

    assert response.status_code == 200
    data = response.json()

    assert data["query"] == "transformers attention mechanism"
    assert isinstance(data["total"], int)
    assert isinstance(data["hits"], list)

    for hit in data["hits"]:
        assert "arxiv_id" in hit
        assert "title" in hit
        assert "score" in hit
