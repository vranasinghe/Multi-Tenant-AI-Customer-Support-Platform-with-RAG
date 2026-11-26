"""Two tenants ingest large documents at once through the running QA stack (real worker, S3, DB).

Run inside the QA api container; /tmp/measure_a5.py supplies the document builder. Reports each
job's queue wait and processing time. Synthetic accounts and content only.
"""

import json
import re
import sys
import time
import types
import uuid

import httpx2 as httpx

source = open("/tmp/measure_a5.py", encoding="utf-8").read()  # noqa: SIM115, PTH123
base = types.ModuleType("measure_base")
exec(source[: source.index("cases: list")], base.__dict__)  # noqa: S102 - builders only

API, MAIL, ORIGIN = "http://127.0.0.1:8000/api/v1", "http://mailpit:8025", "http://localhost:3000"
PASSWORD = "live-" + uuid.uuid4().hex


def account() -> tuple[httpx.Client, dict[str, str], str]:
    client = httpx.Client(base_url=API, timeout=60)
    email = f"a5-{uuid.uuid4().hex[:10]}@example.com"
    headers = {"Origin": ORIGIN, "X-Requested-With": "platform"}
    signup = client.post(
        "/auth/signup",
        headers=headers,
        json={"email": email, "password": PASSWORD, "name": "A5", "org_name": "A5 Org"},
    )
    signup.raise_for_status()
    headers["Cookie"] = "; ".join(
        h.split(";", 1)[0] for h in signup.headers.get_list("set-cookie") if h.startswith("__Host-")
    )
    for _ in range(60):
        found = httpx.get(f"{MAIL}/api/v1/search", params={"query": f"to:{email}"}).json()
        if found.get("messages"):
            break
        time.sleep(0.25)
    body = httpx.get(f"{MAIL}/api/v1/message/{found['messages'][0]['ID']}").json()["Text"]
    token = re.search(r"verify-email\?token=([A-Za-z0-9_-]+)", body)
    assert token
    client.post("/auth/verify-email", headers=headers, json={"token": token[1]}).raise_for_status()
    org = signup.json()["org"]["id"]
    bot = client.post(f"/orgs/{org}/chatbots", headers=headers, json={"name": "A5"}).json()["id"]
    return client, headers, f"/orgs/{org}/chatbots/{bot}"


data, xml = base.rich_docx(4_900_000, 40)
tenants = [account(), account()]
uploads = []
started = time.monotonic()
for client, headers, path in tenants:
    response = client.post(
        f"{path}/documents",
        params={"filename": "large.docx"},
        content=data,
        headers={**headers, "Content-Type": base.DOCX},
    )
    response.raise_for_status()
    uploads.append((client, headers, path, response.json()["id"]))

results: dict[str, dict[str, object]] = {}
while len(results) < len(uploads) and time.monotonic() - started < 180:
    for index, (client, headers, path, document) in enumerate(uploads):
        doc = client.get(f"{path}/documents/{document}", headers=headers).json()
        if doc["status"] in {"ready", "failed"} and f"tenant{index}" not in results:
            results[f"tenant{index}"] = {
                "status": doc["status"],
                "error_code": doc["error_code"],
                "chunks": doc["chunk_count"],
                "attempt": doc["job"]["attempt"],
                "seconds_since_upload": round(time.monotonic() - started, 2),
            }
    time.sleep(0.25)
for client, headers, path, document in uploads:  # leave the QA stack as found
    client.delete(f"{path}/documents/{document}", headers=headers)
sys.stdout.write(
    "LIVE " + json.dumps({"xml_mib": round(xml / base.MIB, 1), "documents": results}) + "\n"
)
