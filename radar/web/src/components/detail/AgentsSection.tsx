import { type ReactNode, useId } from "react";
import type { AgentTask, AgentsPayload, Crew } from "../../api/types";
import { PERSONA_AGENTS } from "../../api/types";
import { fmtUptime, shortId } from "../../format";
import type { Section } from "../../detail/useCrewDetail";
import { FailedSection } from "./states";

/** The persona an agent name stands for, or null for any other name (case-insensitive). */
export function personaOf(agent: string | null | undefined): string | null {
  const name = (agent ?? "").trim().toLowerCase();
  return (PERSONA_AGENTS as readonly string[]).includes(name) ? name : null;
}

/** Elapsed time. A finished task with no time is shown as an em dash, as it always was. */
function elapsedOf(task: AgentTask): string {
  if (task.done && !(task.elapsed_secs || task.elapsed)) return "—";
  return fmtUptime(task.elapsed_secs || task.elapsed);
}

function TaskCard({ task }: { task: AgentTask }) {
  const persona = personaOf(task.agent);
  const className = persona ? `agent-card persona-${persona}` : "agent-card agent-card-unknown";
  const id = task.task_id || task.id || null;
  return (
    <li className={className}>
      <div className="agent-card-agent">{task.agent?.trim() ? task.agent : "unknown agent"}</div>
      <div className="agent-card-meta">
        <span className="mono" title={id ?? undefined}>
          {shortId(id)}
        </span>
        <span className={task.done ? undefined : "agent-card-state-running"}>
          {task.done ? "done" : "running"}
        </span>
        <span>
          <span className="visually-hidden">Elapsed </span>
          {elapsedOf(task)}
        </span>
      </div>
    </li>
  );
}

/**
 * Running tasks as cards under a count, then finished tasks behind a disclosure with
 * their own count. The disclosure is a native details element, so it works from the
 * keyboard and the pointer. Its tasks stay in the DOM when it is closed.
 */
export function AgentGroups({ tasks }: { tasks: AgentTask[] }) {
  const runningTitle = useId();
  const running = tasks.filter((task) => !task.done);
  const finished = tasks.filter((task) => task.done);
  return (
    <>
      <section className="agent-group" aria-labelledby={runningTitle}>
        <p className="agent-group-title" id={runningTitle}>
          Running · {running.length}
        </p>
        {running.length === 0 ? (
          <p className="state">No active tasks.</p>
        ) : (
          <ul className="agent-cards">
            {running.map((task, index) => (
              <TaskCard key={`running-${task.task_id ?? task.id ?? "task"}-${index}`} task={task} />
            ))}
          </ul>
        )}
      </section>
      {finished.length > 0 ? (
        <details className="agent-finished">
          <summary>Finished · {finished.length}</summary>
          <ul className="agent-cards">
            {finished.map((task, index) => (
              <TaskCard key={`finished-${task.task_id ?? task.id ?? "task"}-${index}`} task={task} />
            ))}
          </ul>
        </details>
      ) : null}
    </>
  );
}

/**
 * The agent tasks of a crew. A running crew shows its live list once that request has
 * answered. A stopped crew shows the list the fleet reported for it.
 */
export function AgentsSection({ crew, detail, controls }: {
  crew: Crew;
  detail: Section<AgentsPayload>;
  controls?: ReactNode;
}) {
  const heading = <div className="task-section-heading">
    <h2 className="detail-section">Active tasks</h2>{controls}
  </div>;
  if (crew.status !== "running") {
    return (
      <>
        {heading}
        <AgentGroups tasks={crew.agents ?? []} />
      </>
    );
  }
  if (detail.state === "ok") {
    return (
      <>
        {heading}
        <AgentGroups tasks={detail.data.agents} />
      </>
    );
  }
  if (detail.state === "failed") {
    return (
      <>
        {heading}
        <FailedSection error={detail.error} unavailable="Active tasks unavailable." />
      </>
    );
  }
  return (
    <>
      {heading}
      <p className="state">Loading tasks…</p>
    </>
  );
}
