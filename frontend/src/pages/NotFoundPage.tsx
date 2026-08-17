import { Link, useLocation } from "react-router-dom";
import { PageHeader, Panel } from "../components/ui";

/**
 * Rendered for any path the router does not know. It lives inside `Layout`, so
 * the nav bar stays available and a stale bookmark is one click from a real page
 * instead of a blank screen.
 */
export function NotFoundPage() {
  const { pathname } = useLocation();

  return (
    <div className="page-enter space-y-8">
      <PageHeader
        title="Page not found"
        subtitle="This address doesn't match any page in the lab UI. Nothing crashed — the app is running normally."
      />

      <Panel className="space-y-3">
        <p className="text-sm text-ink/70">
          Requested path: <code className="font-mono text-ink">{pathname}</code>
        </p>
        <p className="text-sm text-ink/70">
          The usual cause is an old bookmark or a typo in the address bar. Every page is
          reachable from the navigation above — for example, authorization policies live under{" "}
          <Link className="underline" to="/policies">
            Authorization
          </Link>
          .
        </p>
        <div className="flex flex-wrap gap-3">
          <Link className="ui-btn-signal" to="/">
            Back to Dashboard
          </Link>
          <Link className="ui-btn-ghost" to="/wizard">
            Open the Wizard
          </Link>
        </div>
      </Panel>
    </div>
  );
}
