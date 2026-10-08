# AGENTS.md — Pinpoint Specification Router

This file is the entry point for agents working on Pinpoint. It intentionally
contains no feature specification. The authoritative system specifications live
in [`spec files/`](spec%20files/).

## How to use this router

1. Identify the area affected by the task.
2. Read every document marked **Required** for that area before changing code.
3. Read the relevant source files named by those documents; specifications do
   not replace source inspection.
4. If implementation and documentation disagree, do not silently choose one.
   Use [`Implementation_Status.md`](spec%20files/Implementation_Status.md) to
   distinguish intended behavior from known gaps, then update the applicable
   specification as part of any approved behavior change.
5. Keep detailed rules in the specification files. Update this file only when a
   document is added, removed, renamed, or its routing purpose changes.

## Specification map

| When working on... | Read first | Also read |
|---|---|---|
| Any task | **Required:** [`README.md`](spec%20files/README.md), [`System_Overview_and_Architecture.md`](spec%20files/System_Overview_and_Architecture.md), [`Engineering_Standards.md`](spec%20files/Engineering_Standards.md) | [`Implementation_Status.md`](spec%20files/Implementation_Status.md) |
| Flask routes, permissions, response contracts, helpers | **Required:** [`Backend_Modules_and_Routes.md`](spec%20files/Backend_Modules_and_Routes.md) | [`Data_Model_and_Integrations.md`](spec%20files/Data_Model_and_Integrations.md) |
| Database models, migrations, Nagios data, scheduler, discovery, NCPA | **Required:** [`Data_Model_and_Integrations.md`](spec%20files/Data_Model_and_Integrations.md) | [`Backend_Modules_and_Routes.md`](spec%20files/Backend_Modules_and_Routes.md) |
| React pages, navigation, components, API wiring | **Required:** [`Frontend_Modules_and_Routes.md`](spec%20files/Frontend_Modules_and_Routes.md) | The relevant page requirements below |
| Dashboard or Network Health | **Required:** [`Display_Requirements.md`](spec%20files/Display_Requirements.md) | Backend, frontend, and data specifications |
| Alert acknowledgement | **Required:** [`Display_Requirements.md`](spec%20files/Display_Requirements.md) §4 | [`Alerts_Notifications_History_Requirements.md`](spec%20files/Alerts_Notifications_History_Requirements.md) |
| Alerts/notifications history | **Required:** [`Alerts_Notifications_History_Requirements.md`](spec%20files/Alerts_Notifications_History_Requirements.md) | Backend, frontend, and data specifications |
| Plugin Manager or plugin-driven monitoring | **Required:** [`Plugins_List.md`](spec%20files/Plugins_List.md), backend, frontend, and data specifications | Network discovery and Nagios config code named in the data spec |
| Open defects and follow-up from the plugin-driven monitoring acceptance run | **Required:** [`Plugin_Driven_Monitoring_Remediation.md`](docs/plans/Plugin_Driven_Monitoring_Remediation.md), [`Implementation_Status.md`](spec%20files/Implementation_Status.md) | [`Plugin_Driven_Monitoring_Plan.md`](docs/plans/Plugin_Driven_Monitoring_Plan.md), plugin acceptance plan in `server/tests/plans/` |
| Test-run reports, live-lab evidence, or recording a run result | **Required:** [`docs/test-runs/README.md`](docs/test-runs/README.md) | [`Agent_Workflow_and_CI.md`](spec%20files/Agent_Workflow_and_CI.md), [`Implementation_Status.md`](spec%20files/Implementation_Status.md) |
| Task workflow, verification, CI, deployment/installer contract | **Required:** [`Agent_Workflow_and_CI.md`](spec%20files/Agent_Workflow_and_CI.md) | [`Engineering_Standards.md`](spec%20files/Engineering_Standards.md) |
| Tests, migrations, style, validation, security | **Required:** [`Engineering_Standards.md`](spec%20files/Engineering_Standards.md) | The domain specification for the code being changed |
| Backend tests, fixtures, or test failures | **Required:** [`server/tests/README.md`](server/tests/README.md), [`Engineering_Standards.md`](spec%20files/Engineering_Standards.md) | The backend/domain specification for the behavior under test |
| Frontend tests | **Required:** [`Frontend_Modules_and_Routes.md`](spec%20files/Frontend_Modules_and_Routes.md), [`Engineering_Standards.md`](spec%20files/Engineering_Standards.md) | The page/domain specification for the behavior under test |
| Scope, unfinished work, or exclusions | **Required:** [`Implementation_Status.md`](spec%20files/Implementation_Status.md) | Relevant domain specification |

## Working an issue

To work a GitHub issue, follow [`.agent/workflows/work-issue.md`](.agent/workflows/work-issue.md).
It is the one procedure for every agent. The commands below only load it:

| Tool | Command |
|---|---|
| Claude Code | `/work-issue <n>` (`.claude/skills/work-issue/SKILL.md`) |
| OpenCode | `/work-issue <n>` (`.opencode/commands/work-issue.md`) |
| Any other agent | Tell it: "Follow `.agent/workflows/work-issue.md` for issue #<n>." |

Run each agent in its own checkout (`scripts/agent-worktree.sh <name>`); see
[`Agent_Workflow_and_CI.md`](spec%20files/Agent_Workflow_and_CI.md) "One checkout per agent".

## Verify before you finish

Run `scripts/verify.sh <docs|backend|frontend|all>` (the same commands CI runs)
and follow the loop in
[`Agent_Workflow_and_CI.md`](spec%20files/Agent_Workflow_and_CI.md). A task is
done when its finish condition holds and CI is green. Keep a progress file
(`.agent/progress/issue-<n>.md`) and checkpoint after each round so a stopped
job can be resumed; see the same document.

## Precedence

For implementation work, use this order:

1. The user's current request.
2. Behavioral requirements in the relevant page/domain specification.
3. Architecture, data ownership, security, and engineering standards.
4. The implementation-status inventory.
5. Existing code conventions after inspecting the relevant files.

`Implementation_Status.md` describes what exists; it does not override a
behavioral requirement. `Plugins_List.md` is a reference catalog, not a general
coding-standard document.

## Keeping the specifications current

When a change adds or removes a module, route, page, model, integration, major
setting, permission, or supported workflow, update the matching file in
`spec files/` in the same change. Update `Implementation_Status.md` when a gap is
completed or a new known gap is introduced. Add a route here only by linking to
its owning specification; do not duplicate the route contract in this router.
