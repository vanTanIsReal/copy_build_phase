"""Seeds the 6 demo accounts and Delivery/Quality datasets from
MULTI_AGENT_IMPLEMENTATION_PLAN.md §14.1-14.3, for real manual testing and demo/staging - not the
throwaway per-case seeding scripts/run_eval.py does for the golden dataset (that seeds synthetic
IDs matching eval/datasets/multi_agent_workspace_v1.jsonl and is torn down implicitly by reusing
the same rows every run; this script is meant to be run once against a real environment and leave
a stable, reusable account set behind).

Idempotent (plan requirement, §14.2's last line): every row is looked up by a fixed, stable id/key
before insert, and re-running this script updates rather than duplicates. Every account/message/
task below is synthetic - no real names, emails or content.

Usage (needs DATABASE_URL pointed at the environment to seed, same as the app):
    python scripts/seed_multi_agent_demo.py

Requires the multi-agent feature flags to already be turned on for these accounts to reach
anything past the /chat kill switch (see src/config.py, MULTI_AGENT_ENABLED and friends) - this
script does not touch flags, it only seeds data.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

import src.db.session as db_session  # noqa: E402
from src.auth.security import hash_password  # noqa: E402
from src.db.models import (  # noqa: E402
    AgentWorkspace,
    AgentWorkspaceConversation,
    AgentWorkspaceMembership,
    Conversation,
    ConversationParticipant,
    Message,
    Task,
    User,
    Workspace,
    WorkspaceMembership,
)

DEMO_PASSWORD = "OrbitDemo123!"

ORG_ID = "org-orbit-demo"
DELIVERY_WORKSPACE_ID = "aw-delivery-demo"
QUALITY_WORKSPACE_ID = "aw-quality-demo"
RELEASE_TARGET = "release-2026.09"

# email -> (display_name, org role, [(agent_workspace_id, business_role), ...])
_ACCOUNTS: dict[str, tuple[str, str, list[tuple[str, str]]]] = {
    "executive.demo@orbit.local": (
        "Executive Demo",
        "member",
        [(DELIVERY_WORKSPACE_ID, "executive_viewer"), (QUALITY_WORKSPACE_ID, "executive_viewer")],
    ),
    "delivery.lead@orbit.local": ("Delivery Lead", "member", [(DELIVERY_WORKSPACE_ID, "lead")]),
    "delivery.member@orbit.local": ("Delivery Member", "member", [(DELIVERY_WORKSPACE_ID, "member")]),
    "quality.lead@orbit.local": ("Quality Lead", "member", [(QUALITY_WORKSPACE_ID, "lead")]),
    "quality.member@orbit.local": ("Quality Member", "member", [(QUALITY_WORKSPACE_ID, "member")]),
    # Deliberately zero agent-workspace membership - proves an org admin does NOT automatically
    # get business entitlement to Delivery/Quality data (MULTI_AGENT_IMPLEMENTATION_PLAN.md §5.1
    # "Admin không tự động có quyền đọc dữ liệu nghiệp vụ").
    "workspace.admin@orbit.local": ("Workspace Admin", "owner", []),
}


async def _ensure_user(db, email: str, display_name: str) -> User:
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is None:
        user = User(email=email, password_hash=hash_password(DEMO_PASSWORD), display_name=display_name)
        db.add(user)
        await db.flush()
    else:
        # Idempotent re-seed always resets the password to the known demo one - this account set
        # is meant to be shareable/reproducible for a demo, not a real user's credentials.
        user.password_hash = hash_password(DEMO_PASSWORD)
        user.display_name = display_name
    return user


async def _ensure_org_membership(db, user_id: str, role: str) -> None:
    existing = (
        await db.execute(
            select(WorkspaceMembership).where(WorkspaceMembership.workspace_id == ORG_ID, WorkspaceMembership.user_id == user_id)
        )
    ).scalar_one_or_none()
    if existing is None:
        db.add(WorkspaceMembership(workspace_id=ORG_ID, user_id=user_id, role=role, status="active"))
    else:
        existing.role = role
        existing.status = "active"


async def _ensure_agent_membership(db, agent_workspace_id: str, user_id: str, business_role: str) -> None:
    existing = (
        await db.execute(
            select(AgentWorkspaceMembership).where(
                AgentWorkspaceMembership.agent_workspace_id == agent_workspace_id,
                AgentWorkspaceMembership.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        db.add(
            AgentWorkspaceMembership(
                agent_workspace_id=agent_workspace_id, user_id=user_id, business_role=business_role, status="active", consent_status="active"
            )
        )
    else:
        existing.business_role = business_role
        existing.status = "active"
        existing.consent_status = "active"


async def _ensure_conversation(db, conv_id: str, name: str, created_by: str, member_ids: list[str], ai_enabled: bool = True) -> Conversation:
    conversation = await db.get(Conversation, conv_id)
    if conversation is None:
        conversation = Conversation(
            id=conv_id, type="group", name=name, created_by=created_by, workspace_id=ORG_ID, ai_policy_version="v1", ai_enabled=ai_enabled
        )
        db.add(conversation)
        await db.flush()
    else:
        conversation.ai_enabled = ai_enabled
    existing_ids = {
        row
        for row in (
            await db.execute(select(ConversationParticipant.user_id).where(ConversationParticipant.conversation_id == conv_id))
        ).scalars()
    }
    for user_id in member_ids:
        if user_id not in existing_ids:
            db.add(ConversationParticipant(conversation_id=conv_id, user_id=user_id))
    return conversation


async def _ensure_agent_workspace_conversation(db, agent_workspace_id: str, conversation_id: str, classification: str, linked_by: str) -> None:
    existing = (
        await db.execute(select(AgentWorkspaceConversation).where(AgentWorkspaceConversation.conversation_id == conversation_id))
    ).scalar_one_or_none()
    if existing is None:
        db.add(
            AgentWorkspaceConversation(
                agent_workspace_id=agent_workspace_id, conversation_id=conversation_id, classification=classification, linked_by_user_id=linked_by
            )
        )


async def _ensure_message(db, msg_id: str, conversation_id: str, sender_id: str, content: str) -> None:
    if await db.get(Message, msg_id) is None:
        db.add(Message(id=msg_id, conversation_id=conversation_id, sender_id=sender_id, content=content))


async def _upsert_task(db, task_id: str, **fields) -> None:
    task = await db.get(Task, task_id)
    if task is None:
        db.add(Task(id=task_id, **fields))
    else:
        for key, value in fields.items():
            setattr(task, key, value)


async def main() -> None:
    async with db_session.async_session_maker() as db:
        org = await db.get(Workspace, ORG_ID)
        if org is None:
            db.add(Workspace(id=ORG_ID, type="organization", name="Orbit Demo Company", status="active"))
            await db.flush()

        users: dict[str, User] = {}
        for email, (display_name, org_role, _) in _ACCOUNTS.items():
            user = await _ensure_user(db, email, display_name)
            users[email] = user
            await _ensure_org_membership(db, user.id, org_role)
        await db.flush()

        delivery_ws = await db.get(AgentWorkspace, DELIVERY_WORKSPACE_ID)
        if delivery_ws is None:
            db.add(
                AgentWorkspace(
                    id=DELIVERY_WORKSPACE_ID, organization_workspace_id=ORG_ID, key="delivery", name="Product Delivery", agent_profile="product_delivery"
                )
            )
        quality_ws = await db.get(AgentWorkspace, QUALITY_WORKSPACE_ID)
        if quality_ws is None:
            db.add(
                AgentWorkspace(
                    id=QUALITY_WORKSPACE_ID, organization_workspace_id=ORG_ID, key="quality", name="Quality Assurance", agent_profile="quality_assurance"
                )
            )
        await db.flush()

        for email, (_, _, memberships) in _ACCOUNTS.items():
            for agent_workspace_id, business_role in memberships:
                await _ensure_agent_membership(db, agent_workspace_id, users[email].id, business_role)
        await db.flush()

        lead = users["delivery.lead@orbit.local"].id
        member = users["delivery.member@orbit.local"].id
        await _ensure_conversation(db, "conv-delivery-standup", "Delivery Standup", lead, [lead, member])
        await _ensure_conversation(db, "conv-delivery-release", "Delivery Release Planning", lead, [lead, member])
        await db.flush()
        await _ensure_agent_workspace_conversation(db, DELIVERY_WORKSPACE_ID, "conv-delivery-standup", "delivery", lead)
        await _ensure_agent_workspace_conversation(db, DELIVERY_WORKSPACE_ID, "conv-delivery-release", "delivery", lead)
        await _ensure_message(db, "msg-delivery-1", "conv-delivery-standup", lead, "Đang chặn ở review PR, cần thêm reviewer.")
        await _ensure_message(db, "msg-delivery-2", "conv-delivery-release", member, "Release 2026.09 dự kiến ship thứ Sáu tuần này.")

        q_lead = users["quality.lead@orbit.local"].id
        q_member = users["quality.member@orbit.local"].id
        await _ensure_conversation(db, "conv-quality-triage", "QA Bug Triage", q_lead, [q_lead, q_member])
        await _ensure_conversation(db, "conv-quality-release", "QA Release Signoff", q_lead, [q_lead, q_member])
        await db.flush()
        await _ensure_agent_workspace_conversation(db, QUALITY_WORKSPACE_ID, "conv-quality-triage", "quality", q_lead)
        await _ensure_agent_workspace_conversation(db, QUALITY_WORKSPACE_ID, "conv-quality-release", "quality", q_lead)
        await _ensure_message(db, "msg-quality-1", "conv-quality-triage", q_lead, "Bug crash khi lưu form - severity critical.")
        await _ensure_message(db, "msg-quality-2", "conv-quality-release", q_member, "2 test case regression đang fail trên staging.")

        now = datetime.now(UTC)

        # ---- Delivery dataset (§14.2): 10-15 tasks - 2 overdue, 2 due soon, 2 blocked, 1
        # ambiguous ("unassigned" per the plan - Task.owner_id is NOT NULL in this schema, so
        # modeled as needs_clarification=True on an owner assigned for bookkeeping only, same as
        # the app's existing proactive-detection "ambiguous owner" convention), 1 release_target
        # dependency shared with Quality, plus a few plain in-progress/completed tasks to round
        # out the count.
        delivery_tasks = [
            dict(id="task-delivery-overdue-1", title="Fix pipeline lỗi build", owner_id=lead, status="pending", priority="High", due_at=now - timedelta(days=3)),
            dict(id="task-delivery-overdue-2", title="Review PR #212", owner_id=member, status="pending", priority="Medium", due_at=now - timedelta(days=1)),
            dict(id="task-delivery-due-soon-1", title="Chuẩn bị release notes", owner_id=lead, status="in_progress", priority="Medium", due_at=now + timedelta(days=1)),
            dict(id="task-delivery-due-soon-2", title="Demo với stakeholder", owner_id=member, status="in_progress", priority="High", due_at=now + timedelta(days=2)),
            dict(id="task-delivery-blocked-1", title="Chờ QA sign-off release 2026.09", owner_id=lead, status="blocked", priority="High", release_target=RELEASE_TARGET),
            dict(id="task-delivery-blocked-2", title="Chờ vendor API key mới", owner_id=member, status="blocked", priority="Medium"),
            dict(id="task-delivery-ambiguous-1", title="Việc gì đó cần làm gấp (chưa rõ owner)", owner_id=lead, status="pending", priority="Medium", needs_clarification=True),
            dict(id="task-delivery-ambiguous-2", title="Theo dõi feedback khách hàng (chưa rõ hạn)", owner_id=member, status="pending", priority="Low", needs_clarification=True),
            dict(id="task-delivery-progress-1", title="Viết integration test cho checkout", owner_id=member, status="in_progress", priority="Medium"),
            dict(id="task-delivery-progress-2", title="Refactor module thanh toán", owner_id=lead, status="in_progress", priority="Low"),
            dict(id="task-delivery-done-1", title="Deploy staging build 2026.08", owner_id=lead, status="completed", priority="Medium"),
            dict(id="task-delivery-done-2", title="Cập nhật changelog", owner_id=member, status="completed", priority="Low"),
        ]
        for task in delivery_tasks:
            task.setdefault("conversation_id", "conv-delivery-standup")
            await _upsert_task(db, task.pop("id"), agent_workspace_id=DELIVERY_WORKSPACE_ID, source="manual", **task)

        # ---- Quality dataset (§14.3): 12-16 work items - 1 critical bug open (shared
        # release_target with Delivery's blocked task above, so cross-workspace dependency has a
        # real match), 2 failed tests, 1 blocked regression, several passed checks, 2
        # ambiguous/ needs-clarification items.
        quality_items = [
            dict(id="qa-bug-critical-1", title="Crash khi lưu form thanh toán", work_item_type="bug", severity="critical", quality_status="open", release_target=RELEASE_TARGET, owner_id=q_lead),
            dict(id="qa-bug-high-1", title="Sai định dạng ngày ở trang Profile", work_item_type="bug", severity="high", quality_status="open", owner_id=q_member),
            dict(id="qa-test-failed-1", title="Regression: đăng nhập Google", work_item_type="test_case", severity="medium", quality_status="failed", owner_id=q_lead),
            dict(id="qa-test-failed-2", title="Regression: tạo reminder", work_item_type="test_case", severity="medium", quality_status="failed", owner_id=q_member),
            dict(id="qa-test-blocked-1", title="Regression suite chờ môi trường staging", work_item_type="test_case", severity="high", quality_status="blocked", owner_id=q_lead),
            dict(id="qa-check-passed-1", title="Release check: smoke test API", work_item_type="release_check", severity="low", quality_status="passed", owner_id=q_member),
            dict(id="qa-check-passed-2", title="Release check: performance baseline", work_item_type="release_check", severity="low", quality_status="passed", owner_id=q_lead),
            dict(id="qa-test-passed-1", title="Test case: checkout thành công", work_item_type="test_case", severity="low", quality_status="passed", owner_id=q_member),
            dict(id="qa-test-passed-2", title="Test case: gửi reminder đúng giờ", work_item_type="test_case", severity="low", quality_status="passed", owner_id=q_lead),
            dict(id="qa-bug-ambiguous-1", title="Lỗi report từ user (chưa rõ bước tái hiện)", work_item_type="bug", severity="medium", quality_status="open", owner_id=q_member, needs_clarification=True),
            dict(id="qa-test-ambiguous-1", title="Kết quả test không rõ nguồn báo cáo", work_item_type="test_case", severity="low", quality_status="open", owner_id=q_lead, needs_clarification=True),
            dict(id="qa-check-progress-1", title="Release check: bảo mật đang chạy", work_item_type="release_check", severity="medium", quality_status="testing", owner_id=q_member),
        ]
        for item in quality_items:
            item.setdefault("conversation_id", "conv-quality-triage")
            await _upsert_task(db, item.pop("id"), agent_workspace_id=QUALITY_WORKSPACE_ID, status="suggested", priority="Medium", source="manual", **item)

        await db.commit()

    print("Seeded multi-agent demo data.")
    print(f"Organization: {ORG_ID} | Delivery workspace: {DELIVERY_WORKSPACE_ID} | Quality workspace: {QUALITY_WORKSPACE_ID}")
    print(f"Shared demo password for every account below: {DEMO_PASSWORD}")
    for email, (display_name, org_role, memberships) in _ACCOUNTS.items():
        roles = ", ".join(f"{ws}:{role}" for ws, role in memberships) or "no agent-workspace membership"
        print(f"  {email:32s} ({display_name}) org={org_role:6s} {roles}")
    print()
    print("Reminder: these accounts only reach anything past POST /chat once MULTI_AGENT_ENABLED")
    print("and the relevant PRODUCT_DELIVERY_AGENT_ENABLED/QUALITY_ASSURANCE_AGENT_ENABLED/")
    print("EXECUTIVE_AGENT_ENABLED flags are turned on in .env (src/config.py) - this script only")
    print("seeds data, it never touches flags.")
    print()
    print("Note: 'milestones' from the plan's §14.2 are not modeled as their own DB record yet")
    print("(see get_delivery_milestones's own data_gap) - only task-level due dates are seeded.")


if __name__ == "__main__":
    asyncio.run(main())
