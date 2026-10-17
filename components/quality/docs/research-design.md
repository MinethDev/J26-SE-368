# Software Quality Intelligence - PP1 Research Design

## Research Problem
Existing software quality evidence is fragmented across
static analysis, source-code metrics and development history,
making it difficult to predict and prioritize software units
that pose future quality risk.

## Primary AI Task
Software defect / quality-risk prediction.

## Unit of Analysis
File, class or module-level software unit depending on the
selected dataset.

## Inputs
- Static software metrics
- Complexity metrics
- Change metrics where available
- Historical defect information
- Static-analysis quality indicators where available

## Target
Binary defect/quality-risk label.

0 = non-defective / lower risk
1 = defective / higher risk

## Baselines
1. Majority/stratified classifier
2. Logistic Regression

## Proposed AI Approach
Random Forest classifier.

Additional models may be evaluated where justified by
experimental results.

## Explainability
SHAP feature attribution.

## Evaluation Metrics
- Precision
- Recall
- F1-score
- PR-AUC
- ROC-AUC
- Confusion matrix

## Validation
Prefer repository-level or temporal holdout where supported
by the selected dataset. Avoid leakage between training and
test data.

## PP1 Output
For a software unit, output:
- predicted defect/quality-risk probability
- risk classification
- major contributing features
- quality-prioritization information