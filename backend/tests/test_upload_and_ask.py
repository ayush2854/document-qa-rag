def fake_get_embedding(text, mode):
    dimension = 768 if mode == "local" else 3072
    return [0.1] * dimension

def fake_generate_answer(prompt, mode):
    return "This is a mocked answer for testing."


def test_upload_rejects_non_pdf(client, auth_headers):
    response = client.post(
        "/upload",
        files={"file": ("test.txt", b"hello world", "text/plain")},
        data={"mode": "cloud"},
        headers=auth_headers,
    )
    data = response.json()
    assert "error" in data
    assert "PDF" in data["error"]


def test_upload_pdf_succeeds(client, auth_headers, monkeypatch, sample_pdf_bytes):
    monkeypatch.setattr("main.get_embedding", fake_get_embedding)

    response = client.post(
        "/upload",
        files={"file": ("sample.pdf", sample_pdf_bytes, "application/pdf")},
        data={"mode": "cloud"},
        headers=auth_headers,
    )
    data = response.json()
    assert response.status_code == 200
    assert data["num_chunks"] > 0
    assert data["filename"] == "sample.pdf"


def test_ask_without_any_documents_returns_helpful_message(client, auth_headers, monkeypatch):
    monkeypatch.setattr("main.get_embedding", fake_get_embedding)

    conv_response = client.post("/conversations", headers=auth_headers)
    conversation_id = conv_response.json()["id"]

    response = client.post(
        "/ask",
        json={"query": "anything", "history": [], "mode": "cloud", "conversation_id": conversation_id},
        headers=auth_headers,
    )
    data = response.json()
    assert "No documents" in data["answer"]


def test_ask_after_upload_returns_grounded_answer(client, auth_headers, monkeypatch, sample_pdf_bytes):
    monkeypatch.setattr("main.get_embedding", fake_get_embedding)
    monkeypatch.setattr("main.generate_answer", fake_generate_answer)

    upload_response = client.post(
        "/upload",
        files={"file": ("sample.pdf", sample_pdf_bytes, "application/pdf")},
        data={"mode": "cloud"},
        headers=auth_headers,
    )
    assert upload_response.status_code == 200

    conv_response = client.post("/conversations", headers=auth_headers)
    conversation_id = conv_response.json()["id"]

    ask_response = client.post(
        "/ask",
        json={"query": "What is this about?", "history": [], "mode": "cloud", "conversation_id": conversation_id},
        headers=auth_headers,
    )
    data = ask_response.json()
    assert ask_response.status_code == 200
    assert data["answer"] == "This is a mocked answer for testing."
    assert len(data["sources"]) > 0