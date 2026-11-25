"""Record address-family routing only, never response bodies or credentials."""

import json
import re
import urllib.error
import urllib.request

result = []
for host in ["127.0.0.1", "localhost", "[::1]"]:
    try:
        with urllib.request.urlopen(
            "http://" + host + ":3000/signup", timeout=5
        ) as response:
            status, body = response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        status, body = error.code, error.read().decode()
    result.append(
        {
            "host": host,
            "status": status,
            "title": re.findall("<title>(.*?)</title>", body)[:1],
        }
    )
print(json.dumps(result))
