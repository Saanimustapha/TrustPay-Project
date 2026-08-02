import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient):
    payload = {
        "email": "alice@example.com",
        "password": "SuperSecurePass123!",
        "full_name": "Alice Example",
    }
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "alice@example.com"
    assert data["full_name"] == "Alice Example"
    assert data["is_active"] is True
    assert data["kyc_status"] == "pending"
    assert "id" in data


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient):
    payload = {
        "email": "bob@example.com",
        "password": "SuperSecurePass123!",
    }
    await client.post("/api/v1/auth/register", json=payload)
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    # First register
    await client.post(
        "/api/v1/auth/register",
        json={"email": "carol@example.com", "password": "SuperSecurePass123!"},
    )
    # Then login
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": "carol@example.com", "password": "SuperSecurePass123!"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "dave@example.com", "password": "SuperSecurePass123!"},
    )
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": "dave@example.com", "password": "WrongPassword!"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_endpoint(client: AsyncClient):
    # Register + login
    await client.post(
        "/api/v1/auth/register",
        json={"email": "eve@example.com", "password": "SuperSecurePass123!"},
    )
    login_resp = await client.post(
        "/api/v1/auth/login",
        data={"username": "eve@example.com", "password": "SuperSecurePass123!"},
    )
    token = login_resp.json()["access_token"]

    response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["email"] == "eve@example.com"