"""
Configuration file for Git Repository Analysis Tool
"""

# --------------------------------------------------------------
# Phase 1 (Commit Extraction) Configuration
# --------------------------------------------------------------
# Path to the directory containing your Git repositories
# Each repository should be in its own subdirectory within the REPOS_PATH:
REPOS_PATH = "/Users/username/Downloads/all_repos/"  # <-- UPDATE THIS PATH

# Only repositories with names starting with this prefix will be processed:
REPO_PREFIX = "project-" # <-- UPDATE THIS PREFIX

# --------------------------------------------------------------
# Phase 2 (Feature Label Generation) Configuration
# --------------------------------------------------------------
# A folder path containing JSON files from Phase 1 (processes all *_commits.json files in that folder)
# Tip: use the rolling latest snapshot so you don't need to update this after each Phase 1 run.
EXTRACTED_COMMITS_INPUT = "phase_1_output_extracted_commits_latest"
# Or pin to a specific run:
# EXTRACTED_COMMITS_INPUT = "phase_1_output_extracted_commits-2026-03-12-123208/"

# Specify the OpenAI model to use for Phase 2a feature label generation
OPENAI_MODEL_PHASE_2 = "gpt-5"
OPENAI_MODEL_REASONING_EFFORT_PHASE_2 = "low"  # Options: "low", "medium", "high"

# Single source of truth for label files used by both Phase 2b and Phase 3.
# Phase 2b reads *_features.json files from this directory and writes all-features.json there.
# Phase 3 then reads all-features.json from the same directory.
FEATURE_LABELS_INPUT = "phase_2_output_feature_labels_latest/"  
# Or pin to a specific run:
# FEATURE_LABELS_INPUT = "phase_2_output_feature_labels-2026-03-12-123208/"


# --------------------------------------------------------------
# Phase 3 (Synthesise Labels) Configuration
# --------------------------------------------------------------
# Specify the OpenAI model to use for Phase 3 label synthesis
OPENAI_MODEL_PHASE_3 = "gpt-5"
OPENAI_MODEL_REASONING_EFFORT_PHASE_3 = "low"  # Options: "low", "medium", "high"

# This phase reads from FEATURE_LABELS_INPUT (same as Phase 2b output), so no separate config needed here.


# --------------------------------------------------------------
# Phase 4 (Label Commits with Synthesised Labels) Configuration
# --------------------------------------------------------------
# Specify the OpenAI model to use for Phase 4 commit classification
OPENAI_MODEL_PHASE_4 = "gpt-5-mini"
OPENAI_MODEL_REASONING_EFFORT_PHASE_4 = "low"  # Options: "low", "medium", "high"

# This phase reads from EXTRACTED_COMMITS_INPUT (Phase 1 output) and from the output of Phase 3 (synthesised labels), so no separate config needed here.
