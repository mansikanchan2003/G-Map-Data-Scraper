import pytest
from fastapi.testclient import TestClient
from src.main import app
import os
import shutil
import io

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_teardown_media_dir():
    # Setup
    media_dir = os.path.join("data", "whatsapp_media")
    os.makedirs(media_dir, exist_ok=True)
    yield
    # We do not strictly tear down to avoid deleting real test data if any, 
    # but since this is a test, we can clean up files created during the test.
    # We'll just leave them for manual inspection if needed, or clear the directory.
    pass

def test_upload_image_success():
    file_content = b"fake image content"
    files = {"file": ("test.jpg", io.BytesIO(file_content), "image/jpeg")}
    data = {"media_type": "image"}
    
    response = client.post("/api/v1/whatsapp/media/upload", files=files, data=data)
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["status"] == "success"
    assert res_data["media_type"] == "image"
    assert res_data["filename"] == "test.jpg"
    assert res_data["size_bytes"] == len(file_content)
    assert res_data["media_id"].endswith(".jpg")
    
    # Test preview endpoint
    media_id = res_data["media_id"]
    get_res = client.get(f"/api/v1/whatsapp/media/{media_id}")
    assert get_res.status_code == 200
    assert get_res.content == file_content
    
    # Cleanup
    os.remove(os.path.join("data", "whatsapp_media", media_id))

def test_upload_video_success():
    file_content = b"fake video content"
    files = {"file": ("test.mp4", io.BytesIO(file_content), "video/mp4")}
    data = {"media_type": "video"}
    
    response = client.post("/api/v1/whatsapp/media/upload", files=files, data=data)
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["media_type"] == "video"
    assert res_data["filename"] == "test.mp4"
    assert res_data["media_id"].endswith(".mp4")
    
    # Cleanup
    os.remove(os.path.join("data", "whatsapp_media", res_data["media_id"]))

def test_upload_unsupported_image_format():
    file_content = b"fake gif content"
    files = {"file": ("test.gif", io.BytesIO(file_content), "image/gif")}
    data = {"media_type": "image"}
    
    response = client.post("/api/v1/whatsapp/media/upload", files=files, data=data)
    assert response.status_code == 400
    assert "Unsupported image format" in response.json()["detail"]

def test_upload_unsupported_video_format():
    file_content = b"fake mkv content"
    files = {"file": ("test.mkv", io.BytesIO(file_content), "video/x-matroska")}
    data = {"media_type": "video"}
    
    response = client.post("/api/v1/whatsapp/media/upload", files=files, data=data)
    assert response.status_code == 400
    assert "Unsupported video format" in response.json()["detail"]

def test_upload_invalid_media_type():
    file_content = b"fake content"
    files = {"file": ("test.jpg", io.BytesIO(file_content), "image/jpeg")}
    data = {"media_type": "document"} # Not image or video
    
    response = client.post("/api/v1/whatsapp/media/upload", files=files, data=data)
    assert response.status_code == 400
    assert "Invalid media_type" in response.json()["detail"]

def test_upload_executable_rejected():
    file_content = b"fake exe content"
    files = {"file": ("test.exe", io.BytesIO(file_content), "application/x-msdownload")}
    data = {"media_type": "image"}
    
    response = client.post("/api/v1/whatsapp/media/upload", files=files, data=data)
    assert response.status_code == 400
    assert "Unsupported image format" in response.json()["detail"]

def test_path_traversal_protection():
    get_res = client.get("/api/v1/whatsapp/media/..%2F..%2F.env")
    # Due to os.path.basename, it should look for ".env" in the media directory, not the project root
    # Since .env is not in data/whatsapp_media, it returns 404
    assert get_res.status_code == 404

def test_oversized_file(monkeypatch):
    monkeypatch.setenv("WHATSAPP_MEDIA_MAX_SIZE_MB", "0.000001") # ~1 byte
    file_content = b"this is larger than 1 byte"
    files = {"file": ("test.jpg", io.BytesIO(file_content), "image/jpeg")}
    data = {"media_type": "image"}

    response = client.post("/api/v1/whatsapp/media/upload", files=files, data=data)
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "allows at most" in detail and "compress" in detail


def test_image_over_meta_limit_is_rejected():
    """
    Meta caps image headers at 5MB and rejects anything larger at send time
    with an opaque "(#100) Invalid parameter", which used to surface only when
    a campaign ran. The same limit is applied at upload instead.
    """
    oversized = b"x" * (6 * 1024 * 1024)  # 6MB
    files = {"file": ("big.png", io.BytesIO(oversized), "image/png")}
    response = client.post(
        "/api/v1/whatsapp/media/upload", files=files, data={"media_type": "image"}
    )
    assert response.status_code == 400
    assert "5MB" in response.json()["detail"]


def test_video_may_exceed_the_image_limit():
    """A 6MB video is fine: Meta's video ceiling is 16MB, not 5MB."""
    payload = b"x" * (6 * 1024 * 1024)
    files = {"file": ("clip.mp4", io.BytesIO(payload), "video/mp4")}
    response = client.post(
        "/api/v1/whatsapp/media/upload", files=files, data={"media_type": "video"}
    )
    assert response.status_code == 200
