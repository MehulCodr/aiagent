from __future__ import annotations

from code_agent.approval import ApprovalLayer, PermissionPolicy, PermissionProfile


def test_permission_profiles_evaluate_shell_git_and_read_only(tmp_path) -> None:
    strict = PermissionPolicy(PermissionProfile.STRICT)
    relaxed = PermissionPolicy(PermissionProfile.RELAXED)
    read_only = PermissionPolicy(PermissionProfile.READ_ONLY)

    strict_shell = strict.evaluate("shell", {"command": "python --version"}, tmp_path)
    assert strict_shell.allowed
    assert strict_shell.requires_approval

    relaxed_shell = relaxed.evaluate("shell", {"command": "python --version"}, tmp_path)
    assert relaxed_shell.allowed
    assert not relaxed_shell.requires_approval

    git_status = relaxed.evaluate("shell", {"command": "git status"}, tmp_path)
    assert git_status.allowed
    assert git_status.requires_approval

    write = read_only.evaluate("write_file", {"path": "x.txt", "content": "x"}, tmp_path)
    assert not write.allowed


def test_approval_layer_auto_approves_or_denies(tmp_path) -> None:
    policy = PermissionPolicy(PermissionProfile.STRICT)
    auto = ApprovalLayer(policy=policy, auto_approve=True).authorize(
        "shell",
        {"command": "python --version"},
        tmp_path,
    )
    assert auto.allowed
    assert not auto.requires_approval
    assert "Auto-approved" in auto.reason

    denied = ApprovalLayer(policy=policy, callback=lambda *_args: False).authorize(
        "shell",
        {"command": "python --version"},
        tmp_path,
    )
    assert not denied.allowed
    assert denied.reason.startswith("Denied:")
