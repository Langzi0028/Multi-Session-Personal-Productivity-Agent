from manual_memory_check import build_checks


def test_build_checks_reports_success_when_response_trace_and_memory_rows_are_valid():
    checks = build_checks(
        health_ok=True,
        create_ok=True,
        message_payload={"answer": "已记住。", "session_status": "completed"},
        trace_payload={"traces": [{"action_type": "final"}]},
        profile={"preferred_language": "中文", "answer_style": "简洁直接", "common_topics": []},
        semantic_rows=[{"content": "用户正在准备 Agent 开发岗笔试。"}],
        episodic_rows=[{"session_id": "manual_memory_check", "content": "用户要求记住偏好。"}],
        expected_text="Agent 开发岗笔试",
        session_id="manual_memory_check",
    )

    assert all(check.ok for check in checks)


def test_build_checks_reports_failure_when_memory_rows_are_missing():
    checks = build_checks(
        health_ok=True,
        create_ok=True,
        message_payload={"answer": "已记住。", "session_status": "completed"},
        trace_payload={"traces": [{"action_type": "final"}, {"action_type": "memory_extraction"}]},
        profile=None,
        semantic_rows=[],
        episodic_rows=[],
        expected_text="Agent 开发岗笔试",
        session_id="manual_memory_check",
    )

    failed_names = {check.name for check in checks if not check.ok}
    assert "profile memory" in failed_names
    assert "semantic memory" in failed_names
    assert "episodic memory" in failed_names
    assert "trace has no memory extraction event" in failed_names
