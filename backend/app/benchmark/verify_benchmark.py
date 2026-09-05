import json
import os

def verify_dataset():
    file_path = os.path.join(os.path.dirname(__file__), "audit_benchmark_50.json")
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    categories = {}
    for item in data:
        cat = item["category"]
        categories[cat] = categories.get(cat, 0) + 1

    print("==================================================")
    print("BENCHMARK DATASET CATEGORY BREAKDOWN")
    print("==================================================")
    for cat, count in categories.items():
        print(f" • {cat:<25}: {count} cases")
    print("==================================================")

if __name__ == "__main__":
    verify_dataset()