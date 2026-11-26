import type { AuthRefreshState } from "../../auth/useAuthRefresh";
import type { RefreshNotice } from "../../auth/refresh";

function AuthNotice({ notice }: { notice: RefreshNotice }) {
  switch (notice.kind) {
    case "outcome":
      return (
        <div className={`auth-refresh-result auth-${notice.tone}`} role="status">
          <strong>{notice.label}</strong> {notice.guidance}
        </div>
      );
    case "session-expired":
      return (
        <div className="auth-refresh-result auth-warn" role="status">
          <strong>Session expired.</strong> Your portal session has ended, so nothing was refreshed.{" "}
          <a href="/dashboard/login">Sign in again</a>, then retry.
        </div>
      );
    case "did-not-complete":
      return (
        <div className="auth-refresh-result auth-error" role="status">
          <strong>Refresh did not complete.</strong> {notice.reason}
        </div>
      );
    case "timed-out":
      // Not a fixed outcome: no answer came, so the crew may still have been refreshed.
      return (
        <div className="auth-refresh-result auth-warn" role="status">
          Refresh did not complete: no answer after {notice.seconds} seconds. It may still finish;
          check the crew and retry.
        </div>
      );
    case "unknown":
      return (
        <div className="auth-refresh-result auth-error" role="status">
          <strong>Refresh result unknown.</strong> The response was not recognised. Retry.
        </div>
      );
  }
}

/** The Credentials section: the Refresh auth button and the outcome of the last refresh. */
export function CredentialsSection({ crewId, auth }: { crewId: string; auth: AuthRefreshState }) {
  return (
    <>
      <h2 className="detail-section">Credentials</h2>
      <div className="auth-refresh">
        <button
          type="button"
          className="auth-refresh-btn"
          data-auth-refresh={crewId}
          title="Re-apply this crew's assigned credential if it can be refreshed in place"
          disabled={auth.busy}
          aria-busy={auth.busy || undefined}
          onClick={() => auth.refresh()}
        >
          {auth.busy ? "Refreshing…" : "Refresh auth"}
        </button>
        {auth.busy && auth.slow ? (
          <p className="auth-refresh-note" role="status">
            Still working… a refresh can take up to a minute.
          </p>
        ) : null}
        {auth.notice ? <AuthNotice notice={auth.notice} /> : null}
      </div>
    </>
  );
}
