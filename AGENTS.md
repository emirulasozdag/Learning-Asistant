# AGENTS.md

## 3. Fail Loudly — Never Mask Errors Behind Fallbacks

Fallbacks that mask failures delay diagnosis and can corrupt application state. Propagate errors across internal and backend boundaries by raising an exception, returning an explicit error result, or logging and exiting where appropriate.

- Do not catch an error to return synthetic, empty, or hardcoded data that looks like a successful result.
- Catch errors to add context, translate them at a boundary, or present an actionable message to the user. Preserve the underlying cause for developers.
- Use a fallback only when it is semantically valid and architecturally intended, such as failing over from a CDN to its origin.

**Wrong**

```ts
try {
  return await llm.complete(prompt);
} catch {
  return "I don't know."; // Presents an outage as an answer.
}
```

**Right**

```ts
return await llm.complete(prompt); // The caller or boundary handles the failure.
```
