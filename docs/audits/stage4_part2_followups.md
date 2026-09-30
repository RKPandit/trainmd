# Stage 4 Part 2 — follow-up counts after the spot check · EXPLORATORY / DESCRIPTIVE (no verdicts)

> Read-only counts over ALL 5,976 completed Part 2 trials (5,544 Stage A static, 432 Stage B ReAct), requested
> after the 60-file spot check (2026-09-29). Nothing here changes a verdict, an estimand or a rule. "Answered
> none" = a parsed submission with `detected: false`. "Opened train.py" / "read_config" are read from the tool traces.

## 1. ReAct silent-fault trials (leakage, neutral leakage, metric inflation), all arms of Stage B (off)
| condition | n | det, train.py opened | det, not opened | 'none' answers | ...of which read_config showed the planted key |
|---|---|---|---|---|---|
| claude-sonnet-5 (effort=xhigh) | 54 | 36/45 (0.80) | 0/9 (0.00) | 18 | 18/18 (1.00) |
| claude-sonnet-5 (thinking=disabled) | 54 | 29/44 (0.66) | 0/10 (0.00) | 25 | 25/25 (1.00) |
| gpt-5.6-luna (effort=medium, strict) | 54 | 46/54 (0.85) | — | 3 | 3/3 (1.00) |
| gpt-5.6-luna (effort=none, strict) | 54 | 10/54 (0.19) | — | 44 | 44/44 (1.00) |

'none' answers whose rationale calls the accuracy typical/expected for Adult: {'claude-sonnet-5 (effort=xhigh)': '5/18', 'claude-sonnet-5 (thinking=disabled)': '11/25', 'gpt-5.6-luna (effort=medium, strict)': '0/3', 'gpt-5.6-luna (effort=none, strict)': '0/44'}

## 2. ReAct trials that ended without submit (all Stage B trials)
| claude-sonnet-5 (effort=xhigh) | no submit 0/108 (0.00) | termination reasons {'submitted': 108} |
| claude-sonnet-5 (thinking=disabled) | no submit 0/108 (0.00) | termination reasons {'submitted': 108} |
| gpt-5.6-luna (effort=medium, strict) | no submit 5/108 (0.05) | termination reasons {'submitted': 103, 'ended_without_submit': 5} |
| gpt-5.6-luna (effort=none, strict) | no submit 0/108 (0.00) | termination reasons {'submitted': 108} |

## 3. Luna-none ReAct, per mechanism
| data_leakage | n 36 | detected 4/36 (0.11) | answered 'none' 32/36 (0.89) | no submit 0/36 (0.00) |
| label_corruption | n 18 | detected 8/18 (0.44) | answered 'none' 10/18 (0.56) | no submit 0/18 (0.00) |
| lr_warmup | n 18 | detected 18/18 (1.00) | answered 'none' 0/18 (0.00) | no submit 0/18 (0.00) |
| metric_inflation | n 18 | detected 6/18 (0.33) | answered 'none' 12/18 (0.67) | no submit 0/18 (0.00) |
| shape_mismatch | n 18 | detected 18/18 (1.00) | answered 'none' 0/18 (0.00) | no submit 0/18 (0.00) |

## 4. Sonnet: correct diagnosis (detection + identification, faulty) with no repair
| claude-sonnet-5 (effort=xhigh) | react | correct dx 90 | no repair 0/90 (0.00) (repair_spec null 0) | repair-less with ignored fields 0 |
| claude-sonnet-5 (effort=xhigh) | static | correct dx 633 | no repair 3/633 (0.00) (repair_spec null 3) | repair-less with ignored fields 0 |
| claude-sonnet-5 (thinking=disabled) | react | correct dx 83 | no repair 2/83 (0.02) (repair_spec null 2) | repair-less with ignored fields 0 |
| claude-sonnet-5 (thinking=disabled) | static | correct dx 639 | no repair 40/639 (0.06) (repair_spec null 40) | repair-less with ignored fields 0 |
ignored field names on repair-less correct diagnoses: []

## 5. Strict mode: submit truncated at the output cap (unparseable)
| gpt-5.6-luna (effort=medium, strict) | react | truncated 1/108 (0.01) | mean evidence refs before the cut 4 | prefix says detected:true 1/1 |
| gpt-5.6-luna (effort=medium, strict) | static | truncated 1/924 (0.00) | mean evidence refs before the cut 5 | prefix says detected:true 1/1 |
| gpt-5.6-luna (effort=none, strict) | react | truncated 0/108 |
| gpt-5.6-luna (effort=none, strict) | static | truncated 5/924 (0.01) | mean evidence refs before the cut 4 | prefix says detected:true 5/5 |
| gpt-6-luna (effort=medium, strict) | static | truncated 0/924 |
| gpt-6-sol (effort=medium, strict) | static | truncated 0/924 |

## Reading

1. **ReAct silent faults (leakage, neutral leakage, metric inflation).**
   - **Sonnet never detected one without opening `train.py`** (0/9 xhigh, 0/10 off). With it opened, it
     detected 0.80 (xhigh) and 0.66 (off).
   - **Every "none" answer, in all four conditions, had read the config with the planted key in it**
     (Sonnet off 25/25, xhigh 18/18, Luna medium 3/3, Luna none 44/44). The key was visible and not judged
     anomalous without its code path.
   - Sonnet's misses often justify the inflated accuracy as normal for the dataset: 11/25 (off) and 5/18
     (xhigh) call it typical or expected for Adult. This is a strict text match, so a lower bound on the
     hand-read impression.
2. **Ending without submit:** Luna medium ReAct 5/108 (4 of them on silent-fault cases); 0 for every other
   condition. Of Luna medium's 8 silent-fault non-detections: 4 never submitted, 1 was a strict-mode
   truncation (§5), and 3 answered "none". So most of its "misses" are compliance, not diagnosis.
3. **Luna `none` ReAct answers "none" on real silent faults:** leakage 32/36, metric inflation 12/18,
   label corruption 10/18. It detects every lr_warmup and crash case. This is the opposite of its static
   behaviour (which flags nearly everything; `stage4_part2_control_false_alarms.md`). It opened `train.py`
   in 89/90 non-crash trials.
4. **Sonnet repair omission** is a static, thinking-off pattern: a correct diagnosis with `repair_spec` null
   in 40/639 (6%). For comparison: 3/633 static xhigh, 2/83 ReAct off, 0/90 ReAct xhigh. None of these
   trials carries a repair in `ignored_fields`, so no repair was lost to parsing; it was omitted.
5. **Strict-mode truncation:** see LIMITATIONS L35 (added 2026-09-29). 7 of 3,996 strict trials. It is
   runaway WHITESPACE after 3–4 distinct evidence refs, not a long list of refs, and every truncated prefix
   begins `"detected":true`.
