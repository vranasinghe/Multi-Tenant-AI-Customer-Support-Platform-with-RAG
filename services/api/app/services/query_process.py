"""One bounded query operation. Credentials arrive through stdin and never enter logs."""

import json
import os
import sys
import threading

from app.rag.embeddings import OpenAICompatibleEmbedder


def main() -> None:
    payload = json.loads(sys.stdin.buffer.read(65537))
    question = payload.pop("question")
    # Independent hard wall limit also covers disappearance of the supervising API process.
    guard = threading.Timer(float(payload["timeout"]), os._exit, args=(124,))
    guard.daemon = True
    guard.start()
    try:
        vector = OpenAICompatibleEmbedder(**payload).embed_query(question)
        sys.stdout.write(json.dumps(vector))
    finally:
        guard.cancel()


if __name__ == "__main__":
    main()
