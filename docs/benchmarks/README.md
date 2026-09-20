# OpsPilot Benchmarking

Phase 15 provides the benchmark data model, metric calculations, scenario
labels, and result aggregator. The framework is ready for execution adapters;
no baseline-vs-OpsPilot benchmark results have been claimed yet.

Current status: **Benchmark framework implemented; results pending execution.**

Start with a plan generated from the actual simulator catalog:

```powershell
python scripts/benchmarks/run_benchmark.py --mode catalog --trials 10
```

Once a real baseline/OpsPilot adapter has recorded `TrialResult` records:

```powershell
python scripts/benchmarks/run_benchmark.py --mode aggregate --input path/to/raw-trials.json --output docs/benchmarks/results
```

Generated JSON results are ignored by Git. Markdown reports from actual runs
may be retained under `docs/benchmarks/results/` with their raw input and
configuration.
