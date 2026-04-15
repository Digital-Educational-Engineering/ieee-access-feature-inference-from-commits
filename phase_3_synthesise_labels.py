
import os
import json
import csv
import random
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from dotenv import load_dotenv
from openai import OpenAI
import config

load_dotenv()

PROMPT_DIR = Path("system-prompts-and-output-schema")
PROMPT_FILE = PROMPT_DIR / "synthesise-features-prompt.txt"
SCHEMA_FILE = PROMPT_DIR / "synthesise-features-schema.json"


def load_all_features(input_file: Path) -> Dict[str, Any]:
    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("Input JSON must be an object with 'features' and 'non_feature_labels'")
    data.setdefault('features', [])
    data.setdefault('non_feature_labels', [])
    return data


def shuffle_items(features: List[Dict[str, str]], non_features: List[Dict[str, str]]):
    random.shuffle(features)
    random.shuffle(non_features)


def load_instruction_prompt() -> str:
    try:
        if PROMPT_FILE.exists():
            return PROMPT_FILE.read_text(encoding="utf-8").strip()
    except Exception as e:
        print(f"Warning: Failed to read prompt file '{PROMPT_FILE}': {e}")
    return (
        "Given arrays 'features' and 'non_feature_labels' with label, description, and source_category, "
        "group equivalent items into a single 'synthesised' list of groups. Each group must include a normalised label, "
        "a refined description, a category (FEATURE or NON_FEATURE), and an 'originals' array listing all inputs assigned to it. "
        "Output valid JSON matching the provided schema."
    )


def load_output_schema() -> Dict[str, Any]:
    """Load the JSON schema for the synthesis structured output."""
    try:
        if SCHEMA_FILE.exists():
            data = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
            if all(k in data for k in ("name", "strict", "schema")):
                return data
            else:
                raise ValueError("Schema JSON must include 'name', 'strict', and 'schema' keys")
        else:
            raise FileNotFoundError(f"Schema file not found: {SCHEMA_FILE}")
    except Exception as e:
        raise RuntimeError(f"Failed to load output schema: {e}")


def build_instruction() -> str:
    return load_instruction_prompt()


def call_openai_synthesis(features: List[Dict[str, str]], non_features: List[Dict[str, str]], client: OpenAI) -> Dict[str, Any]:
    schema_def = load_output_schema()
    instruction = load_instruction_prompt()

    model = config.OPENAI_MODEL_PHASE_3

    input_payload = {
        "role": "user",
        "content": [
            {
                "type": "input_text",
                "text": "features =\n" + json.dumps(features, indent=2, ensure_ascii=False)
            },
            {
                "type": "input_text",
                "text": "non_feature_labels =\n" + json.dumps(non_features, indent=2, ensure_ascii=False)
            }
        ]
    }

    resp = client.responses.create(
        model=model,
        instructions=instruction,
        input=[input_payload],
        reasoning={"effort": getattr(config, "OPENAI_MODEL_REASONING_EFFORT_PHASE_3", getattr(config, "REASONING_EFFORT", "low"))},
        text={
            "format": {
                "type": "json_schema",
                "name": schema_def["name"],
                "strict": schema_def["strict"],
                "schema": schema_def["schema"],
            }
        },
        store=False,
    )

    if hasattr(resp, "output_text") and resp.output_text:
        return json.loads(resp.output_text)

    if hasattr(resp, "output") and resp.output:
        for item in resp.output:
            contents = getattr(item, "content", [])
            for c in contents:
                if getattr(c, "type", None) in ("output_text", "output_text_delta", "text"):
                    text_val = getattr(c, "text", None) or getattr(c, "content", None)
                    if text_val:
                        return json.loads(text_val)

    raise ValueError("Unable to extract structured JSON from Responses API output")


