"use client";

import { useMemo, useState } from "react";
import {
  ArrowDownRight, ArrowRight, AudioLines, BookOpen, Check, ChevronDown,
  CircleHelp, Clapperboard, Clock3, Film, Layers3, LoaderCircle, MessageSquare,
  Play, Plus, RefreshCw, Settings2, Sparkles, WandSparkles, X,
} from "lucide-react";

type Character = {
  id: string; name: string; age_range: string; appearance: string;
  personality: string; relationships: string[];
};
type Scene = {
  scene_number: number; location: string; time_of_day: string;
  duration_seconds: number; characters_present: string[]; action: string;
  dialogue: string[]; emotional_beat: string; visual_direction: string; transition: string;
};
type Screenplay = {
  title: string; logline: string; genre: string; language: string;
  visual_style: string; characters: Character[]; scenes: Scene[];
  cliffhanger: string; continuity_notes: string[];
};
type StoryResponse = { status: "completed"; screenplay: Screenplay };
type VideoJob = { job_id: string; status: "queued" | "starting" | "processing" | "succeeded" | "failed" | "canceled" | "unknown"; video_url: string | null; error: string | null };

const inspiration = "When Mira returns to her coastal hometown for her sister's engagement, she discovers that the quiet photographer hired for the ceremony is the boy who disappeared from her life seven years ago. They agree to act like strangers, but an old letter hidden inside the family house threatens to reveal why he left.";
const genres = ["Romance", "Mystery", "Drama", "Fantasy", "Thriller", "Slice of life"];
const styles = [
  { label: "Cinematic realism", detail: "Natural light · Film texture", tone: "realism" },
  { label: "K-drama aesthetic", detail: "Expressive close-ups · Soft glow", tone: "kdrama" },
  { label: "Dreamlike", detail: "Atmospheric · Surreal", tone: "dream" },
  { label: "Neo-noir", detail: "Deep shadows · Moody color", tone: "noir" },
];

