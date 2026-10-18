from pathlib import Path


DECISION_ROOT = Path(__file__).resolve().parent
DATASET_PATH = DECISION_ROOT / "calibration" / "dataset.json"
ARTIFACT_DIR = DECISION_ROOT / "calibration" / "artifacts"
# Fitted on gemma4:31b-cloud calibration rows. Llama maps stay in their own artifact folders.
CALIBRATOR_PATH = ARTIFACT_DIR / "gemma4-31b-cloud" / "calibrator.json"
PREDICTIONS_PATH = ARTIFACT_DIR / "raw_predictions.json"
REPORT_PATH = ARTIFACT_DIR / "evaluation_report.json"
REPORT_MD_PATH = ARTIFACT_DIR / "evaluation_report.md"
DIAGRAM_PATH = ARTIFACT_DIR / "reliability.svg"
RULES_PATH = DECISION_ROOT / "routing" / "rules.json"
