from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app as webapp


def test_create_user_template_and_list_it(tmp_path):
    webapp.app.config["TESTING"] = True
    webapp.app.config["USER_TEMPLATE_DIR"] = tmp_path

    client = webapp.app.test_client()

    create_response = client.post(
        "/api/templates",
        json={"name": "my-template", "content": "Hello {input_txt}"},
    )
    assert create_response.status_code == 201
    payload = create_response.get_json()
    assert payload["name"] == "my-template.txt"

    created_file = tmp_path / "my-template.txt"
    assert created_file.exists()
    assert created_file.read_text(encoding="utf-8") == "Hello {input_txt}"

    list_response = client.get("/api/templates")
    assert list_response.status_code == 200
    list_payload = list_response.get_json()
    assert "my-template.txt" in list_payload["templates"]


def test_create_template_rejects_path_traversal(tmp_path):
    webapp.app.config["TESTING"] = True
    webapp.app.config["USER_TEMPLATE_DIR"] = tmp_path

    client = webapp.app.test_client()
    response = client.post(
        "/api/templates",
        json={"name": "../bad", "content": "nope"},
    )
    assert response.status_code == 400
