"""Settings for sprint recommendations and the written report. Thresholds are decision-support
rules a person can tune, not learned values; run_recommendations.py shows how often each fires."""
import os

# Risk bands for the model's probability that the sprint misses its commitment.
HIGH_RISK, MEDIUM_RISK = 0.7, 0.5

# A rule fires when its signal passes this level (shares are 0..1 of the sprint's work).
BEHIND_GAP = 0.3            # burndown gap from the health score
NOT_STARTED_SHARE = 0.3     # share of issues still To Do...
NOT_STARTED_FROM = 0.5      # ...once this much of the sprint has gone
SCOPE_ADDED_SHARE = 0.2
UNESTIMATED_SHARE = 0.2
TEAM_MISSED_RATE = 0.7      # team missed this share of its recent sprints
OVERCOMMIT_RATIO = 1.2      # same threshold as productivity.config

# Rules backed by a model feature are ranked higher when that feature is one of the
# top drivers pushing this sprint's risk up (from the SHAP explanation).
DRIVER_BOOST = 2

# Optional LLM-written report through a local Ollama server. Off unless DEVINTEL_SPRINT_LLM=ollama.
LLM_PROVIDER = os.getenv("DEVINTEL_SPRINT_LLM", "")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")
LLM_TIMEOUT_SECONDS = 60
