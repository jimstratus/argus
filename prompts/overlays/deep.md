## Deep review overlay

This diff may be large or touch multiple files. Prioritize:
- Cross-file consistency (callers updated to match signature changes, schema migrations paired with code)
- Semantic changes disguised as refactors
- State machine or invariant violations introduced by the change
- Feature-flag or config-flag states that were not updated consistently
- Hidden coupling (global state, singletons, module-level mutables) affected by the diff
