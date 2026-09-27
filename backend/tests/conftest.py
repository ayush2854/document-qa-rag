import os
import io
import pytest
from dotenv import load_dotenv
from reportlab.pdfgen import canvas

load_dotenv()
os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]

from fastapi.testclient import TestClient
from main import app, db_engine
from sqlalchemy import text

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture(autouse=True)
def clean_database():
    yield
    with db_engine.connect() as conn:
        conn.execute(text("DELETE FROM chat_history"))
        conn.execute(text("DELETE FROM conversations"))
        conn.execute(text("DELETE FROM chunks_cloud"))
        conn.execute(text("DELETE FROM chunks_local"))
        conn.execute(text("DELETE FROM users"))
        conn.commit()

@pytest.fixture
def sample_pdf_bytes():
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer)
    c.drawString(100, 750, "This is a test document about key-value stores.")
    c.save()
    buffer.seek(0)
    return buffer.read()

@pytest.fixture
def auth_headers(client):
    response = client.post("/signup", json={"email": "fixture_user@example.com", "password": "testpass123"})
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}