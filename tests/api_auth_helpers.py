from fastapi.testclient import TestClient


def register_and_auth(client: TestClient, username: str = "alice") -> dict[str, str]:
    response = client.post("/auth/register", json={"username": username, "password": "password123"})
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['token']}"}


def create_authenticated_session(client: TestClient, username: str = "alice") -> tuple[dict[str, str], str]:
    headers = register_and_auth(client, username)
    response = client.post("/sessions", headers=headers)
    assert response.status_code == 201
    return headers, response.json()["session"]["session_id"]
