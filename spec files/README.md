# Pinpoint System Specifications

**Last verified against the repository:** 2026-09-27

This directory is the authoritative documentation set for Pinpoint. The root
`AGENTS.md` is only a router into these documents.

## Document index

| Document | Authority and purpose |
|---|---|
| [`System_Overview_and_Architecture.md`](System_Overview_and_Architecture.md) | Product boundaries, deployment shape, repository layout, technology stack, and high-level architecture |
| [`Backend_Modules_and_Routes.md`](Backend_Modules_and_Routes.md) | Flask module inventory, complete HTTP route catalog, permissions, response conventions, and shared helpers |
| [`Frontend_Modules_and_Routes.md`](Frontend_Modules_and_Routes.md) | React route/page map, component ownership, contexts, API clients, and page-access rules |
| [`Data_Model_and_Integrations.md`](Data_Model_and_Integrations.md) | Database ownership, model inventory, Nagios data semantics, scheduler, network discovery, NCPA, and plugin integration |
| [`Engineering_Standards.md`](Engineering_Standards.md) | Coding, validation, security, migration, test, and run rules |
| [`Agent_Workflow_and_CI.md`](Agent_Workflow_and_CI.md) | Task intake, agent loop, verification commands, CI pipeline, dev container, installer deployment contract |
| [`Implementation_Status.md`](Implementation_Status.md) | Current implemented surface, incomplete work, exclusions, and known code/spec mismatches |
| [`Display_Requirements.md`](Display_Requirements.md) | Normative Dashboard, Network Health, and alert-acknowledgement behavior and API shapes |
| [`Alerts_Notifications_History_Requirements.md`](Alerts_Notifications_History_Requirements.md) | Normative Alerts and Notifications History page behavior |
| [`Plugins_List.md`](Plugins_List.md) | Nagios Plugins 2.4.12 capability, argument, output, and performance-data reference |

## Document types

- **Normative requirements** define what the product must do. The two page
  requirement documents are authoritative for their named user experiences.
- **Architecture specifications** define boundaries and invariants that changes
  must preserve.
- **Inventories** describe the currently implemented code and must be refreshed
  when that code changes.
- **Reference catalogs** provide factual lookup information for a subsystem.

## Maintenance rule

Do not put substantial system documentation back into `AGENTS.md`. New material
belongs in the most specific document above. If no document owns it, create a
focused specification here and add it to both this index and the root router.
