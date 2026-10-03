# PILOT report — cost, tokens, reasoning presence, compliance (NO scores)

| provider | model | effort | thinking | strict tools | agent | trials | completed | cost $ | $ / trial | input tok | output tok | reasoning tok | trials w/ reasoning blocks | truncations | reasoning past 1st tool call | submit parsed | empty diagnosis |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| anthropic | claude-haiku-4-5-20251001 | — | — | no | static | 4 | 4 | 0.0485 | 0.0121 | 28,205 | 4,068 | not reported | 0/4 | 0 | 0/0 | 4/4 | 0/4 |
| anthropic | claude-haiku-4-5-20251001 | — | — | no | react | 4 | 4 | 0.1596 | 0.0399 | 243,153 | 7,873 | not reported | 0/4 | 0 | 0/4 | 4/4 | 0/4 |
| anthropic | claude-sonnet-5 | — | disabled | no | static | 4 | 4 | 0.0752 | 0.0188 | 34,096 | 703 | not reported | 0/4 | 0 | 0/0 | 4/4 | 0/4 |
| anthropic | claude-sonnet-5 | — | disabled | no | react | 4 | 4 | 0.1038 | 0.0260 | 81,365 | 3,741 | not reported | 0/4 | 0 | 0/4 | 4/4 | 0/4 |
| openai | gpt-5.6-luna | medium | — | yes | static | 4 | 4 | 0.0065 | 0.0016 | 21,260 | 1,024 | 357 | 4/4 | 0 | 0/0 | 4/4 | 0/4 |
| openai | gpt-5.6-luna | medium | — | yes | react | 4 | 4 | 0.0159 | 0.0040 | 123,305 | 5,274 | 2,526 | 4/4 | 0 | 4/4 | 4/4 | 0/4 |
| openai | gpt-5.6-luna | none | — | yes | static | 4 | 4 | 0.0067 | 0.0017 | 21,231 | 1,147 | 0 | 0/4 | 0 | 0/0 | 4/4 | 0/4 |
| openai | gpt-5.6-luna | none | — | yes | react | 4 | 4 | 0.0081 | 0.0020 | 54,911 | 1,769 | 0 | 0/4 | 0 | 0/4 | 4/4 | 0/4 |

Total estimated cost: $0.4244 over 32 trials. *Reasoning tok* = the provider's reported reasoning-token breakout (already inside output tok); *not reported* where the provider gives none (Anthropic). *Trials w/ reasoning blocks* = trials with at least one thinking block / reasoning item. *Reasoning past 1st tool call* = multi-call trials with a reasoning block on a turn after the first; *submit parsed* = the final submit call's arguments parsed as an object; *empty diagnosis* = no usable `diagnosis.detected`. No detection, identification, evidence or recovery score is computed or shown.
