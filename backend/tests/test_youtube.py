import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.youtube import YoutubeError, video_id

VID = "jNQXAC9IVRw"


@pytest.fixture(scope="module")
def client():
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        yield c


@pytest.mark.parametrize("url", [
    f"https://www.youtube.com/watch?v={VID}",
    f"https://youtube.com/watch?v={VID}&list=PLxxxxxxxxxxxxxxxx&t=42s",
    f"https://m.youtube.com/watch?v={VID}",
    f"https://youtu.be/{VID}",
    f"https://youtu.be/{VID}?si=abc",
    f"https://www.youtube.com/shorts/{VID}",
    f"https://www.youtube.com/live/{VID}",
    f"https://www.youtube.com/embed/{VID}",
    f"  https://www.youtube.com/watch?v={VID}  ",
])
def test_urls_acceptees(url):
    assert video_id(url) == VID


@pytest.mark.parametrize("url", [
    "",
    "not a url",
    f"http://www.youtube.com/watch?v={VID}",                       # pas de https
    f"https://evil.example/watch?v={VID}",
    f"https://youtube.com.evil.example/watch?v={VID}",             # faux sous-domaine
    f"https://www.youtube.com@evil.example/watch?v={VID}",         # identifiants dans l'URL
    f"https://user:pw@www.youtube.com/watch?v={VID}",
    f"https://www.youtube.com:8443/watch?v={VID}",
    f"https://notyoutu.be/{VID}",
    f"file:///C:/Users/x/{VID}.mp4",
    "https://www.youtube.com/playlist?list=PLxxxxxxxxxxxxxxxx",    # playlist seule
    "https://www.youtube.com/@chaine",
    "https://www.youtube.com/watch?v=court",
    f"https://www.youtube.com/watch?v={VID};rm -rf",
    "https://www.youtube.com/watch?v=" + "a" * 50,
    "javascript:alert(1)",
])
def test_urls_refusees(url):
    with pytest.raises(YoutubeError):
        video_id(url)


def test_endpoint_refuse_hors_youtube(client):
    r = client.post("/jobs/youtube", json={"url": "https://evil.example/x"})
    assert r.status_code == 422


def test_endpoint_exige_origin_valide(client):
    r = client.post("/jobs/youtube", json={"url": f"https://youtu.be/{VID}"}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
