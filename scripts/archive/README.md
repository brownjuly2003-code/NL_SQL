# scripts/archive — FROZEN eval scripts, do not use

The nine scripts in this directory are frozen. They score predictions with the
raw `compare_results` comparator from `nl_sql.eval.metrics.execution_accuracy`,
which has a known defect: a prediction whose execution **failed** can still be
scored as a match when the gold query returns an **empty** result (the
"qid 518" class of false positives). Any accuracy numbers produced by these
scripts are suspect for that case.

Do not run or import these scripts for new eval work, and do not copy their
comparison logic. For rescoring, use the safe path instead:

- `scripts/audit_rescore.py`, which uses
  `nl_sql.eval.metrics.execution_accuracy.safe_compare_pred` (treats an
  exec-failed prediction as a non-match regardless of the gold result).

Frozen files:

- `archive_sweep.py`
- `ensemble_vote.py`
- `run_critique_retry.py`
- `run_groq_voting.py`
- `run_openrouter_voting.py`
- `run_planner_eval.py`
- `run_selfcon_retry.py`
- `run_sonnet_voting.py`
- `run_wide_schema_retry.py`

They are kept only as a record of the parked voting/retry experiments. If one
of them is ever needed again, migrate it to `safe_compare_pred` first.
