import { Check, Crown, Radio } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { time, cx, Avatar } from "./ui";

export function Post({ event: e }) {
  if (e.kind === "routing")
    return (
      <div className="routing-post">
        <Radio size={14} />
        <div>
          {e.content}
          <details>
            <summary>Why this speaker?</summary>
            <p>{e.metadata.selection}</p>
            {e.metadata.knowledge?.evidence?.map((item, i) => (
              <blockquote key={i}>
                <code>{item.path}</code>
                <pre>{item.quote}</pre>
              </blockquote>
            ))}
          </details>
        </div>
      </div>
    );
  if (e.kind === "system")
    return (
      <div className="system-post">
        <Check size={13} />
        {e.content}
        <time>{time(e.created_at)}</time>
      </div>
    );
  const m = e.metadata;
  return (
    <article
      className={cx(
        "post",
        e.kind === "user" && "user-post",
        e.kind === "synthesis" && "synthesis",
        e.kind === "error" && "error-post",
      )}
    >
      <Avatar
        name={e.author}
        provider={m.provider || (e.kind === "user" ? "user" : "system")}
      />
      <div className="post-body">
        <div className="post-heading">
          <strong>{e.author}</strong>
          {e.kind === "synthesis" ? (
            <span className="synthesis-label">
              <Crown size={11} />
              Chief synthesis
            </span>
          ) : e.kind === "user" ? (
            <span className="post-role">
              {m.mode === "broadcast" || m.mode === "opinions"
                ? `${m.mode === "broadcast" ? "KNOWLEDGE BROADCAST" : "INDEPENDENT OPINIONS"} · ${m.targets?.length || 0} MODELS`
                : m.targets?.length
                  ? "DIRECT MESSAGE"
                  : "IDEA"}
            </span>
          ) : (
            <span className="post-role">
              {m.simulated ? "SIMULATED · " : ""}
              {m.phase
                ? {
                    lead: "FIRST ANSWER",
                    review: "NEW CONTRIBUTION",
                    update: "ANSWER UPDATE",
                  }[m.phase] || m.phase.toUpperCase()
                : e.kind === "reply"
                  ? ""
                  : m.round
                    ? "ROUND " + m.round
                    : e.kind.toUpperCase()}
            </span>
          )}
          <time>{time(e.created_at)}</time>
        </div>
        <div className="markdown">
          <ReactMarkdown
            components={{
              img: ({ alt }) => <span>[Image: {alt}]</span>,
              a: ({ href, children }) => (
                <a href={href} target="_blank" rel="noreferrer">
                  {children}
                </a>
              ),
            }}
          >
            {e.content}
          </ReactMarkdown>
        </div>
        {m.images?.length > 0 && (
          <div className="post-images">
            {m.images.map((im) => (
              <img
                src={"/api/attachments/" + im.id}
                alt={im.name}
                key={im.id}
              />
            ))}
          </div>
        )}
        {m.model && (
          <div className="post-meta">
            <span>{m.model}</span>
            <span>{(m.elapsed_ms / 1000).toFixed(1)}s</span>
            {m.truncated && <strong>Output limit reached</strong>}
            <details>
              <summary>Usage</summary>
              <pre>{JSON.stringify(m.usage, null, 2)}</pre>
            </details>
          </div>
        )}
      </div>
    </article>
  );
}
