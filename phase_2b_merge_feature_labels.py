
import json
import csv
from pathlib import Path
from typing import List
import config


def aggregate_features(input_dir: Path):
    print(f"\nAggregating features from: {input_dir}")
    
    all_features = []
    all_non_features = []
    all_items_with_repo = [] 
    
    feature_files = sorted(input_dir.glob('*_features.json'))
    
    if not feature_files:
        print(f"Error: No *_features.json files found in {input_dir}")
        return
    
    for json_file in feature_files:
        if json_file.name == 'all-features.json':
            continue
        
        repo_name = json_file.stem.replace('_features', '')
            
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            features = data.get('features', [])
            all_features.extend(features)
            
            for feature in features:
                all_items_with_repo.append({
                    'repo': repo_name,
                    'label_type': 'FEATURE',
                    'label': feature.get('label', ''),
                    'description': feature.get('description', '')
                })
            
            non_features = data.get('non_feature_labels', [])
            all_non_features.extend(non_features)
            
            for non_feature in non_features:
                all_items_with_repo.append({
                    'repo': repo_name,
                    'label_type': 'NON_FEATURE',
                    'label': non_feature.get('label', ''),
                    'description': non_feature.get('description', '')
                })
            
            print(f"  Added {len(features)} features and {len(non_features)} non-features from {json_file.name}")
        except Exception as e:
            print(f"  Warning: Failed to read {json_file.name}: {e}")
    
    all_features.sort(key=lambda x: x.get('label', '').lower())
    all_non_features.sort(key=lambda x: x.get('label', '').lower())
    all_items_with_repo.sort(key=lambda x: x.get('label', '').lower())
    
    aggregated = {
        'features': all_features,
        'non_feature_labels': all_non_features
    }
    
    output_file_json = input_dir / 'all-features.json'
    with open(output_file_json, 'w', encoding='utf-8') as f:
        json.dump(aggregated, f, indent=2, ensure_ascii=False)
    
    output_file_csv = input_dir / 'all-features.csv'
    with open(output_file_csv, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['repo', 'label_type', 'label', 'description'])
        writer.writeheader()
        writer.writerows(all_items_with_repo)
    
    print(f"\n  Saved aggregated features to: {output_file_json.name}")
    print(f"  Saved aggregated CSV to: {output_file_csv.name}")
    print(f"  Total: {len(all_features)} features, {len(all_non_features)} non-feature labels")
    print(f"\n{'='*60}")
    print(f"Merge complete!")
    print(f"JSON: {output_file_json}")
    print(f"CSV:  {output_file_csv}")
    print(f"{'='*60}")


def find_feature_labels_dir() -> Path:
    input_path_str = getattr(config, 'FEATURE_LABELS_INPUT', 'phase_2_output_feature_labels_latest')
    input_path = Path(input_path_str)
        
    if input_path.is_dir():
        return input_path
    
    print(f"Warning: {input_path} not found, using phase_2_output_feature_labels_latest/ as default")
    return Path('phase_2_output_feature_labels_latest')


def main():
    input_dir = find_feature_labels_dir()
    
    if not input_dir.exists():
        print(f"Error: Directory does not exist: {input_dir}")
        print("Please run phase_2a_generate_initial_feature_labels.py first to create feature label files.")
        return
    
    aggregate_features(input_dir)


if __name__ == "__main__":
    main()
