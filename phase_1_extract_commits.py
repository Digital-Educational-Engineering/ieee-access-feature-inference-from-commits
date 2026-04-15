
import os
import csv
import subprocess
import shutil
from datetime import datetime
from pathlib import Path
import re
import json
import random
import config
from git import Repo, InvalidGitRepositoryError, NoSuchPathError


def get_commit_stats(repo_path, commit_hash):
    try:
        result = subprocess.run(
            ['git', 'show', '--numstat', '--format=', commit_hash],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True
        )
        
        lines = result.stdout.strip().split('\n')
        additions = 0
        deletions = 0
        files_changed = 0
        
        for line in lines:
            if line.strip():
                parts = line.split('\t')
                if len(parts) >= 2:
                    try:
                        add = int(parts[0]) if parts[0] != '-' else 0
                        delete = int(parts[1]) if parts[1] != '-' else 0
                        additions += add
                        deletions += delete
                        files_changed += 1
                    except ValueError:
                        # Skip binary files or other non-numeric entries
                        continue
        
        return additions, deletions, files_changed
    except subprocess.CalledProcessError:
        return 0, 0, 0


def is_git_repository(path: Path) -> bool:
    try:
        Repo(path, search_parent_directories=False)
        return True
    except (InvalidGitRepositoryError, NoSuchPathError):
        pass

    git_entry = path / ".git"
    if git_entry.exists():
        return True

    if (path / "HEAD").is_file() and (path / "objects").is_dir() and (path / "refs").is_dir():
        return True

    return False


def extract_commits_from_repo(repo_path):
    commits = []

    try:
        repo = Repo(repo_path, search_parent_directories=False)

        def clean_person_name(name: str | None) -> str:
            if not name:
                return ""
            normalized = str(name).replace('\t', ' ')
            normalized = re.sub(r"\s+", " ", normalized)
            return normalized.strip()

        def clean_email(email: str | None) -> str:
            if not email:
                return ""
            return str(email).replace('\t', '').strip()

        for commit in repo.iter_commits('--all'):
            full_message = commit.message or ''
            lines = full_message.splitlines()
            subject = lines[0] if lines else ''
            body = '\n'.join(lines[1:]).strip() if len(lines) > 1 else ''

            stats = commit.stats.total if commit.stats else {}
            additions = int(stats.get('insertions', 0))
            deletions = int(stats.get('deletions', 0))
            files_changed = int(stats.get('files', 0))

            parent_count = len(commit.parents) if commit.parents else 0
            parent_hashes = ';'.join(parent.hexsha for parent in commit.parents) if commit.parents else ''
            is_merge = parent_count > 1

            commits.append({
                'commit_hash': commit.hexsha,
                'parent_count': parent_count,
                'parent_hashes': parent_hashes,
                'is_merge': is_merge,
                'author_name': clean_person_name(getattr(commit.author, 'name', '') or ''),
                'author_email': clean_email(getattr(commit.author, 'email', '') or ''),
                'author_date': (commit.authored_datetime.isoformat() if getattr(commit, 'authored_datetime', None) else ''),
                'committer_name': clean_person_name(getattr(commit.committer, 'name', '') or ''),
                'committer_email': clean_email(getattr(commit.committer, 'email', '') or ''),
                'committer_date': (commit.committed_datetime.isoformat() if getattr(commit, 'committed_datetime', None) else ''),
                'subject': subject,
                'message_body': body,
                'files_changed': files_changed,
                'additions': additions,
                'deletions': deletions,
                'total_changes': additions + deletions,
            })

        return commits
    except (InvalidGitRepositoryError, NoSuchPathError) as e:
        print(f"Error: {repo_path} is not a valid Git repository: {e}")
        return []


def save_commits_to_csv(commits, output_file, include_repo_name=False):
    if not commits:
        print(f"No commits to save to {output_file}")
        return
    
    fieldnames = [
        'commit_hash',
        'parent_count',
        'parent_hashes',
        'is_merge',
        'author_name',
        'author_email',
        'author_date',
        'committer_name',
        'committer_email',
        'committer_date',
        'subject',
        'message_body',
        'files_changed',
        'additions',
        'deletions',
        'total_changes'
    ]
    
    if include_repo_name:
        fieldnames.insert(0, 'repository_name')
    
    with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(commits)
    
    print(f"Saved {len(commits)} commits to {output_file}")


