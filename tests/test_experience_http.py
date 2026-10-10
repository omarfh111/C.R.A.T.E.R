import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from crater_assistant.experience import Journal
from crater_assistant.experience_analysis import ExperienceService
from crater_assistant.server import make_server
from test_experience import event
from test_experience_analysis import assistant, done


def test_real_http_records_then_polls_background_analysis_and_keeps_ask(tmp_path):
    j = Journal(tmp_path / "j.sqlite")
    a = assistant()
    with ExperienceService(a, j) as experiences:
        with make_server(a, port=0, experiences=experiences) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            def post(path, body):
                req = Request(base + path, data=json.dumps(body).encode(),
                              headers={"Content-Type": "application/json", "Origin": "http://localhost:5173"})
                with urlopen(req, timeout=3) as response:
                    return response.status, json.load(response)
            try:
                status, recorded = post('/experience/events', {"event": event(), "analyze": True})
                assert status == 201 and recorded["event"]["eventId"] == event()["eventId"]
                analysis_id = recorded["analysis"]["analysisId"]
                assert done(experiences, analysis_id)["state"] == "completed"
                assert json.load(urlopen(base + '/experience/analyses/' + analysis_id))["result"]["status"] == "answered"
                assert json.load(urlopen(base + '/experience/events'))["events"][0]["imageAnalysis"] == "not_performed"
                assert post('/ask', {"question": "inconnue"})[1]["status"] == "insufficient_evidence"
                assert json.load(urlopen(base + '/health'))["experience"]["imageInference"] is False
                try:
                    post('/experience/events', {"event": event(), "analyze": "yes"})
                    assert False
                except HTTPError as exc:
                    assert exc.code == 400
            finally:
                server.shutdown()
                thread.join(timeout=2)
