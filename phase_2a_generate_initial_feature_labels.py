
import os
import json
import csv
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any
from dotenv import load_dotenv
from openai import OpenAI
import config
import shutil
import time

load_dotenv()

PROMPT_DIR = Path("system-prompts-and-output-schema")
PROMPT_FILE = PROMPT_DIR / "generate-initial-feature-labels-prompt.txt"
SCHEMA_FILE = PROMPT_DIR / "generate-initial-feature-labels-schema.json"


def load_instruction_prompt() -> str:
    """Load the analysis instructions from the prompt file, with a built-in fallback."""
    try:
        if PROMPT_FILE.exists():
            return PROMPT_FILE.read_text(encoding="utf-8").strip()
    except Exception as e:
        print(f"Warning: Failed to read prompt file '{PROMPT_FILE}': {e}")
    return (
        "You are an expert software analyst. Given a JSON array named 'commits' "
        "(objects with 'hash' and 'message'), infer an 'overview', a deduplicated list "
        "of user/API-facing 'features' (label+description), and a deduplicated list of "
        "'non_feature_labels' (label+description). Normalize labels (Title Case, 1–3 words), "
        "avoid project-specific terms, and output strictly valid JSON matching the provided schema."
    )


def load_output_schema() -> Dict[str, Any]:
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


def call_openai_responses_api(commits: List[Dict[str, str]], client: OpenAI) -> Dict[str, Any]:
    commits_json = json.dumps(commits, indent=2)
    instruction = load_instruction_prompt()
    schema_def = load_output_schema()

    model = config.OPENAI_MODEL_PHASE_2

    print(f"  Calling OpenAI API with model: {model}...")

    try:
        response = client.responses.create(
            model=model,
            instructions=instruction,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "commits =\n" + commits_json}
                    ],
                },
            ],
            reasoning = { 
                "effort": getattr(config, "OPENAI_MODEL_REASONING_EFFORT_PHASE_2", "low")
            },
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

        if hasattr(response, "output_text") and response.output_text:
            return json.loads(response.output_text)

        if hasattr(response, "output") and response.output:
            for item in response.output:
                contents = getattr(item, "content", [])
                for c in contents:
                    if getattr(c, "type", None) in ("output_text", "output_text_delta", "text"):
                        text_val = getattr(c, "text", None) or getattr(c, "content", None)
                        if text_val:
                            return json.loads(text_val)

        if hasattr(response, "input") and response.input:
            for msg in response.input:
                if getattr(msg, "role", None) == "assistant":
                    for content_item in getattr(msg, "content", []):
                        if getattr(content_item, "type", None) == "output_text" and getattr(content_item, "text", None):
                            return json.loads(content_item.text)

        raise ValueError("Unable to extract structured JSON from Responses API output")

    except Exception as e:
        print(f"Error calling OpenAI API: {e}")
        raise


def save_features_json(result: Dict[str, Any], output_file: Path):
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"  Saved feature labels JSON: {output_file.name}")


def save_features_csv(result: Dict[str, Any], output_file: Path):
    rows = []
    
    for feature in result.get('features', []):
        rows.append({
            'label_type': 'FEATURE',
            'label': feature['label'],
            'description': feature['description']
        })
    
    for non_feature in result.get('non_feature_labels', []):
        rows.append({
            'label_type': 'NON_FEATURE',
            'label': non_feature['label'],
            'description': non_feature['description']
        })
    
    if rows:
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['label_type', 'label', 'description'])
            writer.writeheader()
            writer.writerows(rows)
        print(f"  Saved feature labels CSV: {output_file.name}")
    else:
        print(f"  Warning: No features or non-features to save to CSV")


def process_json_file(json_file: Path, output_dir: Path, client: OpenAI):
    print(f"\nProcessing: {json_file.name}")
    start_time = time.time()

    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            commits = json.load(f)
    except Exception as e:
        print(f"  Error reading JSON file: {e}")
        return

    if not commits:
        print(f"  No commits found in file, skipping")
        return

    print(f"  Loaded {len(commits)} commits")

    try:
        result = call_openai_responses_api(commits, client)
    except Exception as e:
        print(f"  Failed to process file: {e}")
        return

    repo_name = json_file.stem.replace('_commits', '')

    json_output = output_dir / f"{repo_name}_features.json"
    csv_output = output_dir / f"{repo_name}_features.csv"

    save_features_json(result, json_output)
    save_features_csv(result, csv_output)

    feature_count = len(result.get('features', []))
    non_feature_count = len(result.get('non_feature_labels', []))
    print(f"  Generated {feature_count} features and {non_feature_count} non-feature labels")

    elapsed = time.time() - start_time
    mins = int(elapsed // 60)
    secs = int(elapsed % 60)
    print(f"  Time taken: {mins} min {secs} sec")


def find_json_files(input_path: Path) -> List[Path]:
    if input_path.is_file() and input_path.suffix == '.json':
        return [input_path]
    elif input_path.is_dir():
        json_files = []
        
        extract_dirs = sorted(input_path.glob('commit-raw-extracts-*'))
        
        if extract_dirs:
            for extract_dir in extract_dirs:
                for json_file in sorted(extract_dir.glob('*_commits.json')):
                    if not json_file.name.startswith('all_repos'):
                        json_files.append(json_file)
        else:
            for json_file in sorted(input_path.glob('*_commits.json')):
                if not json_file.name.startswith('all_repos'):
                    json_files.append(json_file)
        
        return json_files
    else:
        raise ValueError(f"Invalid input path: {input_path}")


def main():
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("Error: OPENAI_API_KEY not found in environment variables")
        print("Please create a .env file with your OpenAI API key:")
        print("  cp .env.example .env")
        print("  # Edit .env and add your API key")
        return
    
    client = OpenAI(api_key=api_key)
    
    input_path = Path(config.EXTRACTED_COMMITS_INPUT)
    if not input_path.exists():
        print(f"Error: Input path does not exist: {input_path}")
        return
    
    try:
        json_files = find_json_files(input_path)
    except ValueError as e:
        print(f"Error: {e}")
        return
    
    if not json_files:
        print(f"No commit JSON files found in: {input_path}")
        return
    
    print(f"Starting feature label generation...")
    print(f"Found {len(json_files)} JSON file(s) to process")
    used_model = config.OPENAI_MODEL_PHASE_2
    print("Using inline prompt and schema from 'system-prompts-and-output-schema/'")
    print(f"OpenAI model: {used_model}")
    
    timestamp = datetime.now().strftime('%Y-%m-%d-%H%M%S')
    output_dir = Path(f'phase_2_output_feature_labels-{timestamp}')
    output_dir.mkdir(exist_ok=True)
    print(f"Output directory: {output_dir}")
    
    processed_count = 0
    failed_count = 0
    
    for json_file in json_files:
        try:
            process_json_file(json_file, output_dir, client)
            processed_count += 1
        except Exception as e:
            print(f"  Failed to process {json_file.name}: {e}")
            failed_count += 1
    
    print(f"\n{'='*60}")
    print(f"Feature label generation complete!")
    print(f"Successfully processed: {processed_count} file(s)")
    if failed_count > 0:
        print(f"Failed: {failed_count} file(s)")
    print(f"Output directory: {output_dir}")
    print(f"{'='*60}")

    backup_dir = Path('phase_2_output_feature_labels_latest')
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    shutil.copytree(output_dir, backup_dir)
    print(f"Backed up results to: {backup_dir}")
    
    
if __name__ == "__main__":
    main()