def normalise_synthesised_groups(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(result, dict):
        return []

    direct = result.get("synthesised")
    if isinstance(direct, list):
        return direct

    groups: List[Dict[str, Any]] = []

    result_obj = result.get("result")
    if isinstance(result_obj, dict):
        mapping = [
            ("features", "FEATURE"),
            ("non_feature_labels", "NON_FEATURE"),
        ]
        for bucket, source_category in mapping:
            items = result_obj.get(bucket, [])
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                merged_from = item.get("merged_from", [])
                originals = []
                if isinstance(merged_from, list):
                    for original in merged_from:
                        if not isinstance(original, dict):
                            continue
                        originals.append(
                            {
                                "source_category": source_category,
                                "label": original.get("label", ""),
                                "description": original.get("description", ""),
                            }
                        )
                groups.append(
                    {
                        "label": item.get("label", ""),
                        "description": item.get("description", ""),
                        "category": source_category,
                        "originals": originals,
                    }
                )
        return groups

    mapping = [
        ("features", "FEATURE"),
        ("non_feature_labels", "NON_FEATURE"),
    ]
    for bucket, source_category in mapping:
        items = result.get(bucket, [])
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            groups.append(
                {
                    "label": item.get("label", ""),
                    "description": item.get("description", ""),
                    "category": source_category,
                    "originals": [],
                }
            )

    return groups


def save_json(synthesised: List[Dict[str, Any]], output_file: Path):
    payload = {"synthesised": synthesised}
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"  Saved synthesis JSON: {output_file.name}")


def save_csv(synthesised: List[Dict[str, Any]], output_file: Path):
    rows = []
    for group in synthesised:
        new_label = group.get('label', '')
        new_desc = group.get('description', '')
        category = group.get('category', '')
        originals = group.get('originals', [])

        lines = []
        for o in originals:
            src_cat = o.get('source_category', '')
            o_label = o.get('label', '')
            o_desc = o.get('description', '')
            lines.append(f"- [{src_cat}] {o_label} — {o_desc}")
        originals_block = "\n".join(lines)

        rows.append({
            'new_label': new_label,
            'new_description': new_desc,
            'category': category,
            'originals': originals_block,
        })

    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['new_label', 'new_description', 'category', 'originals'])
        writer.writeheader()
        writer.writerows(rows)
    print(f"  Saved synthesis CSV: {output_file.name}")


def main():
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("Error: OPENAI_API_KEY not found in environment variables")
        print("Please create a .env file with your OpenAI API key:")
        print("  cp .env.example .env")
        print("  # Edit .env and add your API key")
        return

    client = OpenAI(api_key=api_key)

    input_dir = Path(getattr(config, 'FEATURE_LABELS_INPUT', 'phase_2_output_feature_labels_latest'))
    input_file = input_dir / 'all-features.json'
    print(f"Loading aggregated features: {input_file}")
    data = load_all_features(input_file)

    features = data.get('features', [])
    non_features = data.get('non_feature_labels', [])
    print(f"  Loaded {len(features)} features and {len(non_features)} non-feature labels")

    features_prepped = [{"label": f.get('label', ''), "description": f.get('description', ''), "source_category": "FEATURE"} for f in features]
    non_features_prepped = [{"label": nf.get('label', ''), "description": nf.get('description', ''), "source_category": "NON_FEATURE"} for nf in non_features]

    shuffle_items(features_prepped, non_features_prepped)

    print("Calling OpenAI for synthesis...")
    result = call_openai_synthesis(features_prepped, non_features_prepped, client)

    synthesised = normalise_synthesised_groups(result)
    if not synthesised and (features_prepped or non_features_prepped):
        raise ValueError(
            "Model output did not contain any synthesised groups. "
            "Check prompt/schema alignment in system-prompts-and-output-schema/."
        )

    timestamp = datetime.now().strftime('%Y-%m-%d-%H%M%S')
    output_dir = Path(f'phase_3_output_synthesised_labels-{timestamp}')
    output_dir.mkdir(exist_ok=True)
    print(f"\nOutput directory: {output_dir}")

    json_output = output_dir / 'synthesised-features.json'
    csv_output = output_dir / 'synthesised-features.csv'

    save_json(synthesised, json_output)
    save_csv(synthesised, csv_output)

    print("\nSynthesis complete!")
    print(f"JSON: {json_output}")
    print(f"CSV:  {csv_output}")

    backup_dir = Path('phase_3_output_synthesised_labels_latest')
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    shutil.copytree(output_dir, backup_dir)
    print(f"Backed up results to: {backup_dir}")


if __name__ == '__main__':
    main()
