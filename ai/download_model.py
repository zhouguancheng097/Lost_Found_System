import argparse
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.request

REPOSITORY = "BAAI/bge-small-zh-v1.5"
ROOT = Path(__file__).resolve().parents[1]


def request_json(url):
    with urllib.request.urlopen(url, timeout=25) as response:
        return json.load(response)


def download(endpoint):
    destination = ROOT / "models" / "bge-small-zh-v1.5"
    destination.mkdir(parents=True, exist_ok=True)
    metadata = request_json(f"{endpoint}/api/models/{REPOSITORY}/revision/7999e1d3359715c523056ef9478215996d62a620?blobs=true")
    revision = metadata["sha"]
    siblings = {item["rfilename"]: item for item in metadata["siblings"]}
    weight = "model.safetensors" if "model.safetensors" in siblings else "pytorch_model.bin"
    filenames = ["config.json", "tokenizer_config.json", "special_tokens_map.json", "vocab.txt", "tokenizer.json", "README.md", weight]
    entries = []
    for filename in filenames:
        if filename not in siblings:
            continue
        target = destination / filename
        expected = siblings[filename].get("lfs", {}).get("sha256")
        expected_blob = siblings[filename].get("blobId") if not expected else None
        def valid_file(path):
            if not path.exists():
                return False
            contents = path.read_bytes()
            if expected:
                return hashlib.sha256(contents).hexdigest() == expected
            if expected_blob:
                return hashlib.sha1(f"blob {len(contents)}\0".encode() + contents).hexdigest() == expected_blob
            return False
        if not valid_file(target):
            temporary = target.with_suffix(target.suffix + ".part")
            for attempt in range(3):
                try:
                    print(f"Downloading {filename} from {endpoint} revision {revision}", flush=True)
                    url = f"{endpoint}/{REPOSITORY}/resolve/{revision}/{filename}"
                    with urllib.request.urlopen(url, timeout=90) as response, temporary.open("wb") as output:
                        while chunk := response.read(1024 * 1024):
                            output.write(chunk)
                    actual = hashlib.sha256(temporary.read_bytes()).hexdigest()
                    if expected and actual != expected:
                        raise RuntimeError(f"SHA-256 mismatch: {filename}")
                    if expected_blob and not valid_file(temporary):
                        raise RuntimeError(f"Git blob checksum mismatch: {filename}")
                    temporary.replace(target)
                    break
                except Exception:
                    if attempt == 2:
                        raise
                    time.sleep(2)
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        entries.append({"name": filename, "bytes": target.stat().st_size, "sha256": actual, "lfs_verified": bool(expected)})
    manifest = {"repository": REPOSITORY, "revision": revision, "endpoint": endpoint, "downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "files": entries}
    (destination / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", default="https://huggingface.co")
    arguments = parser.parse_args()
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    download(arguments.endpoint.rstrip("/"))