export default function CreatorStudio() {
  const [title, setTitle] = useState("The Letter We Never Sent");
  const [story, setStory] = useState("");
  const [genre, setGenre] = useState("Romance");
  const [style, setStyle] = useState("Cinematic realism");
  const [language, setLanguage] = useState("English");
  const [duration, setDuration] = useState("45");
  const [screenplay, setScreenplay] = useState<Screenplay | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [activeTab, setActiveTab] = useState<"script" | "cast">("script");
  const [showSettings, setShowSettings] = useState(false);
  const [sceneInstructions, setSceneInstructions] = useState<Record<number, string>>({});
  const [regeneratingScene, setRegeneratingScene] = useState<number | null>(null);
  const [videoJobs, setVideoJobs] = useState<Record<number, VideoJob>>({});
  const [generatingVideo, setGeneratingVideo] = useState<number | null>(null);
  const [checkingVideo, setCheckingVideo] = useState<number | null>(null);

  const wordCount = useMemo(() => story.trim() ? story.trim().split(/\s+/).length : 0, [story]);

  async function createScreenplay() {
    setError("");
    setScreenplay(null);
    if (story.trim().length < 30) {
      setError("Add at least 30 characters so the story planner has enough to work with.");
      return;
    }
    setBusy(true);
    try {
      const response = await fetch("/api/stories/plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: title.trim() || "Untitled story",
          story: story.trim(),
          genre: genre.toLowerCase(),
          visual_style: style.toLowerCase(),
          language,
          episode_duration_seconds: Number(duration),
        }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        const detail = typeof payload.detail === "string" ? payload.detail : "The story planner could not complete this request.";
        throw new Error(response.status === 503
          ? "The API is reachable, but the LLM provider is not configured yet. Set the server-side LLM credentials and try again."
          : detail);
      }
      setScreenplay((payload as StoryResponse).screenplay);
      setActiveTab("script");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  async function regenerateScene(sceneNumber: number) {
    if (!screenplay) return;
    setError("");
    setRegeneratingScene(sceneNumber);
    try {
      const response = await fetch("/api/stories/regenerate-scene", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          screenplay,
          scene_number: sceneNumber,
          instruction: sceneInstructions[sceneNumber]?.trim() || "Improve emotional impact and cinematic visual direction while preserving continuity.",
        }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(typeof payload.detail === "string" ? payload.detail : "Scene regeneration failed.");
      }
      const result = payload as { scene: Scene; continuity_notes: string[] };
      setScreenplay({
        ...screenplay,
        scenes: screenplay.scenes.map(scene => scene.scene_number === sceneNumber ? result.scene : scene),
        continuity_notes: Array.from(new Set([...screenplay.continuity_notes, ...result.continuity_notes])),
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scene regeneration failed.");
    } finally {
      setRegeneratingScene(null);
    }
  }

  function updateSceneAction(sceneNumber: number, action: string) {
    if (!screenplay) return;
    setScreenplay({
      ...screenplay,
      scenes: screenplay.scenes.map(scene => scene.scene_number === sceneNumber ? { ...scene, action } : scene),
    });
  }


  async function generateVideo(sceneNumber: number) {
    if (!screenplay) return;
    setError("");
    setGeneratingVideo(sceneNumber);
    try {
      const response = await fetch("/api/videos/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ screenplay, scene_number: sceneNumber }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(typeof payload.detail === "string" ? payload.detail : "Could not start video generation.");
      }
      setVideoJobs(current => ({ ...current, [sceneNumber]: payload as VideoJob }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start video generation.");
    } finally {
      setGeneratingVideo(null);
    }
  }

  async function refreshVideo(sceneNumber: number) {
    const job = videoJobs[sceneNumber];
    if (!job) return;
    setError("");
    setCheckingVideo(sceneNumber);
    try {
      const response = await fetch(`/api/videos/jobs/${encodeURIComponent(job.job_id)}`);
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(typeof payload.detail === "string" ? payload.detail : "Could not check video status.");
      }
      setVideoJobs(current => ({ ...current, [sceneNumber]: payload as VideoJob }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not check video status.");
    } finally {
      setCheckingVideo(null);
    }
  }

  return (
    <main className="studio-shell">
      <aside className="sidebar">
        <a className="brand" href="#" aria-label="Story-to-Vision home">
          <span className="brand-mark"><Clapperboard size={21} strokeWidth={1.8} /></span>
          <span className="brand-copy"><strong>story<span>to</span>vision</strong><small>CREATOR STUDIO</small></span>
        </a>
        <div className="workspace-label">WORKSPACE <ChevronDown size={13} /></div>
        <button className="workspace-switch"><span className="workspace-avatar">S</span><span><strong>Seeta’s Studio</strong><small>Personal workspace</small></span><ChevronDown size={15} /></button>
        <div className="nav-label">CREATE</div>
        <button className="nav-item active"><WandSparkles size={17} /> Story studio <span className="nav-dot" /></button>
        <button className="nav-item" onClick={() => setError("Episode library is coming in a future milestone.")}><Film size={17} /> My episodes</button>
        <button className="nav-item" onClick={() => setError("Character universe is coming in a future milestone.")}><Layers3 size={17} /> Character universe</button>
        <div className="sidebar-bottom">
          <div className="help-card"><span className="help-icon"><CircleHelp size={17} /></span><strong>Your story, your vision.</strong><p>Start with a feeling. Build a world around it.</p><button onClick={() => { setStory(inspiration); setError(""); }}>Try an example <ArrowRight size={14} /></button></div>
          <button className="nav-item" onClick={() => setShowSettings(v => !v)}><Settings2 size={17} /> Studio settings</button>
          {showSettings && <div className="settings-note">API connection: same-origin proxy to FastAPI. Provider keys stay on the server.</div>}
          <div className="profile-row"><div className="profile-avatar">SD</div><span><strong>Creator account</strong><small>Early access</small></span><span className="profile-menu">···</span></div>
        </div>
      </aside>

      <section className="main-panel">
        <header className="topbar">
          <div className="breadcrumbs"><span>Workspace</span><span className="crumb-slash">/</span><strong>Story studio</strong></div>
          <div className="top-actions"><span className="autosave"><span /> Draft workspace</span><button className="icon-button" aria-label="Help" onClick={() => setError("Tip: write the story in your own words. The planner will structure it into 4–6 scenes.")}><CircleHelp size={18} /></button><div className="top-avatar">S</div></div>
        </header>

        <div className="page-content">
          <div className="welcome-row"><div><div className="eyebrow"><Sparkles size={13} /> YOUR NEXT STORY STARTS HERE</div><h1>Make something <em>unforgettable.</em></h1><p className="page-subtitle">From a tiny spark to a story worth staying up for.</p></div><div className="edition-pill"><span /> STUDIO / 001</div></div>

          <div className="workbench">
            <section className="editor-column">
              <div className="section-heading"><div><span className="step-number">01</span><div><h2>The story</h2><p>Give your idea a heartbeat.</p></div></div><span className="required-label">REQUIRED</span></div>
              <label className="field-label" htmlFor="story-title">Story title</label>
              <input id="story-title" className="title-input" value={title} onChange={e => setTitle(e.target.value)} maxLength={120} placeholder="Give your story a name…" />
              <div className="story-label-row"><label className="field-label" htmlFor="story-text">Your story idea</label><span className="word-count">{wordCount} words</span></div>
              <div className="story-input-wrap"><textarea id="story-text" value={story} onChange={e => setStory(e.target.value)} maxLength={20000} placeholder={"A person. A secret. A moment that changes everything…\n\nWrite freely — a paragraph, a scene, or the whole plot. We’ll help shape it into an episode."} /><div className="textarea-footer"><span><BookOpen size={14} /> Your words are the starting point</span><span>{story.length.toLocaleString()} / 20,000</span></div></div>
              <div className="editor-tip"><Sparkles size={15} /><span><strong>A little detail goes a long way.</strong> Include what your character wants, what stands in their way, and what’s at stake.</span></div>

              <div className="section-heading options-heading"><div><span className="step-number">02</span><div><h2>Set the scene</h2><p>Choose the feeling, not every detail.</p></div></div></div>
              <label className="field-label">Genre</label>
              <div className="genre-grid">{genres.map((g, i) => <button key={g} className={genre === g ? "genre-chip selected" : "genre-chip"} onClick={() => setGenre(g)}><span className={`genre-glyph glyph-${i}`}>{["♡","⌕","✳","✧","◈","☼"][i]}</span>{g}{genre === g && <Check size={13} />}</button>)}</div>

              <label className="field-label style-label">Visual direction</label>
              <div className="style-grid">{styles.map((s, i) => <button key={s.label} className={style === s.label ? `style-card selected style-${i}` : `style-card style-${i}`} onClick={() => setStyle(s.label)}><span className="style-art"><span /><span /><span /></span><span className="style-card-text"><strong>{s.label}</strong><small>{s.detail}</small></span>{style === s.label && <span className="style-check"><Check size={12} /></span>}</button>)}</div>

              <button className="advanced-toggle" onClick={() => setShowSettings(v => !v)}><Settings2 size={15} /> More episode settings <ChevronDown className={showSettings ? "rotate" : ""} size={15} /></button>
              {showSettings && <div className="advanced-panel"><div><label className="field-label" htmlFor="duration">Episode duration</label><select id="duration" value={duration} onChange={e => setDuration(e.target.value)}><option value="30">30 seconds · teaser</option><option value="45">45 seconds · short episode</option><option value="60">60 seconds · standard</option><option value="90">90 seconds · extended</option></select></div><div><label className="field-label" htmlFor="language">Screenplay language</label><select id="language" value={language} onChange={e => setLanguage(e.target.value)}><option>English</option><option>Hindi</option><option>Kannada</option><option>Korean</option><option>Chinese</option></select></div></div>}

              {error && <div className="error-banner" role="alert"><X size={16} /><span>{error}</span><button onClick={() => setError("")} aria-label="Dismiss error"><X size={14} /></button></div>}
              <div className="generate-row"><div className="privacy-note"><span className="privacy-dot" /> Your draft stays yours.<small>Generation requires a configured API.</small></div><button className="generate-button" onClick={createScreenplay} disabled={busy}><span>{busy ? <LoaderCircle className="spin" size={17} /> : <WandSparkles size={17} />}</span>{busy ? "Finding the story…" : "Shape my screenplay"}{!busy && <ArrowRight size={17} />}</button></div>
            </section>

            <aside className="preview-column">
              <div className="preview-topline"><span><span className="preview-live-dot" /> LIVE PREVIEW</span><span className="preview-badge">SCREENPLAY</span></div>
              <div className="preview-cover">
                <div className="cover-grain" /><div className="cover-orbit orbit-one" /><div className="cover-orbit orbit-two" />
                <div className="cover-content"><span className="cover-kicker">AN ORIGINAL STORY</span><div className="cover-symbol"><AudioLines size={28} strokeWidth={1.2} /></div><h3>{screenplay?.title || title || "Your story title"}</h3><p>{screenplay?.logline || "Every unforgettable story begins with a secret."}</p><div className="cover-meta"><span>{genre.toUpperCase()}</span><i /> <span>{duration} SEC</span><i /> <span>EP. 01</span></div></div>
                <div className="cover-bottom"><span>STORY-TO-VISION ORIGINALS</span><span>NO. 001</span></div>
              </div>
              <div className="preview-stats"><div><span>FORMAT</span><strong>9:16 <small>vertical</small></strong></div><div><span>EST. LENGTH</span><strong>{duration}s <small>episode</small></strong></div><div><span>SCENES</span><strong>{screenplay ? screenplay.scenes.length.toString().padStart(2, "0") : "—"} <small>{screenplay ? "planned" : "pending"}</small></strong></div></div>
              <div className="preview-tabs"><button className={activeTab === "script" ? "active" : ""} onClick={() => setActiveTab("script")}><BookOpen size={15} /> Script {screenplay && <span>{screenplay.scenes.length}</span>}</button><button className={activeTab === "cast" ? "active" : ""} onClick={() => setActiveTab("cast")}><Layers3 size={15} /> Cast {screenplay && <span>{screenplay.characters.length}</span>}</button></div>
              <div className="preview-body">
                {!screenplay ? <div className="empty-preview"><div className="empty-icon"><Film size={23} /></div><strong>Your first scene is waiting.</strong><p>Once you shape your story, your screenplay and characters will appear here.</p><div className="empty-steps"><span><Check size={13} /> Story idea</span><ArrowRight size={13} /><span><Clock3 size={13} /> Scene breakdown</span></div></div> : activeTab === "script" ? <div className="scene-list">{screenplay.scenes.map(scene => <article className="scene-card" key={scene.scene_number}><div className="scene-card-top"><span>SCENE {String(scene.scene_number).padStart(2, "0")}</span><span><Clock3 size={12} /> {scene.duration_seconds}s</span></div><h4>{scene.location}</h4><label className="scene-edit-label" htmlFor={`scene-action-${scene.scene_number}`}>Scene action · editable</label><textarea id={`scene-action-${scene.scene_number}`} className="scene-action-editor" value={scene.action} onChange={e => updateSceneAction(scene.scene_number, e.target.value)} rows={3} /><div className="scene-dialogue-preview">{scene.dialogue.slice(0, 2).map((line, i) => <blockquote key={i}>{line}</blockquote>)}</div><label className="scene-edit-label" htmlFor={`scene-instruction-${scene.scene_number}`}>What should change?</label><div className="scene-refine-row"><input id={`scene-instruction-${scene.scene_number}`} value={sceneInstructions[scene.scene_number] || ""} onChange={e => setSceneInstructions(current => ({ ...current, [scene.scene_number]: e.target.value }))} placeholder="More tension, softer dialogue…" maxLength={500} /><button onClick={() => regenerateScene(scene.scene_number)} disabled={regeneratingScene !== null} aria-label={`Regenerate scene ${scene.scene_number}`}>{regeneratingScene === scene.scene_number ? <LoaderCircle className="spin" size={14} /> : <RefreshCw size={14} />} Refine</button></div><div className="scene-emotion"><span /> {scene.emotional_beat}</div><div className="video-generation-row"><button className="video-generate-button" onClick={() => generateVideo(scene.scene_number)} disabled={generatingVideo !== null || ["queued", "starting", "processing"].includes(videoJobs[scene.scene_number]?.status || "")}>{generatingVideo === scene.scene_number ? <LoaderCircle className="spin" size={14} /> : <Film size={14} />} {videoJobs[scene.scene_number] ? "Generate again" : "Generate video clip"}</button>{videoJobs[scene.scene_number] && <div className="video-job-status"><span className={`job-status-dot status-${videoJobs[scene.scene_number].status}`} />{videoJobs[scene.scene_number].status.replace("_", " ")}{["queued", "starting", "processing"].includes(videoJobs[scene.scene_number].status) && <button onClick={() => refreshVideo(scene.scene_number)} disabled={checkingVideo !== null}>{checkingVideo === scene.scene_number ? <LoaderCircle className="spin" size={12} /> : <RefreshCw size={12} />} Check status</button>}</div>}{videoJobs[scene.scene_number]?.error && <p className="video-job-error">{videoJobs[scene.scene_number].error}</p>}{videoJobs[scene.scene_number]?.video_url && <video className="generated-video" controls playsInline preload="metadata" src={videoJobs[scene.scene_number].video_url || undefined}>Your browser does not support video playback.</video>}</div></article>)}<div className="cliffhanger"><span>THE CLIFFHANGER</span><p>{screenplay.cliffhanger}</p></div>{screenplay.continuity_notes.length > 0 && <div className="continuity-note"><strong>Continuity notes</strong>{screenplay.continuity_notes.map((note, i) => <p key={i}>{note}</p>)}</div>}</div> : <div className="cast-list">{screenplay.characters.map(character => <article className="cast-card" key={character.id}><div className="cast-avatar">{character.name.slice(0, 1).toUpperCase()}</div><div><h4>{character.name}</h4><span>{character.age_range}</span><p>{character.appearance}</p><small>{character.personality}</small></div></article>)}</div>}
              </div>
              {screenplay && <button className="continue-button" onClick={() => setError("Choose Generate video clip on a scene to create a real provider-generated video.")}><Play size={15} /> Continue to episode creation <ArrowDownRight size={15} /></button>}
              <div className="preview-footnote"><MessageSquare size={13} /> AI-generated drafts are editable starting points.</div>
            </aside>
          </div>
          <footer className="page-footer"><span>Made for stories that stay with you.</span><span><span className="footer-dot" /> CREATOR STUDIO PREVIEW</span></footer>
        </div>
      </section>
    </main>
  );
}
