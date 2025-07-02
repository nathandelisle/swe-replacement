1. harness/schema.py
Add the new optional string field "message" that may accompany any action.

Remove the numeric cap on "read_files" (it can now be unlimited).

Define six legal top-level keys (mutually exclusive except for "message"):

"read_files" (list [str])

"patch" (string – unified diff)

"run_tests" (bool true)

"list_directory" (string path)

"write_notes" (string text) — new (see §4)

"message" (string)

Export an updated constant ACTION_SCHEMA that enforces the above.

2. harness/entrypoint.py
Create two persistent files at start-up if they do not exist:

/workspace/notes.md (initial empty)

/workspace/.agent_state.json → {"last_message": ""}

After every turn:

Append the raw scratch-pad text to notes.md (prepend “\n\n### Turn <N>\n”).

Commit the change:

bash
Copy
Edit
git add notes.md .agent_state.json
git commit -m "turn <N> notes/message"
Handle "message": if present, overwrite last_message in .agent_state.json and commit as above.

Handle "write_notes": overwrite the entire notes.md with the provided text, then commit.

Token-budget guard (see §3); if summarisation occurs, commit the shortened notes.md.

3. harness/observation_builder.py (or the helper inside entrypoint.py)
Assemble the observation as a Python dict with keys (order doesn’t matter):

jsonc
Copy
Edit
{
  "directory_tree": "<depth-2 tree>",
  "git_diff": "<diff since previous commit>",
  "test_results": "<pytest JSON summary>",
  "requested_files": { "path1": "contents …", … },   // may be huge
  "previous_message": "<.agent_state.json['last_message']>"
}
Count prompt tokens before sending to Claude. Use a fast approximation (e.g. Anthropic tokenizer).

If tokens ≤ PROMPT_MAX (default 8 000) → send.

If tokens exceed:

Summarise the oldest 1 000 tokens of notes.md to ~150 tokens with a local Claude call:

text
Copy
Edit
"Summarise the following developer notes into <150 tokens while keeping exact code references>: …"
Replace that portion in notes.md, commit, recompute tokens, and retry once.

If still too large, return the observation { "error": "prompt_too_large" } instead of a normal observation.

4. harness/scratchpad.py
No logic change needed, but update the docstring to mention the new write_notes and message fields so the validator’s error messages stay accurate.

5. harness/claude_client.py
Insert a paragraph in the system prompt directly after the tool list:

pgsql
Copy
Edit
You also have a persistent “notes.md” file in the project root.
• Everything you write in the <scratchpad> is appended there automatically.
• You may read that file with read_files.
• You may overwrite it entirely by returning {"write_notes": "<full new text>"}.
You may send a short string forward to your next self using the "message" field.
Confirm max_tokens for outputs is still 4 096 (safe).

6. harness/logger.py
Add "message" and "notes_byte_size" fields to the action-result log entries so later analysis can correlate behaviour with note growth.

7. repos/reference/ (initial content)
Add an empty notes.md to the repo so git history starts at turn 0.

Add notes.md to neither .gitignore nor .dockerignore; we want it committed.

8. docker/Dockerfile
Install the Anthropic tokenizer tool for token counting, e.g.

dockerfile
Copy
Edit
RUN pip install tiktoken
9. Tests
No action; function stubs and empty tests remain.

10. README update
Append a “Memory & Messaging” section that explains:

scratch-pad → notes.md persistence

message passing semantics

summarisation policy.