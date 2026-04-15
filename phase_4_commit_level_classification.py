import os
import sys
import json
import glob
import shutil
import pandas as pd
from datetime import datetime
from typing import List, Dict, Optional

from dotenv import load_dotenv
load_dotenv()  

import config 


try:
    from openai import OpenAI
except ImportError:
    print("Please install:  pip install --upgrade openai pandas", file=sys.stderr)
    sys.exit(1)


def resolve_synthesised_features_input() -> str:
    base_dir = "phase_3_output_synthesised_labels_latest"
    candidates = [
        os.path.join(base_dir, "synthesised-features.csv"),
        os.path.join(base_dir, "synthesised-features.json"),
    ]

    for path in candidates:
        if os.path.exists(path):
            return path

    raise FileNotFoundError(
        "[error] No synthesised labels found in phase_3_output_synthesised_labels_latest/. "
        "Run phase_3_synthesise_labels.py first."
    )


def load_features(path: str) -> List[Dict[str, str]]:
    print(f"[info] Loading features from: {path}")

    if not os.path.exists(path):
        raise FileNotFoundError(f"[error] Features file not found: {path}")

    try:
        if path.lower().endswith(".json"):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if isinstance(data, dict) and isinstance(data.get("synthesised"), list):
                items = data["synthesised"]
            elif isinstance(data, list):
                items = data
            else:
                raise ValueError("[error] JSON features must be a list, or an object with a 'synthesised' list.")

            feats = []
            for obj in items:
                label = str(
                    obj.get("feature_label")
                    or obj.get("new_label")
                    or obj.get("label")
                    or ""
                ).strip()
                desc = str(
                    obj.get("feature_description")
                    or obj.get("new_description")
                    or obj.get("description")
                    or ""
                ).strip()
                if label:
                    feats.append({"label": label, "description": desc})
            print(f"[info] Loaded {len(feats)} features from {path}")
            return feats

        df = pd.read_csv(path).fillna("")

        label_col = next((c for c in ["feature_label", "new_label", "label"] if c in df.columns), None)
        if not label_col:
            raise ValueError("[error] CSV must contain one of: feature_label, new_label, label.")

        desc_col = next((c for c in ["feature_description", "new_description", "description"] if c in df.columns), None)

        feats = []
        for _, row in df.iterrows():
            label = str(row[label_col]).strip()
            desc = str(row[desc_col]).strip() if desc_col else ""
            if label:
                feats.append({"label": label, "description": desc})

        print(f"[info] Loaded {len(feats)} features from CSV.")
        if len(feats) == 0:
            print("[error] No valid features parsed from file!")

        return feats

    except Exception as e:
        print(f"[error] Failed to load features: {e}")
        raise



def build_features_block(features: List[Dict[str, str]]) -> str:
    if not features:
        return "[No features found]"

    lines = []
    for f in features:
        label = f.get("label", "").strip()
        desc = f.get("description", "").strip()

        if desc:
            lines.append(f"- {label}: {desc}")
        else:
            lines.append(f"- {label}")

    return "\n".join(lines)



def load_commits_from_json(json_path: str) -> List[Dict[str, str]]:
    """Load commit list from a JSON file."""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Expected a list of commits in {json_path}")
    for item in data:
        if "hash" not in item or "message" not in item:
            raise ValueError(f"Invalid commit object in {json_path}: {item}")
    return data


