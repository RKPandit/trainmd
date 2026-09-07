"""Silent-layer operators (dynamics tier).

Silent operators produce completed training runs (exitcode=0, finite metrics)
that silently degrade accuracy below the reference tolerance.  Crash or NaN
outcomes belong to the execution tier, not here.
"""
