# PILOT report — cost, tokens, reasoning presence, compliance (NO scores)

| provider | model | effort | thinking | strict tools | agent | trials | completed | cost $ | $ / trial | input tok | output tok | reasoning tok | trials w/ reasoning blocks | truncations | reasoning past 1st tool call | submit parsed | empty diagnosis |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| anthropic | claude-opus-5-5 | medium | — | no | static | 10 | 10 | 0.6059 | 0.0606 | 112,563 | 7,783 | not reported | 10/10 | 0 | 0/0 | 10/10 | 0/10 |
| anthropic | claude-opus-5-5 | medium | — | no | react | 3 | 3 | 0.2010 | 0.0670 | 87,476 | 2,763 | not reported | 3/3 | 0 | 3/3 | 3/3 | 0/3 |
| anthropic | claude-sonnet-5 | — | disabled | no | static | 10 | 10 | 0.2702 | 0.0270 | 112,683 | 4,482 | not reported | 0/10 | 0 | 0/0 | 10/10 | 0/10 |
| anthropic | claude-sonnet-5 | — | disabled | no | react | 3 | 3 | 0.1432 | 0.0477 | 112,068 | 4,436 | not reported | 0/3 | 0 | 0/3 | 3/3 | 0/3 |
| anthropic | claude-sonnet-5 | medium | — | no | static | 10 | 10 | 0.2785 | 0.0278 | 112,687 | 5,308 | not reported | 8/10 | 0 | 0/0 | 10/10 | 0/10 |
| anthropic | claude-sonnet-5 | medium | — | no | react | 3 | 3 | 0.0874 | 0.0291 | 59,299 | 3,299 | not reported | 3/3 | 0 | 3/3 | 3/3 | 0/3 |
| openai | gpt-5.6-luna | medium | — | yes | static | 10 | 10 | 0.0225 | 0.0022 | 68,926 | 4,372 | 1,974 | 10/10 | 0 | 0/0 | 10/10 | 0/10 |
| openai | gpt-5.6-luna | medium | — | yes | react | 3 | 3 | 0.0123 | 0.0041 | 105,223 | 3,366 | 1,165 | 3/3 | 0 | 3/3 | 3/3 | 0/3 |
| openai | gpt-5.6-luna | none | — | yes | static | 10 | 10 | 0.0210 | 0.0021 | 71,314 | 2,678 | 0 | 0/10 | 0 | 0/0 | 10/10 | 0/10 |
| openai | gpt-5.6-luna | none | — | yes | react | 3 | 3 | 0.0163 | 0.0054 | 43,299 | 9,579 | 0 | 0/3 | 1 | 0/3 | 2/3 | 1/3 |
| openai | gpt-6-luna | medium | — | yes | static | 10 | 10 | 0.0115 | 0.0011 | 70,190 | 5,373 | 3,441 | 10/10 | 0 | 0/0 | 10/10 | 0/10 |
| openai | gpt-6-luna | medium | — | yes | react | 3 | 3 | 0.0069 | 0.0023 | 106,469 | 5,084 | 2,991 | 3/3 | 0 | 3/3 | 3/3 | 0/3 |
| openai | gpt-6-sol | medium | — | yes | static | 10 | 10 | 0.2071 | 0.0207 | 69,839 | 3,253 | 1,279 | 10/10 | 0 | 0/0 | 10/10 | 0/10 |
| openai | gpt-6-sol | medium | — | yes | react | 3 | 3 | 0.0926 | 0.0309 | 54,076 | 2,596 | 587 | 3/3 | 0 | 3/3 | 3/3 | 0/3 |

Total estimated cost: $1.9763 over 91 trials. *Reasoning tok* = the provider's reported reasoning-token breakout (already inside output tok); *not reported* where the provider gives none (Anthropic). *Trials w/ reasoning blocks* = trials with at least one thinking block / reasoning item. *Reasoning past 1st tool call* = multi-call trials with a reasoning block on a turn after the first; *submit parsed* = the final submit call's arguments parsed as an object; *empty diagnosis* = no usable `diagnosis.detected`. No detection, identification, evidence or recovery score is computed or shown.

