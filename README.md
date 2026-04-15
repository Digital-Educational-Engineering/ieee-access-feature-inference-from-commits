# Git Repository Analysis Tool

This repository accompanies our publication, **"LLM-Driven Feature Inference for Analyzing Student Git Collaboration."** It contains the code used to extract commit data, infer feature labels from commit messages, and classify commits for analyzing collaboration in student software projects.

The repository is released as a research artifact to support transparency and reproducibility. Contact and citation details are provided at the end of this README.

---

## Model Selection

This repository is currently set up for OpenAI models only. In our study, we used GPT-5 for deeper reasoning tasks such as repository-level inference and synthesis, and GPT-5 mini for large-scale commit classification where cost and speed mattered more. Other models and reasoning levels can be configured as you see fit in the `config.py` file (explained in the respective README sections below).

---

## Project Structure

```
/
│
├── README.md
├── requirements.txt
├── config.py
├── .env                    # Your OpenAI API key (create from .env.example)
├── .env.example            # Template for environment variables
├── LICENSE
│
├── phase_1_extract_commits.py                    # Phase 1: Extract commits
├── phase_2a_generate_initial_feature_labels.py   # Phase 2: Generate feature labels
├── phase_2b_merge_feature_labels.py              # Phase 2b: Merge features from all repos
├── phase_3_synthesise_labels.py                  # Phase 3: Synthesise labels
├── phase_4_commit_level_classification.py        # Phase 4: Label each commit
│...
```

---

## Installation

### Prerequisites

- Python 3.7 or higher
- Git installed on your system
- OpenAI API key (for Phase 2)

### Create a Virtual Environment

**On Windows:**
```bash
python3 -m venv venv
venv\Scripts\activate
```

**On macOS/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### Install Required Libraries

```bash
pip3 install -r requirements.txt
```

### Set Up OpenAI API Key

1. Copy the example environment file:
```bash
cp .env.example .env
```

2. Edit `.env` and add your OpenAI API key:
```
OPENAI_API_KEY=your-actual-api-key-here
```

**Note**: Never commit your `.env` file to version control. It's already in `.gitignore`.

---

## Phase 1: Commit Data Extraction

This phase extracts detailed commit information from multiple Git repositories and generates CSV and JSON files for analysis.

- Scans all subdirectories in `REPOS_PATH` that start with `REPO_PREFIX`
- Extracts comprehensive commit data: hash, parents, author, committer, dates, message, file changes, additions/deletions
- Identifies merge commits vs regular commits
- Generates outputs in a timestamped folder
- Updates `phase_1_output_extracted_commits_latest/` as a rolling snapshot (overwritten each run)

### Phase 1 Configuration

Open the `config.py` file and configure the following variables:

**Phase 1: Commit Extraction**
```python
# Path to the directory containing your Git repositories
REPOS_PATH = "/path/to/your/repositories"

# Only process repos starting with this prefix
REPO_PREFIX = "project-" 
```

### Phase 1 Running Instructions

1. Make sure your virtual environment is activated
2. Configure `REPOS_PATH` and `REPO_PREFIX` in `config.py`
3. Run the extraction script:

```bash
python3 phase_1_extract_commits.py
```

It will output results in a timestamped folder named `phase_1_output_extracted_commits-YYYY-MM-DD-HHMMSS/` containing:

**Per Repository:**
- `{repo}_commits.csv` - Full commit data with all columns
- `{repo}_commits.json` - **Randomized** list of non-merge commits (hash + message only) for LLM input

**Aggregate:**
- `all_repos_commits.csv` - All commits from all repositories combined

It also creates/overwrites `phase_1_output_extracted_commits_latest/` with the newest run (overwritten each time).

---

## Phase 2: Feature Label Generation

This phase uses OpenAI's Responses API to analyze commit messages and infer high-level product features and maintenance categories.

This phase is split into two separate scripts (Phase 2a and Phase 2b). Phase 2a generates feature/non-feature labels for each repository individually, while Phase 2b merges these labels into a single aggregated file. This separation allows for experimentation with different merging strategies without needing to re-run the expensive LLM calls in Phase 2a.

### Phase 2 Configuration

Open the `config.py` file and configure the following variables:

```python
# The OpenAI model and reasoning effort to use for feature generation
OPENAI_MODEL_PHASE_2 = "gpt-5"
OPENAI_MODEL_REASONING_EFFORT_PHASE_2 = "low"  # Options: "low", "medium", "high"

# (Phase 2a) The folder containing JSON files from Phase 1 (processes all *_commits.json files in that folder)
EXTRACTED_COMMITS_INPUT = "phase_1_output_extracted_commits_latest" 

# (Phase 2b) The directory containing individual repo feature files from Phase 2a
FEATURE_LABELS_INPUT = "phase_2_output_feature_labels_latest"
```

### Phase 2a Running Instructions

This script processes the JSON files generated in Phase 1, sends commit messages to OpenAI with a structured prompt, and generates feature/non-feature labels for each repository.

1. Make sure Phase 1 has completed and JSON files exist
2. Ensure your `.env` file is set up with `OPENAI_API_KEY`
3. Configure the following in the `config.py` file:
   - `OPENAI_MODEL_PHASE_2`
   - `OPENAI_MODEL_REASONING_EFFORT_PHASE_2`
   - `EXTRACTED_COMMITS_INPUT` 
5. Run the feature generation script:

```bash
python3 phase_2a_generate_initial_feature_labels.py
```

It will output results in a timestamped folder named `phase_2_output_feature_labels-YYYY-MM-DD-HHMMSS/` containing:

