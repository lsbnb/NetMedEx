from pathlib import Path

from evaluation.run_formal_ae_replay import (
    PROFILES,
    build_profile_run_dir,
    build_runner_command,
    build_replay_manifest,
)


def test_build_profile_run_dir() -> None:
    assert build_profile_run_dir(Path("out"), "C_one_hop") == Path("out/C_one_hop")


def test_build_runner_command_targets_profile_specific_run_dir() -> None:
    repo_root = Path("/repo")
    source_run_dir = Path("evaluation/formal/runs/formal-v1-gpt-5.6-terra")
    output_root = Path("evaluation/formal/runs/formal-v1-gpt-5.6-terra-ae-replay-v1")
    cmd = build_runner_command(
        repo_root,
        source_run_dir,
        output_root,
        "E_verified_gated_two_hop",
        model="gpt-5.6-terra",
        queries=Path("evaluation/formal/formal_run_queries.csv"),
        questions_metadata=Path("evaluation/formal/questions.csv"),
        force=True,
        skip_general_llm=True,
        skip_answer_generation=True,
    )
    assert cmd[:3] == [cmd[0], str(repo_root / "evaluation" / "run_formal_50.py"), "--queries"]
    assert "--hybrid-profile" in cmd
    assert cmd[cmd.index("--hybrid-profile") + 1] == "E_verified_gated_two_hop"
    assert cmd[cmd.index("--run-dir") + 1] == str(output_root / "E_verified_gated_two_hop")
    assert cmd[cmd.index("--reuse-corpora-dir") + 1] == str(source_run_dir / "questions")
    assert "--force" in cmd
    assert "--skip-general-llm" in cmd
    assert "--skip-answer-generation" in cmd


def test_build_replay_manifest_lists_all_profiles() -> None:
    manifest = build_replay_manifest(
        Path("evaluation/formal/runs/formal-v1-gpt-5.6-terra"),
        Path("evaluation/formal/runs/formal-v1-gpt-5.6-terra-ae-replay-v1"),
        PROFILES,
        model="gpt-5.6-terra",
        queries=Path("evaluation/formal/formal_run_queries.csv"),
        questions_metadata=Path("evaluation/formal/questions.csv"),
    )
    assert manifest["benchmark"] == "formal-v1-ae-replay"
    assert manifest["status"] == "running"
    assert manifest["profiles"] == list(PROFILES)
