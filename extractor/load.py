import json
import sys
from pathlib import Path

from models.promotion import PromotionNormalized


_output_path: Path | None = None


def configure_output(output_path: str, reset: bool = True) -> Path:
    global _output_path

    _output_path = Path(output_path)
    _output_path.parent.mkdir(parents=True, exist_ok=True)
    if reset:
        _output_path.write_text("", encoding="utf-8")
    return _output_path


def _console_print(message: str) -> None:
    encoding = sys.stdout.encoding or "utf-8"
    safe_message = message.encode(encoding, errors="replace").decode(encoding, errors="replace")
    print(safe_message)


def load_promotion(promotion: PromotionNormalized):
    """Persist normalized promotions as JSONL for comparison and downstream import."""
    if _output_path is None:
        raise RuntimeError("load output is not configured")

    payload = promotion.model_dump(mode="json")
    with _output_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")


def announce_output() -> None:
    if _output_path is not None:
        _console_print(f">>> JSONL output: {_output_path}")
