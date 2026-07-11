# Tools

Built-in tools:

- `list_files`: list files under the project root
- `read_file`: read UTF-8 text files, optionally by line range
- `write_file`: create or overwrite UTF-8 text files
- `edit_file`: exact text replacement with expected replacement count
- `shell`: run commands from the project root

All tool arguments are validated with JSON Schema before execution.

## Shell Safety

Blocked commands fail immediately. Examples include recursive force delete patterns, `git reset --hard`, `git clean -fd`, `format`, `mkfs`, `shutdown`, and `reboot`.

In the default `strict` profile, every shell command requires approval unless `--yes` is passed. Git commands are treated as risky operations. In `relaxed`, safe shell commands can run without approval, while git commands, package installs, file deletes, file moves, and permission changes still require approval.

Commands that mention paths outside the project root are blocked unless `allow_outside_root=true` is provided by the model, which still makes the command risky and approval-gated.

## Execution

`read_file` and `list_files` are marked parallel-safe. The execution engine can run consecutive safe calls concurrently, then returns results in the original tool-call order. Mutating tools and shell commands run serially.
