"""Runs the model-quality evals as LangSmith experiments and prints a summary.

From backend/, with LangSmith configured in .env:

    python -m evals.run guardrail                 # one set
    python -m evals.run all --reps 2 --label baseline
    python -m evals.run stays --limit 3           # a quick check on the first rows

The datasets in evals/datasets/*.jsonl are the source of truth. Each run copies them to a LangSmith
dataset (tripmate-<set>) when they've changed, then runs the matching target from targets.py over
every row and scores it with scorers.py. --reps runs the whole set several times, as separate
experiments, because the model doesn't answer identically every time: the spread between reps is
the noise a later change has to beat before it counts as better or worse.
"""
import argparse
import json
import statistics
import subprocess
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from langsmith import Client  # noqa: E402  (after load_dotenv, so it sees the LangSmith key)

from evals.scorers import SCORERS  # noqa: E402
from evals.targets import TARGETS  # noqa: E402

HERE = Path(__file__).parent
SETS = list(TARGETS)


def load_rows(name: str) -> list[dict]:
    return [json.loads(line) for line in (HERE / "datasets" / f"{name}.jsonl").read_text().splitlines() if line.strip()]


def sync_dataset(client: Client, name: str, rows: list[dict]):
    """Makes the LangSmith dataset match the local file, replacing its examples only when they differ"""
    dataset_name = f"tripmate-{name}"
    wanted = {
        row["id"]: {"inputs": row["inputs"], "outputs": row["expect"],
                    "metadata": {"id": row["id"], "flag": row.get("flag"), "source": row.get("source")}}
        for row in rows
    }

    if client.has_dataset(dataset_name=dataset_name):
        dataset = client.read_dataset(dataset_name=dataset_name)
        existing = list(client.list_examples(dataset_id=dataset.id))
        current = {
            (example.metadata or {}).get("id"): {"inputs": example.inputs, "outputs": example.outputs,
                                                 "metadata": {k: (example.metadata or {}).get(k) for k in ("id", "flag", "source")}}
            for example in existing
        }
        if current == wanted:
            return dataset
        client.delete_examples([example.id for example in existing])
        print(f"  {dataset_name}: local file changed, replacing {len(existing)} examples with {len(wanted)}")
    else:
        dataset = client.create_dataset(dataset_name, description=f"TripMate eval set: {name}. Source: backend/evals/datasets/{name}.jsonl")
        print(f"  {dataset_name}: created with {len(wanted)} examples")

    client.create_examples(dataset_id=dataset.id, examples=list(wanted.values()))
    return dataset


def evaluator_for(name: str):
    scorer = SCORERS[name]

    def evaluate_row(outputs: dict, reference_outputs: dict) -> dict:
        if not outputs:
            return {"results": [{"key": "error", "score": 0, "comment": "the target raised; see the run in LangSmith"}]}
        return {"results": [{"key": key, "score": int(passed), "comment": comment}
                            for key, passed, comment in scorer(outputs, reference_outputs)]}

    evaluate_row.__name__ = f"score_{name}"
    return evaluate_row


def git_version() -> str:
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "."], capture_output=True, text=True).stdout.strip()
        return f"{sha}{'+changes' if dirty else ''}"
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def run_set(client: Client, name: str, reps: int, limit: int | None, concurrency: int, label: str) -> list[list[dict]]:
    rows = load_rows(name)
    dataset = sync_dataset(client, name, rows)

    examples = sorted(client.list_examples(dataset_id=dataset.id), key=lambda example: example.metadata["id"])
    if limit:
        examples = examples[:limit]

    reps_results = []
    for rep in range(1, reps + 1):
        print(f"  {name}: rep {rep}/{reps} over {len(examples)} rows…")
        experiment = client.evaluate(
            TARGETS[name],
            data=examples,
            evaluators=[evaluator_for(name)],
            experiment_prefix=f"{name}-{label}",
            description=f"{name} eval, {label}, rep {rep} of {reps}",
            metadata={"label": label, "rep": rep, "code": git_version(), "set": name},
            max_concurrency=concurrency,
        )

        rows_out = []
        for result in experiment:
            run, example = result["run"], result["example"]
            scores = {r.key: (r.score, r.comment) for r in result["evaluation_results"]["results"]}
            rows_out.append({
                "id": example.metadata["id"],
                "flag": example.metadata.get("flag"),
                "outputs": run.outputs,
                "error": run.error,
                "latency": (run.end_time - run.start_time).total_seconds() if run.end_time else None,
                "scores": scores,
            })
        print(f"    experiment: {experiment.experiment_name}")
        reps_results.append(sorted(rows_out, key=lambda row: row["id"]))

    return reps_results