**Per Repository:**
- `{repo}_features.json` - Full OpenAI response with overview, features, and non-feature labels
- `{repo}_features.csv` - Tabular format with columns: `label_type` (FEATURE/NON_FEATURE), `label`, `description`

It also creates/overwrites the `phase_2_output_feature_labels_latest/` directory as a backup of the latest run, containing the same files for easy access in Phase 2b.


### Phase 2b Running Instructions

This script aggregates the individual feature labels from all repositories (from Phase 2a) into a single sorted JSON file. This allows for experimentation with different merging strategies without re-running the expensive LLM calls in Phase 2a.

1. Ensure Phase 2a has completed and individual `*_features.json` files exist inside the `phase_2_output_feature_labels_latest/` directory.
2. Configure the following in the `config.py` file:
   - `FEATURE_LABELS_INPUT`
3. Run the merge script:

```bash
python3 phase_2b_merge_feature_labels.py
```

It will output two files in the same `FEATURE_LABELS_INPUT` directory:

- `all-features.json` - Structured format for Phase 3 synthesis
- `all-features.csv` - Tabular format with repo tracking

Note: Lists are sorted alphabetically by label. Duplicates from different repos are preserved for Phase 3 to determine equivalence.

---

## Phase 3: Label Synthesis

This phase uses OpenAI's Responses API to analyse the aggregated feature labels from all repositories and synthesise them into a deduplicated, grouped list. Equivalent features (even with different labels) are grouped together with full origin tracking.

### Phase 3 Configuration

Open the `config.py` file and configure the following variables:

```python
# The OpenAI model and reasoning effort to use for label synthesis
OPENAI_MODEL_PHASE_3 = "gpt-5"
OPENAI_MODEL_REASONING_EFFORT_PHASE_3 = "low"  # Options: "low", "medium", "high"

# Single source of truth for Phase 2b and Phase 3
# Phase 2b writes all-features.json into this directory
# Phase 3 reads all-features.json from this same directory
FEATURE_LABELS_INPUT = "phase_2_output_feature_labels_latest"
```

### Phase 3 Running Instructions

1. Ensure Phase 2b has completed and `all-features.json` exists
2. Configure `FEATURE_LABELS_INPUT` in `config.py`
3. Run the synthesis script:

```bash
python3 phase_3_synthesise_labels.py
```

It will output results in a folder named `phase_3_output_synthesised_labels-YYYY-MM-DD-HHMMSS/` containing:

- `synthesised-features.json` - Structured format with groups of equivalent features and their origins
- `synthesised-features.csv` - Human-readable report with indented original labels

It also creates/overwrites `phase_3_output_synthesised_labels_latest/` as a rolling snapshot (overwritten each run) for easy access in Phase 4.

After this step in completed, a human can review the CSV output to verify the quality of the grouping and equivalence decisions made by the LLM before proceeding to Phase 4.

---

## Phase 4: Commit-Level Classification

This phase uses OpenAI's Responses API to classify each individual commit (from Phase 1) based on the synthesised feature labels (from Phase 3). The LLM determines which feature(s) each commit is related to, or if it's a non-feature maintenance commit.

### Phase 4 Configuration

Open the `config.py` file and configure the following variables:

```python
# The OpenAI model and reasoning effort to use for commit classification
OPENAI_MODEL_PHASE_4 = "gpt-5-mini"
OPENAI_MODEL_REASONING_EFFORT_PHASE_4 = "low"  # Options: "low", "medium", "high"

# Input directories (from Phase 1 and Phase 3)
EXTRACTED_COMMITS_INPUT = "phase_1_output_extracted_commits_latest"
SYNTHESISED_LABELS_INPUT = "phase_3_output_synthesised_labels_latest"
``` 

### Phase 4 Running Instructions

1. Ensure Phase 1 and Phase 3 have completed and required files exist
2. The script will reuse the same `EXTRACTED_COMMITS_INPUT` and `SYNTHESISED_LABELS_INPUT` variables in `config.py`, which are from Phase 1 and Phase 3 respectively
3. Run the commit classification script:
```bash
python3 phase_4_commit_level_classification.py
```

It will output results in a folder named `phase_4_output_commit_labels-YYYY-MM-DD-HHMMSS/` containing:

**Per Repository:**
- `{repo}_commits_labeled.csv` - Original commit data with the feature label assigned to each commit
- `{repo}_commits_labeled.json` - Same data in JSON format

It also creates/overwrites `phase_4_output_commit_labels_latest/` as a rolling snapshot (overwritten each run) for easy access.

---

## License

This project is licensed under the **Apache License 2.0**.

- You are free to use, modify, and redistribute the code under Apache-2.0 terms.
- Please retain license and notice text when redistributing.
- See the [LICENSE](LICENSE) file for full terms.

---

## Authors and Contact

**Authors**
- Rawan Gedeon, Bethlehem University
- Nasser Giacaman, University of Auckland

**Contact**
For any questions, please reach out to the authors:

- Rawan Gedeon: rawang@bethlehem.edu
- Nasser Giacaman: n.giacaman@auckland.ac.nz

---

## Citation

If you use this software in academic work, please cite the associated paper.

```bibtex
@article{git_commit_analysis_2026,
   title   = {LLM-Driven Feature Inference for Analyzing Student Git Collaboration},
   author  = {Rawan Gedeon and Nasser Giacaman},
   journal = {IEEE Access},
   year    = {2026},
   doi     = {COMING_SOON}
}
```