def save_non_merge_commits_json(commits, output_file):
    non_merge_commits = [
        {
            'hash': commit['commit_hash'],
            'message': commit['subject']
        }
        for commit in commits
        if not commit.get('is_merge', False)
    ]
    
    if not non_merge_commits:
        print(f"  No non-merge commits to save to JSON")
        return
    
    random.shuffle(non_merge_commits)
    
    with open(output_file, 'w', encoding='utf-8') as jsonfile:
        json.dump(non_merge_commits, jsonfile, indent=2, ensure_ascii=False)
    
    print(f"  Saved {len(non_merge_commits)} non-merge commits to JSON")


def main():
    timestamp = datetime.now().strftime('%Y-%m-%d-%H%M%S')
    output_dir = Path(f'phase_1_output_extracted_commits-{timestamp}')
    output_dir.mkdir(exist_ok=True)
    
    print(f"Starting commit extraction...")
    print(f"Output directory: {output_dir}")
    print(f"Scanning repositories in: {config.REPOS_PATH}")
    try:
        prefix = getattr(config, "REPO_PREFIX", None)
    except Exception:
        prefix = None
    if prefix:
        print(f"Repository name prefix filter: '{prefix}'")
    
    repos_path = Path(config.REPOS_PATH)
    
    if not repos_path.exists():
        print(f"Error: Repository path does not exist: {config.REPOS_PATH}")
        return
    
    all_commits = []
    repo_count = 0
    
    for repo_dir in sorted(repos_path.iterdir()):
        if not repo_dir.is_dir():
            continue
        
        if prefix and not repo_dir.name.startswith(prefix):
            continue

        if not is_git_repository(repo_dir):
            if prefix:
                print(f"\nWarning: '{repo_dir.name}' matches prefix filter but is not a Git repository at this path. Skipping.")
            else:
                print(f"\nWarning: '{repo_dir.name}' is not a Git repository at this path. Skipping.")
            continue
        
        repo_count += 1
        repo_name = repo_dir.name
        print(f"\nProcessing repository: {repo_name}")
        
        commits = extract_commits_from_repo(repo_dir)

        merge_count = sum(1 for c in commits if c.get('is_merge', False))
        non_merge_count = len(commits) - merge_count
        
        print(f"  Total commits: {len(commits)} ({non_merge_count} regular, {merge_count} merge)")
        
        if commits:
            output_file = output_dir / f"{repo_name}_commits.csv"
            save_commits_to_csv(commits, output_file)
            
            json_file = output_dir / f"{repo_name}_commits.json"
            save_non_merge_commits_json(commits, json_file)
            
            for commit in commits:
                commit['repository_name'] = repo_name
            
            all_commits.extend(commits)
        else:
            print(f"  No commits found in {repo_name}")
    
    if all_commits:
        aggregate_file = output_dir / "all_repos_commits.csv"
        print('\nSaving aggregate CSV with all commits...')
        save_commits_to_csv(all_commits, aggregate_file, include_repo_name=True)

        phase_1_latest_dir = Path("phase_1_output_extracted_commits_latest")
        try:
            if phase_1_latest_dir.exists() or phase_1_latest_dir.is_symlink():
                if phase_1_latest_dir.is_dir() and not phase_1_latest_dir.is_symlink():
                    shutil.rmtree(phase_1_latest_dir)
                else:
                    phase_1_latest_dir.unlink()

            shutil.copytree(output_dir, phase_1_latest_dir)
            print(f"\nUpdated phase 1 latest snapshot: {phase_1_latest_dir} (copied from {output_dir.name})")
        except Exception as e:
            print(f"\nWarning: Failed to update phase 1 latest snapshot at '{phase_1_latest_dir}': {e}")

        print(f"\n{'='*60}")
        print(f"Extraction complete!")
        print(f"Processed {repo_count} repositories")
        print(f"Total commits extracted: {len(all_commits)}")
        print(f"Total non-merge commits: {sum(1 for c in all_commits if not c.get('is_merge', False))}")
        print(f"Output directory: {output_dir}")
        print(f"Phase 1 latest snapshot: {phase_1_latest_dir}")
        print(f"{'='*60}")
    else:
        print("\nNo commits found in any repository.")


if __name__ == "__main__":
    main()