def summarise(name: str, reps_results: list[list[dict]]):
    metrics = sorted({key for rows in reps_results for row in rows for key in row["scores"]})
    header = "".join(f"  rep {i + 1:<5}" for i in range(len(reps_results)))
    print(f"\n{name.upper()}  ({len(reps_results[0])} rows)\n  {'metric':<16}{header}")

    for metric in metrics:
        cells = []
        for rows in reps_results:
            scored = [row["scores"][metric][0] for row in rows if metric in row["scores"]]
            cells.append(f"{sum(scored)}/{len(scored)}" if scored else "-")
        print(f"  {metric:<16}" + "".join(f"  {cell:<9}" for cell in cells))

    passed = [f"{sum(all(s for s, _ in row['scores'].values()) for row in rows)}/{len(rows)}" for rows in reps_results]
    print(f"  {'all checks':<16}" + "".join(f"  {cell:<9}" for cell in passed))

    latencies = [row["latency"] for rows in reps_results for row in rows if row["latency"]]
    calls = [row["outputs"].get("llm_calls", 0) for rows in reps_results for row in rows if row["outputs"]]
    if latencies:
        print(f"  {'latency':<16}  median {statistics.median(latencies):.2f}s, slowest {max(latencies):.2f}s per row")
    if calls:
        print(f"  {'model calls':<16}  {statistics.mean(calls):.1f} per row")

    # Every check that failed in any rep, with how often, so noise and real failures look different
    failures = {}
    for rows in reps_results:
        for row in rows:
            for metric, (score, comment) in row["scores"].items():
                if not score:
                    entry = failures.setdefault((row["id"], metric), {"flag": row["flag"], "count": 0, "comment": comment})
                    entry["count"] += 1

    if failures:
        print("  failed checks:")
        for (row_id, metric), entry in sorted(failures.items()):
            flag = f" [{entry['flag']}]" if entry["flag"] else ""
            print(f"    {row_id}{flag} {metric} ({entry['count']}/{len(reps_results)} reps): {entry['comment'][:150]}")


def main():
    parser = argparse.ArgumentParser(description="Run TripMate's model-quality evals")
    parser.add_argument("sets", nargs="+", choices=[*SETS, "all"])
    parser.add_argument("--reps", type=int, default=1, help="how many times to run each set, to measure noise")
    parser.add_argument("--limit", type=int, help="only the first N rows of each set")
    parser.add_argument("--concurrency", type=int, default=3, help="rows run at once; keep low for free-tier rate limits")
    parser.add_argument("--label", default="run", help="names the experiments, like 'baseline' or 'merged-supervisor'")
    args = parser.parse_args()

    names = SETS if "all" in args.sets else args.sets
    client = Client()
    results_dir = HERE / "results"
    results_dir.mkdir(exist_ok=True)

    for name in names:
        started = time.time()
        reps_results = run_set(client, name, args.reps, args.limit, args.concurrency, args.label)
        summarise(name, reps_results)
        print(f"  took {time.time() - started:.0f}s")

        stamp = time.strftime("%Y%m%d-%H%M%S")
        (results_dir / f"{name}-{args.label}-{stamp}.json").write_text(json.dumps(reps_results, indent=1, default=str))


if __name__ == "__main__":
    main()