def call_openai_responses_api_phase3(
    commit_message: str,
    features_block: str,
    client: OpenAI
) -> str:
    instructions = (
        "You are an expert software engineering educator labeling Git commits.\n"
        "Each commit message should be assigned exactly ONE feature label from the provided list.\n"
        "If a commit does not relate to any feature, return 'NONE'.\n"
        "However, if the commit defines or modifies data models, DTOs, services, controllers, "
        "or endpoints that belong to a feature, label it with that feature.\n"
        "Output only the feature label string, with no punctuation or explanation."
    )

    user_text = f"""Commit message:
    {commit_message}

    Feature labels (with descriptions):
    {features_block}

    Task:
    Select the ONE feature label that best matches this commit.
    If the commit refactors, fixes, or updates controllers, DTOs, or services that clearly belong to a feature,
    label it with that feature rather than 'NONE'.
    If the commit appears to implement new functionality but the correct feature cannot be confidently identified,
    choose the closest related feature rather than 'NONE'.

    Return only the label string (e.g., Authentication, Testing, etc.)."""

    model = config.OPENAI_MODEL_PHASE_4
    reasoning_effort = getattr(config, "OPENAI_MODEL_REASONING_EFFORT_PHASE_4", "low")

    kwargs = {
        "model": model,
        "instructions": instructions,
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": user_text}
                ],
            },
        ],
        "reasoning": {"effort": reasoning_effort},
        "store": False,
        "max_output_tokens": 256,
        "text": {
            "format": {"type": "text"},
            "verbosity": "medium"
        }
    }

    try:
        response = client.responses.create(**kwargs)

        if getattr(response, "output_text", None):
            return response.output_text.strip()

        output = getattr(response, "output", None)
        if output:
            for item in output:
                contents = getattr(item, "content", None)
                if not contents:
                    continue
                for c in contents:
                    txt = getattr(c, "text", None) or getattr(c, "content", None)
                    if txt:
                        return txt.strip()

        if getattr(response, "reasoning", None) and getattr(response.reasoning, "summary", None):
            summary = response.reasoning.summary
            if isinstance(summary, str) and summary.strip():
                return summary.strip()

        print("[warn] No text content found in response; model may have been truncated.")
        return "NONE"

    except Exception as e:
        print(f"[error] OpenAI API call failed: {e}")
        return "NONE"


def postprocess_label(pred: str, valid_labels: set, strict: bool = True) -> str:
    guess = pred.strip().strip("'\"`")
    if guess.upper() == "NONE":
        return "NONE"
    if strict:
        return guess if guess in valid_labels else "NONE"
    if guess.casefold() in {v.casefold() for v in valid_labels}:
        for v in valid_labels:
            if guess.casefold() == v.casefold():
                return v
    return "NONE"


def main():
    features_input = resolve_synthesised_features_input()

    features = load_features(features_input)
    features_block = build_features_block(features)
    valid_labels = {f["label"] for f in features}

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    output_dir = os.path.normpath(f"phase_4_output_labeled_commits_{timestamp}")
    latest_dir = os.path.normpath("phase_4_output_labeled_commits_latest")
    os.makedirs(output_dir, exist_ok=True)
    print(f"[info] Writing run output to: {output_dir}")
    print(f"[info] Latest output mirror:  {latest_dir}")

    json_files = glob.glob(os.path.join(config.EXTRACTED_COMMITS_INPUT, "*.json"))
    if not json_files:
        print(f"[error] No JSON files found in {config.EXTRACTED_COMMITS_INPUT}")
        return

    print(f"[info] Found {len(json_files)} team JSON files.")

    all_dfs = []

    for json_path in json_files:
        team_name = os.path.splitext(os.path.basename(json_path))[0]
        print(f"\n[team] Processing {team_name} ...")

        commits = load_commits_from_json(json_path)
        print(f"[info] Loaded {len(commits)} commits from {json_path}")

        labeled_rows = []
        for i, commit in enumerate(commits):
            msg = commit["message"].strip()
            if not msg:
                label = "NONE"
            else:
                raw_label = call_openai_responses_api_phase3(msg, features_block, client)
                label = postprocess_label(raw_label, valid_labels)
            labeled_rows.append({"hash": commit["hash"], "subject": msg, "FEATURE_LABEL": label})

            if (i + 1) % 10 == 0:
                print(f"  ...labeled {i+1}/{len(commits)} commits")
        
        out_path = os.path.join(output_dir, f"{team_name}_labeled.csv")
        pd.DataFrame(labeled_rows).to_csv(out_path, index=False)
        print(f"[done] Wrote labeled CSV → {out_path}")

        all_dfs.append(pd.DataFrame(labeled_rows))
        
    all_teams_path = os.path.join(output_dir, "all_teams_labeled.csv")
    pd.concat(all_dfs).to_csv(all_teams_path, index=False)
    print(f"[done] Wrote combined CSV → {all_teams_path}")

    if os.path.exists(latest_dir):
        shutil.rmtree(latest_dir)
    shutil.copytree(output_dir, latest_dir)
    print(f"[done] Backed up latest output → {latest_dir}")



if __name__ == "__main__":
    main()
