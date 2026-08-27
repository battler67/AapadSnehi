import { ExternalLink, Fingerprint, LoaderCircle, Radio, Search } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Notice, PageHeader } from "../components/ui";
import { demoBlueskyAuthors } from "../data/demo";
import { api } from "../lib/api";
import { timeAgo, titleCase } from "../lib/format";
import type { BlueskyScanResult } from "../types";

export function BlueskyHelpersPage() {
  const [query, setQuery] = useState("floods in india");
  const [result, setResult] = useState<BlueskyScanResult | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");

  const runScan = async (event: FormEvent) => {
    event.preventDefault();
    if (!query.trim()) return;
    setRunning(true);
    setError("");
    try {
      setResult(await api.scanBlueskyAuthors(query.trim()));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Bluesky scan failed");
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="content page-space bluesky-helpers-page">
      <PageHeader
        eyebrow="Bluesky adapter"
        title="Find public disaster helpers"
        description="Run the server-side Bluesky search and list public authors whose posts explicitly offer disaster help. Ready for the quick demo."
        actions={<span className="demo-admin-badge"><Radio size={15} />Read-only search</span>}
      />

      <Notice tone="warning">
        This uses transparent help-offer keywords, not Hugging Face, Transformers, or sentiment AI. A match is only a lead from a public post—not proof that the person is verified, available, or consenting to contact.
      </Notice>
      {error && <Notice tone="danger">{error}</Notice>}

      <section className="glass-panel bluesky-scan-panel">
        <form className="bluesky-scan-form" onSubmit={(event) => void runScan(event)}>
          <label className="field">
            <span>Bluesky search query</span>
            <input
              value={query}
              maxLength={100}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="floods in india"
            />
          </label>
          <button className="button primary" type="submit" disabled={running || !query.trim()}>
            {running ? <LoaderCircle className="spin" size={16} /> : <Search size={16} />}
            {running ? "Scanning…" : "Run Bluesky scan"}
          </button>
        </form>

        {result && (
          <div className="bluesky-results">
            <div className="panel-title">
              <div><p className="eyebrow"><span />Latest scan</p><h2>Useful-intent authors</h2></div>
              <span>{result.matchCount} matches from {result.scannedCount} posts</span>
            </div>
            {result.authors.length ? (
              <div className="bluesky-author-list">
                {result.authors.map((author) => (
                  <article className="bluesky-author-card" key={author.id}>
                    <div className="bluesky-author-head">
                      <span className="helper-avatar"><Fingerprint size={18} /></span>
                      <div>
                        <strong>{author.displayName || `@${author.handle}`}</strong>
                        <small>@{author.handle} · {timeAgo(author.postedAt)}</small>
                      </div>
                    </div>
                    <div className="bluesky-did"><span>Author ID</span><code>{author.id}</code></div>
                    <blockquote>{author.postText}</blockquote>
                    <div className="need-row">
                      <span>{titleCase(author.disasterType)}</span>
                      {author.capabilities.map((item) => <span key={item}>{titleCase(item)}</span>)}
                    </div>
                    <small>Matched: {author.matchedTerms.join(", ")}</small>
                    {author.postUrl && <a className="button secondary helper-source-link" href={author.postUrl} target="_blank" rel="noreferrer noopener"><ExternalLink size={14} />Open public post</a>}
                  </article>
                ))}
              </div>
            ) : (
              <div className="empty-inline"><Radio size={20} />No explicit offers of disaster help were found in this bounded search.</div>
            )}
          </div>
        )}

        <div className="bluesky-results">
          <div className="panel-title">
            <div><p className="eyebrow"><span />Demo results</p><h2>Example flood helper IDs</h2></div>
            <span>{demoBlueskyAuthors.length} sample profiles</span>
          </div>
          <div className="bluesky-author-list">
            {demoBlueskyAuthors.map((author) => (
              <article className="bluesky-author-card" key={author.id}>
                <div className="bluesky-author-head">
                  <span className="helper-avatar"><Fingerprint size={18} /></span>
                  <div>
                    <strong>{author.displayName}</strong>
                    <small>@{author.handle} · {timeAgo(author.postedAt)}</small>
                  </div>
                </div>
                <div className="bluesky-did"><span>Author ID</span><code>{author.id}</code></div>
                <blockquote>{author.postText}</blockquote>
                <div className="need-row">
                  <span>{titleCase(author.disasterType)}</span>
                  {author.capabilities.map((item) => <span key={item}>{titleCase(item)}</span>)}
                </div>
                <small>Matched: {author.matchedTerms.join(", ")}</small>
              </article>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}
