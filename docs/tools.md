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

Risky commands require approval unless `--yes` is passed. Examples include package installs, file deletes, file moves, permission changes, and branch/reset/rebase commands.

Commands that mention paths outside the project root are blocked unless `allow_outside_root=true` is provided by the model, which still makes the command risky and approval-gated.
