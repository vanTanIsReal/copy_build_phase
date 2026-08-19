# People Intelligence

## Product model

People is a workspace directory, not a social friend graph. Organization members appear
automatically, while the user only manages sparse private context:

- pin a person;
- add a private note;
- schedule a follow-up;
- keep truly external clients, vendors, partners, and mentors separately.

This avoids asking every employee to configure relationships with tens or hundreds of
coworkers. Existing external-contact and relationship records remain supported.

## Collaboration score v1

The API returns a 0–100 score calculated on read. It is a relevance signal, not an employee
performance score.

| Signal | Maximum | Calculation |
| --- | ---: | --- |
| Interaction recency | 35 | Exponential decay over time |
| Direct-message frequency | 25 | Log-normalized, capped at 40 messages/30 days |
| Shared-message frequency | 15 | Log-normalized, capped at 80 messages/30 days |
| Shared conversations | 15 | Linear, capped at 5 conversations |
| Open shared tasks | 10 | Linear, capped at 5 tasks |

Message frequency uses a rolling 30-day window. A person is `recent` when the last shared
interaction is within 14 days and `frequent` when the score is at least 55 or there are at
least 15 direct messages in the window. The response carries `score_version=v1` and
`metric_window_days=30` so clients and later migrations can distinguish metric definitions.

## Privacy and authorization

- Only active owner/admin/member accounts can read an organization directory; guests cannot.
- Preferences are directional and private to `(workspace, owner, subject)`.
- Another user never receives the owner's note, pin, or follow-up state.
- Metrics derive from message/task metadata. Message content is not copied into the people
  table or used by the score.
- AI people context is limited to five records, scoped to the authenticated user and active
  workspace, and only loaded for a named-person or people-related request.
- Private notes are marked as untrusted data before entering the AI prompt.

## API and storage

- `GET /api/v1/workspaces/{workspace_id}/people-insights`
- `PATCH /api/v1/workspaces/{workspace_id}/people-insights/{subject_user_id}`
- PostgreSQL table: `people_preferences`
- Alembic revision: `20260806_05`

The table stays sparse; collaboration metrics are derived from the existing indexed
conversation, message, and task records. The API caps directory reads at 100 results and the
service has a 500-member safety bound. For materially larger tenants, the next version should
move metric aggregation to a scheduled summary table without changing this API contract.
