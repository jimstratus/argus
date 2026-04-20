## Security focus (overlay)

This review is scoped to security. Prioritize finding:
- Authentication / session / authorization flaws
- Input validation failures (SQLi, command injection, XSS, SSRF, LDAP, XML/XXE)
- Cryptography misuse (weak algorithms, hardcoded keys, bad IVs, insecure RNG, missing integrity checks)
- Secrets or credentials leaking into logs, URLs, or error messages
- Insecure deserialization, path traversal, unsafe file operations
- TOCTOU and race conditions in security-critical paths
- Missing rate limiting or CSRF protection on state-changing endpoints
- Regex DoS and algorithmic complexity attacks

Other categories of findings are welcome but security findings take priority.
