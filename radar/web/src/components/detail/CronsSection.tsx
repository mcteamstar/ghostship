import type { Crew, CronsPayload } from "../../api/types";
import type { Section } from "../../detail/useCrewDetail";
import { FailedSection } from "./states";

/**
 * The crew's scheduled jobs, without the Captain schedule (the Captain block shows that).
 * Stopped crews have no such request, so they show no section.
 */
export function CronsSection({ crew, detail }: { crew: Crew; detail: Section<CronsPayload> }) {
  if (crew.status !== "running") return null;
  return (
    <>
      <h2 className="detail-section">Scheduled jobs</h2>
      {detail.state === "ok" ? (
        <CronList jobs={detail.data.jobs.filter((job) => job.type !== "captain")} />
      ) : detail.state === "failed" ? (
        <FailedSection error={detail.error} unavailable="Scheduled jobs unavailable." />
      ) : (
        <p className="state">Loading scheduled jobs…</p>
      )}
    </>
  );
}

function CronList({ jobs }: { jobs: CronsPayload["jobs"] }) {
  if (jobs.length === 0) return <p className="state">No scheduled jobs.</p>;
  return (
    <table className="detail-table">
      <thead>
        <tr>
          <th scope="col">Name</th>
          <th scope="col">Agent</th>
          <th scope="col">Schedule</th>
        </tr>
      </thead>
      <tbody>
        {jobs.map((job, index) => (
          <tr key={`${job.name ?? "job"}-${index}`}>
            <td>{job.name || "—"}</td>
            <td>{job.agent || "—"}</td>
            <td>{job.schedule || job.cron_expr || "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
