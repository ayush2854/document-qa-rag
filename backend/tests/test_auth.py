def test_signup_creates_user(client):
    response = client.post("/signup", json={"email": "test@example.com", "password": "testpass123"})
    data = response.json()
    assert response.status_code == 200
    assert "token" in data
    assert data["email"] == "test@example.com"

def test_signup_duplicate_email_fails(client):
    client.post("/signup", json={"email": "dupe@example.com", "password": "testpass123"})
    response = client.post("/signup", json={"email": "dupe@example.com", "password": "differentpass"})
    data = response.json()
    assert "error" in data
    assert "already exists" in data["error"]

def test_login_success(client):
    client.post("/signup", json={"email": "login@example.com", "password": "testpass123"})
    response = client.post("/login", json={"email": "login@example.com", "password": "testpass123"})
    data = response.json()
    assert response.status_code == 200
    assert "token" in data

def test_login_wrong_password_fails(client):
    client.post("/signup", json={"email": "wrongpass@example.com", "password": "correctpass"})
    response = client.post("/login", json={"email": "wrongpass@example.com", "password": "wrongpass"})
    data = response.json()
    assert "error" in data

def test_login_nonexistent_user_fails(client):
    response = client.post("/login", json={"email": "doesnotexist@example.com", "password": "anything"})
    data = response.json()
    assert "error" in data

def test_protected_endpoint_without_token_returns_401(client):
    response = client.get("/documents?mode=cloud")
    assert response.status_code == 401

def test_protected_endpoint_with_valid_token_succeeds(client):
    signup_response = client.post("/signup", json={"email": "protected@example.com", "password": "testpass123"})
    token = signup_response.json()["token"]

    response = client.get("/documents?mode=cloud", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json() == {"documents": []}