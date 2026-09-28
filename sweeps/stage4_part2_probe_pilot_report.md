# PILOT report — cost, tokens, reasoning presence, compliance (NO scores)

| provider | model | effort | thinking | strict tools | agent | trials | completed | cost $ | $ / trial | input tok | output tok | reasoning tok | trials w/ reasoning blocks | truncations | reasoning past 1st tool call | submit parsed | empty diagnosis |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| anthropic | claude-sonnet-5 | high | — | no | static | 10 | 10 | 0.2980 | 0.0298 | 112,687 | 7,261 | not reported | 10/10 | 0 | 0/0 | 10/10 | 0/10 |
| anthropic | claude-sonnet-5 | xhigh | — | no | static | 10 | 10 | 0.3427 | 0.0343 | 112,687 | 11,734 | not reported | 10/10 | 0 | 0/0 | 10/10 | 0/10 |

Total estimated cost: $0.6407 over 20 trials. *Reasoning tok* = the provider's reported reasoning-token breakout (already inside output tok); *not reported* where the provider gives none (Anthropic). *Trials w/ reasoning blocks* = trials with at least one thinking block / reasoning item. *Reasoning past 1st tool call* = multi-call trials with a reasoning block on a turn after the first; *submit parsed* = the final submit call's arguments parsed as an object; *empty diagnosis* = no usable `diagnosis.detected`. No detection, identification, evidence or recovery score is computed or shown.

