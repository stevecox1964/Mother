import { useEffect, useState } from "react";
import { ArrowRight, Database, Search } from "lucide-react";
import { time, date, Field } from "./ui";

export function Archive({ open, fail, api }) {
  const [q, setQ] = useState(""),
    [start, setStart] = useState(""),
    [end, setEnd] = useState(""),
    [results, setResults] = useState([]),
    [busy, setBusy] = useState(false),
    [mode, setMode] = useState("hybrid"),
    [indexStatus, setIndexStatus] = useState(null),
    [warning, setWarning] = useState("");
  useEffect(() => {
    let live = true;
    const refresh = () =>
      api("/search/status")
        .then((r) => {
          if (live) setIndexStatus(r);
        })
        .catch(() => {});
    refresh();
    const timer = setInterval(refresh, 3000);
    return () => {
      live = false;
      clearInterval(timer);
    };
  }, []);
  useEffect(() => {
    let live = true;
    setBusy(true);
    const id = setTimeout(() => {
      api("/search/hybrid?" + new URLSearchParams({ q, start, end, mode }))
        .then((r) => {
          if (live) {
            setResults(r.results);
            setWarning(r.warning);
            setIndexStatus(r.index);
          }
        })
        .catch((e) => {
          if (live) {
            setResults([]);
            setWarning(e.message);
          }
        })
        .finally(() => {
          if (live) setBusy(false);
        });
    }, 500);
    return () => {
      live = false;
      clearTimeout(id);
    };
  }, [q, start, end, mode, indexStatus?.indexed]);
  return (
    <div className="settings-page">
      <div className="page-heading">
        <div>
          <h1>Search conversations</h1>
          <p>Find a phrase, a topic, or an idea from a past conversation.</p>
        </div>
        <Database size={28} />
      </div>
      <div className="archive-body">
        <div className="archive-filters">
          <div className="search-input">
            <Search size={18} />
            <input
              autoFocus
              maxLength={1000}
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search every conversation…"
              aria-label="Search conversations"
            />
          </div>
          <Field label="From (UTC)">
            <input
              type="date"
              value={start}
              onChange={(e) => setStart(e.target.value)}
            />
          </Field>
          <Field label="To (UTC)">
            <input
              type="date"
              value={end}
              onChange={(e) => setEnd(e.target.value)}
            />
          </Field>
        </div>
        <div className="search-options">
          <div className="search-modes" aria-label="Search mode">
            <button
              aria-pressed={mode === "hybrid"}
              onClick={() => setMode("hybrid")}
            >
              Smart search
            </button>
            <button
              aria-pressed={mode === "keyword"}
              onClick={() => setMode("keyword")}
            >
              Exact text
            </button>
          </div>
          {indexStatus && (
            <div className="search-index-status" role="status">
              {indexStatus.pending
                ? `${indexStatus.indexed} of ${indexStatus.total} messages indexed`
                : "Local search ready"}
              {(indexStatus.failed > 0 ||
                indexStatus.error ||
                (indexStatus.pending > 0 && !indexStatus.busy)) && (
                <button
                  className="subtle-link"
                  onClick={async () => {
                    try {
                      setIndexStatus(await api("/search/index", "POST", {}));
                      setWarning("");
                    } catch (e) {
                      setWarning(e.message);
                    }
                  }}
                >
                  Retry indexing
                </button>
              )}
            </div>
          )}
        </div>
        {(warning || indexStatus?.error) && (
          <p className="search-warning" role="status">
            {warning || indexStatus.error}
          </p>
        )}
        <div className="archive-count" role="status">
          {busy
            ? "Searching…"
            : `${results.length} results · ${q.trim() && mode === "hybrid" ? "ranked by relevance" : "most recent first"}`}
        </div>
        {results.length ? (
          results.map((e) => (
            <button
              className="search-result"
              key={e.id}
              onClick={() => open(e.conversation_id)}
            >
              <div>
                <span>{e.title}</span>
                <small>
                  {date(e.created_at)} · {time(e.created_at)}
                </small>
              </div>
              <strong>
                {e.author}
                <span>{e.match_type || e.kind}</span>
              </strong>
              <p>
                {(e.snippet || e.content).slice(0, 450)}
                {(e.snippet || e.content).length > 450 ? "…" : ""}
              </p>
              <span className="result-link">
                Open conversation <ArrowRight size={13} />
              </span>
            </button>
          ))
        ) : (
          <div className="archive-empty">
            <Database size={30} />
            <h3>No matching conversations yet.</h3>
            <p>Try another phrase or clear the date filters.</p>
          </div>
        )}
      </div>
    </div>
  );
}
