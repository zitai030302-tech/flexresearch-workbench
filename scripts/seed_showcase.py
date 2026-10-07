"""Create a clearly labelled, local-only showcase graph for FlexResearch.

This script is opt-in. It never calls an external API and never changes existing
lab records. Every inserted object starts with ``DEMO`` so it can be removed
from a copy of the local database before a real lab deployment.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

# `python scripts/seed_showcase.py` sets sys.path to scripts/, not the project
# root. Keep this opt-in helper runnable both directly and via `make demo-seed`.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import analyze, get_db, now

DEMO_PROJECT = "DEMO · 柔性传感可靠性（公开样例）"


def main() -> None:
    demo_file = PROJECT_ROOT / "data" / "demo_strain_sensor.csv"
    if not demo_file.exists():
        raise SystemExit(f"找不到公开样例数据：{demo_file}")
    raw = demo_file.read_bytes()
    frame = pd.read_csv(demo_file)
    analysis = analyze(frame)
    with get_db() as db:
        existing = db.execute("SELECT id FROM projects WHERE name = ?", (DEMO_PROJECT,)).fetchone()
        if existing:
            print(f"样例已存在（projectId={existing['id']}），未写入重复记录。")
            return
        created = now()
        project_id = db.execute("INSERT INTO projects (name, track, owner, objective, status, created_at) VALUES (?, ?, ?, ?, ?, ?)", (DEMO_PROJECT, "柔性感知", "FlexResearch demo", "展示论文—证据—测量—决策的可追溯关系；不可用作实验结论。", "demo", created)).lastrowid
        sample_id = db.execute("INSERT INTO samples (project_id, sample_code, material, process_note, status, created_at) VALUES (?, ?, ?, ?, ?, ?)", (project_id, "DEMO-STRAIN-01", "DEMO · synthetic strain-resistance dataset", "公开 CSV 示例；非实验室样品。", "demo", created)).lastrowid
        metrics = analysis["metrics"]
        measurement_id = db.execute("INSERT INTO measurements (sample_id, filename, sha256, measurement_type, x_column, y_column, point_count, metrics_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (sample_id, demo_file.name, hashlib.sha256(raw).hexdigest(), analysis["measurementType"], analysis["columns"]["x"], analysis["columns"]["y"], analysis["points"], json.dumps(metrics, ensure_ascii=False), created)).lastrowid
        public_doi = "10.1038/s41928-026-01617-0"
        doi_already_used = db.execute("SELECT 1 FROM papers WHERE doi = ?", (public_doi,)).fetchone()
        paper_id = db.execute("INSERT INTO papers (project_id, doi, title, journal, authors, publication_year, source_url, source_provider, quality_json, tags, notes, review_status, reviewer, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (project_id, None if doi_already_used else public_doi, "A symmetry-reconfigurable photodiode for sensing and computing", "Nature Electronics", "请在正式引用前通过 DOI/Crossref 补全作者", 2026, "https://doi.org/10.1038/s41928-026-01617-0", "Demo public seed", json.dumps({"metadataScore": 65, "flags": ["展示记录，正式使用前请核对原文与完整元数据"], "definition": "元数据完整性评分，不代表论文科学质量或结论可靠性"}, ensure_ascii=False), "DEMO, flexible optoelectronics, evidence workflow", "此条仅演示 DOI—证据卡流转；不自动提取论文性能结论。", "reviewed", "Demo reviewer", created, created)).lastrowid
        card_id = db.execute("INSERT INTO evidence_cards (paper_id, title, claim, evidence_type, locator, excerpt, review_status, reviewer, review_note, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (paper_id, "DEMO · 从公开来源进入证据审阅", "该卡仅展示“DOI 记录需经人工定位和审核后才能进入决策包”的工作流，不构成器件性能结论。", "method", "DEMO workflow anchor", "公开展示样例：请在真实项目中替换为原文图号、页码和短摘录。", "reviewed", "Demo reviewer", "已标识为非科研结论的工作流样例。", created, created)).lastrowid
        snapshot = {"schemaVersion": 1, "capturedAt": created, "measurements": [{"id": measurement_id, "sampleCode": "DEMO-STRAIN-01", "type": analysis["measurementType"], "filename": demo_file.name, "sha256": hashlib.sha256(raw).hexdigest(), "metrics": metrics}], "evidenceCards": [{"id": card_id, "title": "DEMO · 从公开来源进入证据审阅", "claim": "该卡仅展示“DOI 记录需经人工定位和审核后才能进入决策包”的工作流，不构成器件性能结论。", "type": "method", "locator": "DEMO workflow anchor", "source": "A symmetry-reconfigurable photodiode for sensing and computing", "doi": "10.1038/s41928-026-01617-0", "reviewer": "Demo reviewer"}]}
        db.execute("INSERT INTO decision_packets (project_id, title, question, proposed_decision, measurement_ids_json, evidence_card_ids_json, snapshot_json, status, reviewer, review_note, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (project_id, "DEMO · 证据驱动实验决策包", "如何展示从文献条目到数据分析和人工决策的完整链路？", "仅用于产品演示：真实实验必须由负责人依据原文、SOP 与数据质量另行决策。", json.dumps([measurement_id]), json.dumps([card_id]), json.dumps(snapshot, ensure_ascii=False), "draft", "", "等待真实负责人审核。", created, created))
    print("已写入本地公开样例。打开 /provenance 并选择 ‘DEMO · 柔性传感可靠性（公开样例）’ 查看完整链路。")


if __name__ == "__main__":
    main()

