# MEMORY — NovaAML (Graph analysis)

## Notation Registry
| Variable | Convention | Anti-pattern |
|---|---|---|
| Account label | `is_laundering` = account in ≥1 laundering tx (sender or receiver) | Labelling only senders |
| Amounts | `amt_vnd` = amt_paid × implied USD rate × `USD_VND` | Using raw amounts across currencies |

## Estimand Registry
| What we estimate | Identification | Key assumptions |
|---|---|---|
| Ranking quality of rule-based graph score vs IBM labels (PR-AUC primary) | Out-of-the-box rules, thresholds locked in `log/plans/2026-11-01_aml-streamlit-vn.md` | SIMO overlay excluded from primary eval (label leakage) |

## Key Decisions
| Decision | Rationale | Date |
|---|---|---|
| Features on full HI-Small (5.08M tx), app shows subset only | Sampling normal tx would inflate precision | 2026-11-01 |
| Cycle search drops accounts with >50 counterparties, length ≤ 6, 7-day windows | Keeps enumeration bounded (~14 s) | 2026-11-01 |
| No real Vietnamese bank names; banks shown as `NH-xxx` | Avoid impersonation / misleading mapping | 2026-11-01 |

## Citations

## Anti-Patterns

## Code Pitfalls
| Bug | Impact | Fix |
|---|---|---|
| [LEARN:code] Column named `flags` → `df.flags` returns pandas `Flags` object | AttributeError on `.apply` | Name the column `signals`; use `df["col"]` |
| [LEARN:code] Windows console cp1252 can't print Vietnamese | UnicodeEncodeError in scripts | `sys.stdout.reconfigure(encoding="utf-8")` or `PYTHONIOENCODING=utf-8` |
| [LEARN:code] IBM AML CSV has two `Account` columns and zero-padded bank IDs | Wrong joins / lost leading zeros | Read with explicit `names=` and `dtype=str` for banks/accounts |
