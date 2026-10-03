# Pinpoint Frontend

## Start for development

From the repository root:

```bash
cd client
npm install
npm run dev
```

Open the local URL printed by Vite, normally
[http://localhost:5173](http://localhost:5173). The Flask backend should also
be running on `http://127.0.0.1:5000`; Vite proxies every `/api` request to
that server.

Useful commands:

```bash
npm run test       # run the Vitest suite once
npm run test:watch # run tests in watch mode
npm run lint       # run ESLint
npm run build      # type-check and create a production build
npm run preview    # preview the production build
```

## What this side does

The frontend is the React and TypeScript interface for Pinpoint. It presents
Nagios monitoring data through the Dashboard, Network Health, Device Inventory,
Reports, Logs, Plugin Manager, account management, and settings pages.

It communicates with the Flask backend through same-origin `/api/*` requests
and uses the backend's session cookie for authentication. Page visibility is
permission-aware, but the backend remains responsible for enforcing access.

## Important parts

- `src/App.tsx` defines browser routes and connects pages to the authenticated
  layout.
- `src/components/layout/` contains the sidebar, header, access guard, session
  timeout watcher, and maintenance banner.
- `src/contexts/CurrentUserContext.tsx` loads the signed-in user and their
  permissions.
- `src/contexts/SystemSettingsContext.tsx` combines system settings with
  per-user display preferences.
- `src/lib/api.ts` is the shared JSON API client; `pluginApi.ts` contains
  Plugin Manager request wrappers.
- `src/types/` contains API record types, view models, and response converters.
- `src/hooks/useNetworkRescan.ts` owns the reusable discovery/rescan workflow.

## Folder structure

```text
client/
|-- public/                 static browser assets
|-- src/
|   |-- components/        feature and shared UI components
|   |   |-- dashboard/
|   |   |-- network-health/
|   |   |-- device-inventory/
|   |   |-- plugin-manager/
|   |   |-- reports/
|   |   |-- settings/
|   |   |-- layout/
|   |   `-- shared/
|   |-- pages/             top-level routed pages
|   |-- contexts/          current-user and settings state
|   |-- hooks/             reusable React workflows
|   |-- lib/               API and page-access utilities
|   |-- types/             TypeScript contracts and adapters
|   |-- utils/             date formatting and export helpers
|   |-- data/              legacy/static reference data
|   |-- test/              Vitest tests and test setup
|   |-- App.tsx            application route map
|   |-- main.tsx           React entry point
|   `-- index.css          global styles and Tailwind setup
|-- package.json           scripts and dependencies
|-- vite.config.ts         dev server and /api proxy
`-- vitest.config.ts       frontend test configuration
```

Pages belong in `src/pages/`. Page-specific components belong in the matching
`src/components/<feature>/` folder. New API-backed pages should also update
`src/lib/pageAccess.ts` when they require a permission.

## Main stack

- React 19 and TypeScript
- Vite
- Tailwind CSS
- React Router
- Recharts
- Lucide React
- Vitest and Testing Library

## Further documentation

See [Frontend Modules and Routes](../spec%20files/Frontend_Modules_and_Routes.md)
for the current page map and
[Display Requirements](../spec%20files/Display_Requirements.md) for Dashboard
and Network Health behavior.

Design reference:
[Figma — CAPSTONE PinPoint](https://www.figma.com/design/f8TYqcKORYTS6Rqhr39mPE/CAPSTONE---PinPoint)
