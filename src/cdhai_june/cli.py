from __future__ import annotations

import argparse
from pathlib import Path

from cdhai_june.config import load_config
from cdhai_june.pipeline import PatientAnalysisPipeline, manifest_as_text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cdhai-june",
        description="Run the CDHAI_June single-patient analysis agent.",
    )
    subparsers = parser.add_subparsers(dest="command")

    run = subparsers.add_parser("run", help="Run the full patient analysis cycle.")
    _add_run_args(run)

    profile = subparsers.add_parser("profile", help="Alias for a one-cycle dry run.")
    _add_run_args(profile)

    return parser


def _add_run_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--input", required=True, help="Patient data file or directory.")
    parser.add_argument("--patient-id", default=None, help="Override patient id.")
    parser.add_argument("--config", default="configs/default.yaml", help="YAML config path.")
    parser.add_argument("--cycles", type=int, default=None, help="Override narrative cycle count.")
    parser.add_argument("--llm-provider", default=None, help="Override LLM provider: mock, codex_oauth, openai_compatible.")
    parser.add_argument("--model", default=None, help="Override LLM model.")
    parser.add_argument("--output-dir", default=None, help="Override output directory.")
    parser.add_argument("--print-manifest", action="store_true", help="Print full manifest JSON.")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 2

    config = load_config(args.config)
    if args.command == "profile" and args.cycles is None:
        config.analysis.max_narrative_cycles = 1
        config.llm.provider = args.llm_provider or "mock"
    if args.cycles is not None:
        config.analysis.max_narrative_cycles = args.cycles
    if args.llm_provider:
        config.llm.provider = args.llm_provider
    if args.model:
        config.llm.model = args.model
    if args.output_dir:
        config.analysis.output_dir = Path(args.output_dir)

    pipeline = PatientAnalysisPipeline(config)
    manifest = pipeline.run(args.input, patient_id=args.patient_id)
    if args.print_manifest:
        print(manifest_as_text(manifest))
    else:
        print(f"Run complete: {manifest['paths']['run_dir']}")
        print(f"Final report: {manifest['final_report']}")
    return 0

