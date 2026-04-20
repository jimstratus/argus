## Full-codebase audit overlay

The input below is the complete state of a codebase (empty-tree → HEAD) presented as a unified diff. Treat this as a **full codebase audit**, not a PR review.

- Do NOT skip findings because "everything looks new" or "this is a greenfield implementation."
- Every file is in scope. Every function, every config key, every command template is in scope.
- Prioritize:
  - Logic bugs that will surface in normal operation (wrong operators, off-by-one, inverted conditions, null/undefined deref)
  - Security issues (injection via argv, logged secrets, unsafe deserialization, path traversal)
  - Resource leaks (unclosed handles, unbounded growth, connections without finally)
  - Contract violations (swallowed errors, silent failures, broken invariants)
  - API misuse (CLI flags that don't exist / do other things than assumed)
  - Concurrency issues (race conditions, non-atomic reads-then-writes)
- Flag issues confidently. Empty `{"findings": []}` is a valid answer only when you've actively looked and genuinely disagree with the premise that bugs exist.

Your baseline assumption should be: **this codebase has bugs. Find them.**
