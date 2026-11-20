import json
from pathlib import Path
import re
import statistics
import time
import unicodedata
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def normalize(text):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text).lower().replace("学生卡", "校园卡").replace("饭卡", "校园卡"))


def keyword(query, text):
    tokens = set()
    for token in re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", normalize(query)):
        if re.fullmatch(r"[a-z0-9]+", token) or len(token) == 1:
            tokens.add(token)
        else:
            tokens.update(token[index:index + 2] for index in range(len(token) - 1))
    return sum(token in normalize(text) for token in tokens) / max(len(tokens), 1)


def metrics(order, relevant):
    positions = [index + 1 for index, identifier in enumerate(order) if identifier in relevant]
    return {"recall_at_5": sum(position <= 5 for position in positions) / len(relevant), "recall_at_10": sum(position <= 10 for position in positions) / len(relevant), "mrr": 1 / min(positions) if positions else 0}


def main():
    dataset = json.loads((ROOT / "ai" / "evaluation.json").read_text(encoding="utf-8"))
    rows = []
    for sample in dataset["queries"]:
        payload = json.dumps({"query": sample["query"], "documents": dataset["documents"]}, ensure_ascii=False).encode()
        request = urllib.request.Request("http://127.0.0.1:8765/score", data=payload, headers={"Content-Type": "application/json"})
        start = time.perf_counter()
        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.load(response)
        elapsed = (time.perf_counter() - start) * 1000
        semantic_order = sorted((document["id"] for document in dataset["documents"]), key=lambda identifier: result["scores"][str(identifier)], reverse=True)
        keyword_order = [document["id"] for document in sorted(dataset["documents"], key=lambda document: keyword(sample["query"], document["text"]), reverse=True)]
        rows.append({**sample, "semantic": metrics(semantic_order, sample["relevant"]), "keyword": metrics(keyword_order, sample["relevant"]), "semantic_top5": semantic_order[:5], "latency_ms": round(elapsed, 2)})
    summary = {"model": result["model"], "revision": result["revision"], "documents": len(dataset["documents"]), "queries": len(rows), "note": "人工构造小样本；比较原始语义排序与词片段基线，非正式业务准确率；第一条含文档向量冷缓存开销。", "results": rows}
    for method in ("semantic", "keyword"):
        summary[method] = {metric: round(statistics.mean(row[method][metric] for row in rows), 4) for metric in ("recall_at_5", "recall_at_10", "mrr")}
    summary["first_query_ms"] = rows[0]["latency_ms"]
    summary["warm_average_ms"] = round(statistics.mean(row["latency_ms"] for row in rows[1:]), 2)
    summary["warm_max_ms"] = max(row["latency_ms"] for row in rows[1:])
    (ROOT / "docs" / "检索评测结果.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key != "results"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
