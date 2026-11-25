import json,os
from app.core.config import get_settings
s=get_settings()
assert s.app_env == "local", "Audit runtime must be local"
print(json.dumps(dict(environment=s.app_env,llm_provider=s.llm_provider,llm_key_present=bool(s.llm_api_key and s.llm_api_key.get_secret_value()),embedding_provider=s.embedding_provider,embedding_key_present=bool(s.embedding_api_key and s.embedding_api_key.get_secret_value()),storage=s.storage_backend,cpu=os.cpu_count())))
