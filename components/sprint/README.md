# AI-Assisted Sprint Intelligence

Owner: **Wahalathanthri E. I.**

Collects sprint data from Jira, monitors sprint progress and health, predicts the risk that a sprint
misses its commitment, analyses team productivity and workload, and turns all of it into explained
recommendations and a sprint report on the dashboard.

Decision support only: the component suggests, the team decides.

## Inputs and outputs

**Inputs** (per project, from Jira through the platform's connector; the research used the same fields from TAWOS):

| Input | Fields used | Why |
|---|---|---|
| Sprints | id, name, state, start date, end date, completion date | Sprint length and how far through the sprint "now" is |
| Issues | key, sprint, story points, status category (To Do / In Progress / Done), assignee, created, resolved | What was committed, what is done, who holds what |
| Issue change history | sprint moves, status changes, story point changes, each with a timestamp | Rebuild the sprint as it was on any day: what was committed, added, removed, finished |
| Planning baseline (from the Planning component) | average story points per issue | Size the unestimated issues |

**Outputs** (per active sprint, as platform insights shown on the Sprint dashboard):

| Output | Value | Explanation shown with it |
|---|---|---|
| `sprint-risk` | Probability (0-1) that the sprint delivers less than 80% of its commitment, and a level: low < 0.5 <= medium < 0.7 <= high | Top 5 SHAP drivers (which features pushed the risk up or down) and the recommended actions |
| `sprint-health` | Health score 0-100 and a band: healthy (>= 70), at-risk (40-70), critical (< 40) | How many points each warning sign took off |
| `sprint-burndown` | Committed work remaining per day, the ideal line, and the total in the sprint | |
| `sprint-workload` | Open / in-progress / done work per person, share of open work, imbalance (Gini 0-1) | Overloaded people, unassigned work |
| `sprint-report` | A written sprint summary (template, or rewritten by a local LLM) | The facts above in plain language |

## Methodology

```text
1. Jira sprints + issues + change history
2. Daily snapshots: the sprint's state on each day, using only changes made up to that moment
3. Health score: five warning signs -> a 0-100 score (rule-based, no training)
4. Risk model: 15 features at that moment -> XGBoost -> P(missed) + SHAP drivers
5. Productivity: velocity, say/do, over-commitment, workload per person
6. Recommendations: each fires on a data condition and is ranked by the SHAP drivers
7. Insights -> Sprint dashboard and sprint report
```

The same code runs on the research dataset and on live Jira data (`live/`), so the model sees the same
features in both.

**Snapshots.** For each sprint and each day, the issue change history is replayed up to that moment to
get: the issues in the sprint, their status category and story points. The **commitment** is what the
sprint held 24 hours after it started. From this every snapshot has: committed work, committed work
done, work added after the commitment, committed work removed, issues in To Do / In Progress, and
issues without story points. Work is measured in story points, or in issue counts when nothing in the
commitment was estimated.

### How the sprint health score is calculated

The score starts at 100 and each of five warning signs takes points off. Each sign is first scaled to 0..1:

| Warning sign | Formula (0..1) | Weight |
|---|---|---|
| Behind the burndown | `min(max(elapsed - delivered, 0) / max(elapsed, 0.25), 1)` | 0.45 |
| Work added mid-sprint | `added / committed` (capped at 1) | 0.20 |
| Committed work removed | `removed / committed` (capped at 1) | 0.10 |
| Unestimated issues | `issues without points / issues in sprint` | 0.10 |
| Late work not started | `(issues in To Do / issues in sprint) x elapsed` | 0.15 |

where `elapsed` = share of the planned sprint duration gone and `delivered` = committed work done / committed work.

```text
points taken off by a sign = 100 x weight x sign
health score = max(100 - sum of points taken off, 0)
band: healthy >= 70, at-risk 40-70, critical < 40
```

The burndown sign compares delivery with where the ideal burndown says the sprint should be, relative
to that point (floored at 25% of the sprint so the first days don't swing the score). Late work only
counts as the sprint goes on, which is why it is multiplied by `elapsed`.

**Worked example.** Halfway through (`elapsed` = 0.5), 40 points committed, 10 done (`delivered` = 0.25),
8 points added, nothing removed, 1 of 10 issues unestimated, 6 of 10 still in To Do:

| Sign | Value | Points off |
|---|---|---|
| Behind the burndown | (0.5 - 0.25) / 0.5 = 0.50 | 100 x 0.45 x 0.50 = 22.5 |
| Work added | 8 / 40 = 0.20 | 100 x 0.20 x 0.20 = 4.0 |
| Work removed | 0 | 0 |
| Unestimated | 1 / 10 = 0.10 | 100 x 0.10 x 0.10 = 1.0 |
| Late work not started | 0.6 x 0.5 = 0.30 | 100 x 0.15 x 0.30 = 4.5 |
| **Health score** | | **100 - 32 = 68, at-risk** |

(`tests/test_health.py` checks this behaviour; the same numbers come out of `sprint_health.health.assess`.)

The weights are design choices, not learned. Whether the score is useful was then measured: on the
test sprints it separates missed from delivered sprints with AUC 0.776 (0.71 / 0.81 / 0.83 at 25 / 50 / 75%
of the sprint). It is kept as the explainable baseline and as one of the model's features.

### Risk model

**Label:** missed = less than 80% of the committed work delivered by the end date.

**Features (15)**, all known at the moment of prediction:

| Group | Features |
|---|---|
| Time and size | share of sprint gone, sprint length (days), committed issues, committed points |
| Progress | share of the commitment delivered so far, burndown gap, health score |
| Scope | work added, work removed, share of issues unestimated |
| Flow | share of issues in To Do, share in progress |
| Team history | number of earlier sprints, their average delivery, their miss rate (only sprints that ended before this moment) |

**Models compared:** always "missed" (majority), the health score, logistic regression (median
imputation, standardisation), and XGBoost (grid of depth, trees, learning rate and minimum child weight,
chosen on validation: depth 2, 100 trees, learning rate 0.1, min child weight 1).

## Structure

| Folder / file | Purpose |
|---|---|
| `preprocessing/` | Load and clean the TAWOS export (`build_clean_dataset.py`) |
| `sprint_health/` | Daily snapshots from change logs (`snapshot.py`) and the health score (`health.py`) |
| `risk_prediction/` | Dataset, chronological split, models, SHAP explanations, freeze-before-test, charts |
| `productivity/` | Velocity, throughput, say/do, over-commitment, workload per person |
| `recommendations/` | Rules that turn signals into actions (`interventions.py`) and the sprint report (`report.py`) |
| `live/` | Platform Jira data -> the same tables and features, then the full pipeline |
| `service/` | FastAPI service the platform calls (port 8002) |
| `models/risk_model.joblib` | The released risk model, so the service runs without retraining |
| `research/` | One-off data investigations |
| `run_*.py` | Command-line entry points, in the order below |
| `tests/` | Unit tests on synthetic data (34; the dataset is not needed) |

## Data

TAWOS (Tawosi et al., MSR 2022), open-source Jira projects, exported from MySQL into three CSV files:

| File | Rows | Content |
|---|---|---|
| `final_sprint_issues.csv` | 7,997 | Issues with sprint, status, story points, dates |
| `final_sprint_metadata.csv` | 884 | Sprints with start, end and completion dates |
| `final_sprint_change_logs.csv` | 179,782 | Every field change: sprint moves, status, story points |

The raw files and everything under `data/` are not committed. The path is taken from `--raw-path`,
then `DEVINTEL_SPRINT_RAW_DATA`, then the default in `preprocessing/config.py`.

Key definitions:
- **Commitment**: the issues in the sprint 24 hours after it started (teams often fill the sprint just
  after pressing Start; `research/inspect_commitment.py`). 839 of 884 sprints have a commitment.
- **Missed**: less than 80% of the committed work delivered by the end date (story points, or issue
  counts when nothing was estimated). 68% of sprints miss.
- **Checkpoints**: predictions are made 25%, 50% and 75% of the way through each sprint, using only
  changes made up to that moment.

## Run the research pipeline

From `components/sprint`, with the virtual environment active:

```powershell
pip install -r requirements.txt
python -m preprocessing.build_clean_dataset      # data/clean/
python run_sprint_snapshots.py                   # data/snapshots/
python run_sprint_health.py                      # health score and its AUC
python run_risk_prediction.py build              # dataset + chronological split
python run_risk_prediction.py tune               # models compared on validation only
python run_risk_prediction.py freeze             # lock the settings + code fingerprint
python run_risk_prediction.py test               # the single test run, charts in data/risk/charts/
python run_risk_prediction.py final              # retrain on train + validation -> data/risk/risk_model.joblib
python run_productivity.py                       # velocity, over-commitment, workload
python run_recommendations.py                    # recommendations on the test sprints
python -m unittest discover -s tests             # 34 tests
```

To release a newly trained model, copy `data/risk/risk_model.joblib` to `models/`.

## Evaluation method

- **Split**: chronological within each project, 70 / 15 / 15% of sprints (599 / 120 / 120). Projects
  with fewer than 7 sprints go to training. A held-out sprint never starts before a training sprint.
- **No leakage**: features come from the snapshot at the checkpoint; team-history features use only
  sprints of the same project that had ended before that moment.
- **Freeze before test**: model choice and hyper-parameters are picked on validation, then frozen with
  a SHA-256 fingerprint of the code. The test split is run once; the script refuses to run it again or
  to run it after the code changed.
- **Uncertainty**: 95% bootstrap confidence intervals on AUC, resampling sprints.
- **Baselines**: always predict "missed" (majority), and the rule-based health score.

## Sprint test results

Test split: the newest 15% of sprints of each project, 120 sprints, scored at 3 checkpoints (360
predictions). Run once, after the settings were frozen.

| Model | AUC (95% CI) | AUC at 25% | at 50% | at 75% | Avg precision | Brier | Accuracy | Precision | Recall | F1 |
|---|---|---|---|---|---|---|---|---|---|---|
| Always "missed" | 0.500 | 0.500 | 0.500 | 0.500 | 0.733 | 0.250 | 0.733 | 0.733 | 1.000 | 0.846 |
| Health score | 0.776 (0.693-0.852) | 0.706 | 0.814 | 0.833 | 0.881 | | 0.744 | 0.926 | 0.708 | 0.803 |
| Logistic regression | 0.863 (0.787-0.926) | 0.798 | 0.886 | 0.894 | 0.940 | 0.124 | 0.842 | 0.829 | 0.989 | 0.902 |
| **XGBoost** | **0.872 (0.798-0.937)** | **0.802** | 0.885 | **0.923** | 0.935 | **0.104** | **0.858** | 0.851 | 0.977 | **0.910** |

(Health score alert = score below 70. Brier: lower is better; it only applies to probabilities.)

- **Early warning:** XGBoost already reaches AUC 0.80 a quarter of the way into the sprint, and 0.92 at 75%.
- **Confusion matrix (XGBoost, 360 predictions):** 258 missed sprints caught, 6 missed, 51 on-track
  correctly cleared, 45 false alarms. When it warns it is right 85% of the time; it flags about half
  of the on-track checkpoints, so it is a cautious early-warning tool.
- **Drivers (mean |SHAP|, log-odds):** delivered so far 0.72, team's earlier sprints 0.39, committed
  points 0.27, sprint length 0.22, committed issues 0.21, health score 0.19, burndown gap 0.16.
- The final model is retrained on train + validation (719 sprints) and saved as `models/risk_model.joblib`.
- Charts: `data/risk/charts/` (ROC curves, AUC by checkpoint, confusion matrix, feature importance).

## Logistic regression vs XGBoost

| | Logistic regression | XGBoost |
|---|---|---|
| Validation AUC (25 / 50 / 75%) | **0.898** (0.846 / 0.888 / 0.941) | 0.856 (0.784 / 0.854 / 0.914) |
| Test AUC (95% CI) | 0.863 (0.787-0.926) | **0.872** (0.798-0.937) |
| Test AUC at 75% | 0.894 | **0.923** |
| Test Brier (calibration) | 0.124 | **0.104** |
| Test accuracy / F1 | 0.842 / 0.902 | **0.858 / 0.910** |
| Test recall | **0.989** | 0.977 |
| How it explains | coefficient x standardised value (exact SHAP for a linear model) | TreeSHAP (exact, built into XGBoost) |
| Missing team history | needs imputation | handled natively |
| Non-linear effects | no | yes (e.g. "behind AND late in the sprint") |

- **They are statistically tied.** Logistic regression was better on validation and XGBoost on test,
  and the 95% intervals overlap almost completely. The honest conclusion is that both clearly beat the
  rule-based health score (AUC about +0.09) and neither beats the other on this data.
- **XGBoost is deployed.** It was fixed as the deployed model before the test split was run, because
  the proposal specified a gradient-boosted model and it handles missing team history without
  imputation. On test it also gave better calibrated probabilities (lower Brier) and the best
  late-sprint warning.
- Logistic regression stays in the code as a transparent cross-check.

## Productivity and recommendations

Productivity (839 sprints): median say/do 0.56, 0.52 issues finished per day, 2 committed issues
carried over. Committing more than the team's recent velocity raises the miss rate from 51%
(<= 0.8x velocity) to 84% (> 2x). Workload imbalance did not separate missed from delivered sprints
(67% vs 70%, 333 sprints with known assignees).

Recommendations (test sprints, 50% checkpoint; 73% of them missed):

| Recommendation | Sprints | Share that missed |
|---|---|---|
| Estimate the unestimated issues | 32 | 94% |
| Stop adding work mid-sprint | 30 | 93% |
| Reduce the sprint scope | 81 | 91% |
| Decide on work that hasn't started | 42 | 88% |
| Sprint bigger than recent velocity | 72 | 81% |
| Plan the next sprint from past delivery | 59 | 76% |
| Sprint is on track | 9 | 11% |

Rule thresholds were set before this run and not tuned on the test split.

## Limitations

- One dataset (TAWOS open-source projects); results may differ for other teams.
- About 15% of issues have no story points; those sprints fall back to issue counts.
- The 24-hour commitment window and the 80% threshold are definitions, not ground truth.
- The TAWOS export has no assignee column; assignees come from change logs and are known for only
  4,994 of 7,997 issues.
- The recommendation table shows the rules point at sprints in trouble; it does not show that following
  them saves a sprint (that needs a study with real teams).
- Live Jira returns at most the 100 latest changes per issue.
- Over-commitment is not a model feature yet (the model was frozen before it was measured): future work.

## Live use

The platform's Jira connector syncs sprints, issues and their change history (`expand=changelog`).
On **Run sprint analysis**, `service/analysis.py` returns five insights per active sprint:
`sprint-risk`, `sprint-health`, `sprint-burndown`, `sprint-workload` and `sprint-report`. The
dashboard (`platform/client/src/pages/SprintPage.jsx`) re-reads them every minute.

Without a model file the service falls back to the health score. Without change history, work is
counted as added if the issue was created after the sprint started. Setting `DEVINTEL_SPRINT_LLM=ollama`
(with `OLLAMA_URL`, `OLLAMA_MODEL`) lets a local LLM rewrite the report; the template report is used
whenever the LLM is off or unreachable.
