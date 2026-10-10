# Issue #66: Discovery does not record ports added to scan settings on known devices

Branch: `issue-66-discovery-new-ports`
Status: blocked

## Finish condition

- [ ] After adding TCP 8080 to the saved scan settings and rescanning an already-known app01, `GET /api/system/hosts/<id>/ports` lists 8080/tcp.
- [ ] After adding TCP 2222 to the saved scan settings and rescanning an already-known legacy01, `GET /api/system/hosts/<id>/ports` lists 2222/tcp.
- [ ] The same holds when the added ports are included through ranges 8000-8099 and 2200-2299.

## Plan

1. [ ] Add an isolated regression exercising saved discovery settings, mocked nmap XML, repeat scans, persistence and port inventory in `server/tests/unit/test_network_discovery.py`; run it red.
2. [ ] Correct the narrow cause in `server/app/network_discovery/network_discovery.py` or `server/app/network_discovery/port_lifecycle.py` (and only directly necessary discovery code); run the focused file and `scripts/verify.sh backend`.
3. [ ] Update `spec files/Data_Model_and_Integrations.md` and `spec files/Implementation_Status.md` if the investigation establishes a documented gap; run `scripts/verify.sh docs` and `scripts/verify.sh all`.

## Round log

| Round | Change made | Check run | Result |
|---|---|---|---|

## State for the next session

- Last check run (exact command): `gh issue view 66 --json number,title,body,comments,labels,state,url`
- Result (first failing lines, or "green"): green; issue text obtained after plain `gh issue view 66` failed on deprecated classic project cards.
- Hypothesis: nmap invocation or port lifecycle handling of known devices drops newly configured ports; not yet determined.
- Next action (one specific step, not "continue"): Ask a person to authorize work in the sensitive `app/network_discovery/` module and clarify whether the issue's Expected section is the intended finish condition.

## Decisions and notes

The issue's Expected section supplies the three observable acceptance outcomes above, but there is no separately named finish-condition section. The workflow requires stopping if a finish condition is absent. `spec files/Engineering_Standards.md` labels `app/network_discovery/` sensitive, requiring a person before implementation. No code has been changed and no live scan or lab run is planned. Injection/secret-exposure review will be required if authorized.
