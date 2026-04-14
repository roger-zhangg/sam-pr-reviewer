# Coding Guidelines

Built-in review guidelines for SAM PR Reviewer. These define what the reviewer looks for
and how findings are categorized.

## Categories

| Category | Description |
|---|---|
| `BUG` | Logic errors, incorrect behavior, off-by-one errors, null/undefined dereferences |
| `SECURITY` | Injection flaws, hardcoded secrets, XSS, insecure deserialization, path traversal |
| `ERROR_HANDLING` | Missing error handling, swallowed exceptions, incorrect error propagation |
| `INPUT_VALIDATION` | Missing or insufficient validation of inputs, parameters, or external data |
| `PERFORMANCE` | Unnecessary allocations, N+1 queries, missing pagination, blocking I/O in async code |
| `CONCURRENCY` | Race conditions, deadlocks, unsynchronized shared state, missing locks |
| `RESOURCE_MANAGEMENT` | Unclosed resources, missing cleanup, memory leaks, connection pool exhaustion |
| `NAMING` | Misleading names, abbreviations that reduce clarity, inconsistent naming conventions |
| `STYLE` | Only flag when it materially affects readability. Do not flag formatting preferences. |
| `DOCUMENTATION` | Missing docs on public APIs, misleading comments, outdated comments contradicting code |
| `TESTING` | Missing test coverage for new logic, tests that don't assert meaningful behavior |
| `GENERAL` | Issues that don't fit other categories |

## Review Criteria

### Security
- Flag hardcoded credentials, API keys, tokens, or secrets
- Flag SQL/NoSQL queries built with string concatenation or interpolation
- Flag use of `eval()`, `exec()`, `Function()`, or equivalent dynamic code execution
- Flag user input rendered without escaping (XSS)
- Flag path traversal vulnerabilities (unsanitized file paths from user input)
- Flag insecure cryptographic practices (weak algorithms, hardcoded IVs)
- Flag overly permissive CORS, CSP, or security headers
- Flag deserialization of untrusted data

### Error Handling
- Flag empty catch blocks that swallow errors silently
- Flag catch blocks that only log but don't re-throw or handle appropriately
- Flag missing error handling on I/O operations (file, network, database)
- Flag functions that return null/undefined on error instead of throwing
- Flag async operations without error handling (unhandled promise rejections)

### Input Validation
- Flag public API endpoints that don't validate request parameters
- Flag type coercion that could produce unexpected results
- Flag missing bounds checking on array/collection access
- Flag missing null/undefined checks before dereferencing

### Performance
- Flag database queries inside loops (N+1 problem)
- Flag unbounded queries without LIMIT/pagination
- Flag synchronous I/O in async/event-driven code
- Flag unnecessary object creation in hot paths
- Flag missing indexes suggested by query patterns
- Flag large data structures copied when a reference would suffice

### Concurrency
- Flag shared mutable state accessed without synchronization
- Flag race conditions in check-then-act patterns
- Flag potential deadlocks from inconsistent lock ordering
- Flag missing thread-safety annotations or documentation

### Resource Management
- Flag opened resources (files, connections, streams) without corresponding close/cleanup
- Flag missing try-with-resources, using, defer, or equivalent patterns
- Flag connection/pool creation without size limits
- Flag event listeners or subscriptions without cleanup

### General Best Practices
- Flag code duplication that should be extracted into a shared function
- Flag magic numbers/strings that should be named constants
- Flag overly complex functions (deeply nested, too many parameters, too long)
- Flag public API changes that break backward compatibility without documentation
- Flag TODO/FIXME/HACK comments introduced in new code without tracking issues
