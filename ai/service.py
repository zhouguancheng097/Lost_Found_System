import json
import os
from collections import OrderedDict
from pathlib import Path
import threading
from typing import Annotated

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

import torch
from fastapi import FastAPI
from pydantic import BaseModel, Field
from transformers import AutoModel, AutoTokenizer

MODEL_DIRECTORY = Path(__file__).resolve().parents[1] / "models" / "bge-small-zh-v1.5"
manifest = json.loads((MODEL_DIRECTORY / "manifest.json").read_text(encoding="utf-8"))
torch.set_num_threads(max(1, min(4, os.cpu_count() or 1)))
tokenizer = AutoTokenizer.from_pretrained(MODEL_DIRECTORY, local_files_only=True, trust_remote_code=False)
model = AutoModel.from_pretrained(MODEL_DIRECTORY, local_files_only=True, trust_remote_code=False).eval()
cache = OrderedDict()
lock = threading.Lock()
app = FastAPI(title="失物招领本地语义检索", docs_url=None, redoc_url=None)


class Document(BaseModel):
    id: int
    text: Annotated[str, Field(min_length=1, max_length=2400)]


class ScoreRequest(BaseModel):
    query: Annotated[str, Field(min_length=1, max_length=2200)]
    documents: Annotated[list[Document], Field(max_length=1000)]


def encode(texts):
    vectors = []
    for start in range(0, len(texts), 16):
        inputs = tokenizer(texts[start:start + 16], padding=True, truncation=True, max_length=512, return_tensors="pt")
        with torch.inference_mode():
            outputs = model(**inputs).last_hidden_state[:, 0]
            vectors.append(torch.nn.functional.normalize(outputs, p=2, dim=1).cpu())
    return torch.cat(vectors) if vectors else torch.empty((0, model.config.hidden_size))


@app.get("/health")
def health():
    return {"ok": True, "model": manifest["repository"], "revision": manifest["revision"], "dimension": model.config.hidden_size, "device": "cpu"}


@app.post("/score")
def score(request: ScoreRequest):
    with lock:
        missing = list(dict.fromkeys(document.text for document in request.documents if document.text not in cache))
        for text, vector in zip(missing, encode(missing)):
            cache[text] = vector
        query = encode(["为这个句子生成表示以用于检索相关文章：" + request.query])[0]
        scores = {}
        for document in request.documents:
            cache.move_to_end(document.text)
            scores[str(document.id)] = round(float(torch.dot(query, cache[document.text])), 6)
        while len(cache) > 4096:
            cache.popitem(last=False)
    return {"scores": scores, "model": manifest["repository"], "revision": manifest["revision"]}
