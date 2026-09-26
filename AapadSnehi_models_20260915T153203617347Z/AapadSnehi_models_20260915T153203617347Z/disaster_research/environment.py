import hashlib
import importlib.metadata
import json
import platform
from .paths import ROOT,REPORTS,PROCESSED

def record():
    versions={d.metadata["Name"]:d.version for d in importlib.metadata.distributions() if d.metadata["Name"]}
    hashes={}
    for path in [*ROOT.glob("*.py"),*PROCESSED.glob("flood/*.csv")]:
        hashes[str(path.relative_to(ROOT))]=hashlib.sha256(path.read_bytes()).hexdigest()
    for path in PROCESSED.glob("flood/*.parquet"):
        digest=hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda:stream.read(8*1024**2),b""):digest.update(chunk)
        hashes[str(path.relative_to(ROOT))]=digest.hexdigest()
    (REPORTS/"environment_versions.json").write_text(json.dumps({"python":platform.python_version(),"packages":versions,"source_and_feature_sha256":hashes},indent=2))

if __name__ == "__main__":record()
