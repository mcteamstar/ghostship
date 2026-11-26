import type { AuthRefreshState } from "../auth/useAuthRefresh";
import type { CrewDetailState } from "../detail/useCrewDetail";
import type { Crew } from "../api/types";
import { AgentsSection } from "./detail/AgentsSection";
import { CaptainSection } from "./detail/CaptainSection";
import { CredentialsSection } from "./detail/CredentialsSection";
import { MailboxSection } from "./detail/MailboxSection";

/** The expanded panel of one crew: its tasks, Captain, credentials and mailboxes. */
export function CrewDetail({
  crew,
  detail,
  auth,
}: {
  crew: Crew;
  detail: CrewDetailState;
  auth: AuthRefreshState;
}) {
  const running = crew.status === "running";
  return (
    <>
      {crew.crew_image_version ? (
        <div className="detail-image-version">
          Image: <span className="mono">{crew.crew_image_version}</span>
        </div>
      ) : null}
      <AgentsSection crew={crew} detail={detail.agents} />
      {crew.captain ? <CaptainSection captain={crew.captain} /> : null}
      {running ? null : <p className="stopped-note">Crew is stopped — live schedule data unavailable.</p>}
      <CredentialsSection crewId={crew.crew_id} auth={auth} />
      <MailboxSection detail={detail.mail} />
    </>
  );
}
