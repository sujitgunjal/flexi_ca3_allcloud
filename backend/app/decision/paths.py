from pathlib import Path


DECISION_ROOT = Path(__file__).resolve().parent
DATASET_PATH = DECISION_ROOT / "calibration" / "dataset.json"
ARTIFACT_DIR = DECISION_ROOT / "calibration" / "artifacts"
# Fitted on llama3:8b calibration rows. The llama3.2:3b map stays at calibrator.json.
CALIBRATOR_PATH = ARTIFACT_DIR / "llama3-8b-candidate" / "calibrator.json"
PREDICTIONS_PATH = ARTIFACT_DIR / "raw_predictions.json"
REPORT_PATH = ARTIFACT_DIR / "evaluation_report.json"
REPORT_MD_PATH = ARTIFACT_DIR / "evaluation_report.md"
DIAGRAM_PATH = ARTIFACT_DIR / "reliability.svg"
RULES_PATH = DECISION_ROOT / "routing" / "rules.json"
