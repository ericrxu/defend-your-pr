'use client';

import { useEffect, useState } from 'react';
import { ArrowRight, BookOpen, Check, ChevronRight, Code2, FileCode2, GitBranch, Github, GraduationCap, Layers3, LoaderCircle, MessageSquare, RotateCcw, ShieldAlert, Sparkles, Terminal, X } from 'lucide-react';
import type { Evidence, Review, Report, History, Question } from './types';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
type View = 'analysis' | 'testing' | 'teaching' | 'report';
async function api<T>(path: string, body?: unknown): Promise<T> {
 const response = await fetch(API + path, body === undefined ? {} : {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)}).catch(() => {throw new Error(`Cannot reach the OwnIt API at ${API}. Start the FastAPI backend and check your API URL.`);});
 const data = await response.json().catch(() => null);
 if (!response.ok) throw new Error(typeof data?.detail === 'string' ? data.detail : response.status === 422 ? 'Invalid input. Check the repository URL and required fields.' : `The backend returned an error (${response.status}). Check its terminal and retry.`);
 if (data === null) throw new Error('The backend returned an unexpected response. Check the API URL.');
 return data;
}

function References({items, review, expanded=false}: {items: Evidence[]; review: Review; expanded?: boolean}) {
 return <div className="references">{items.map((e, i) => <details open={expanded} key={`${e.path}-${i}`}><summary><FileCode2 size={13}/>{e.path}:{e.start}–{e.end}</summary><pre>{(review.files[e.path] || '').split('\n').slice(e.start - 1, e.end).map((line, j) => `${String(e.start + j).padStart(3)}  ${line}`).join('\n')}</pre></details>)}</div>;
}

export default function Home() {
 const [review, setReview] = useState<Review | null>(null);
 const [view, setView] = useState<View>('analysis');
 const [url, setUrl] = useState('');
 const [commit, setCommit] = useState('');
 const [history, setHistory] = useState<History[]>([]);
 const [busy, setBusy] = useState('');
 const [error, setError] = useState('');
 const [answer, setAnswer] = useState('');
 const [message, setMessage] = useState('');
 const [concept, setConcept] = useState('');
 const [questionId, setQuestionId] = useState<string | null>(null);
 const [report, setReport] = useState<Report | null>(null);
 const [selectedFile, setSelectedFile] = useState('');
 const [focusId, setFocusId] = useState<string | null>(null);

 useEffect(() => { api<History[]>('/reviews').then(setHistory).catch(() => {}); }, []);
 async function run(label: string, action: () => Promise<void>) {
  setBusy(label); setError('');
  try { await action(); } catch (e) { setError(e instanceof Error ? e.message : 'Something went wrong. Please retry.'); } finally { setBusy(''); }
 }
 function load(r: Review) { setReview(r); setConcept(r.analysis.learning_objectives[0]?.name || ''); setSelectedFile(Object.keys(r.files)[0] || ''); setQuestionId(null); setFocusId(null); setAnswer(''); setMessage(''); setReport(null); setView('analysis'); }
 async function create(demo = false, demo_version = 'initial') {
  await run(demo ? 'Preparing demo analysis…' : 'Fetching public code and analyzing architecture…', async () => {
   const r = await api<Review>('/reviews', {url, demo, demo_version, ...(commit ? {commit} : {})}); load(r); setHistory(await api<History[]>('/reviews'));
  });
 }
 async function startTesting() {
  if (!review) return;
  await run('Preparing code-specific questions…', async () => {setReview(await api<Review>(`/reviews/${review.id}/questions`, {})); setFocusId(null); setView('testing');});
 }
 async function showReport() {
  if (!review) return;
  await run('Loading your learning outcomes…', async () => {setReport(await api<Report>(`/reviews/${review.id}/report`)); setView('report');});
 }
 const answered = new Set(review?.answers.map(a => a.question_id));
 const current = review?.questions.find(q => q.id === focusId) || review?.questions.find(q => !answered.has(q.id)) || review?.questions[review.questions.length - 1];
 const evaluation = current && review?.answers.filter(a => a.question_id === current.id).at(-1);
 const allAnswered = !!review?.questions.length && review.questions.every(q => answered.has(q.id));
 function learn(q?: Question) { if (q) {setConcept(q.concept); setQuestionId(q.id);} else setQuestionId(null); setView('teaching'); }
 async function retest() {
  if (!review || !questionId) {setView('testing'); return;}
  await run('Creating a fresh scenario for this concept…', async () => {
   const r = await api<Review>(`/reviews/${review.id}/retest`, {question_id: questionId});
   let root = r.questions.find(q => q.id === questionId);
   while (root?.parent_id) root = r.questions.find(q => q.id === root?.parent_id);
   setReview(r); setFocusId(r.questions.find(q => q.kind === 'retest' && q.parent_id === root?.id)?.id || null); setAnswer(''); setView('testing');
  });
 }

 return <div className="app-shell">
  <aside className="sidebar">
   <button className="brand" onClick={() => {setReview(null); setError('');}}><span className="brand-mark"><Code2 size={24}/></span>ownit<span className="beta">BETA</span></button>
   <div className="workspace"><span className="avatar">D</span><div>Developer workspace<small>Personal · Demo user</small></div><ChevronRight size={15}/></div>
   <div className="side-label">WORKSPACE</div>
   <button className={!review ? 'side-item active' : 'side-item'} onClick={() => {setReview(null);setError('');}}><Layers3 size={17}/>Repositories<span className="count">{history.length}</span></button>
   {review && <nav aria-label="Review navigation">{([['analysis', Layers3, 'Code analysis'], ['testing', Check, 'Testing mode'], ['teaching', GraduationCap, 'Teaching mode'], ['report', FileCode2, 'Understanding report']] as const).map(([key, Icon, label]) => <button key={key} disabled={!!busy} className={`side-item ${view === key ? 'active' : ''}`} onClick={() => key === 'report' ? void showReport() : key === 'testing' ? void startTesting() : (setView(key), key === 'teaching' && setQuestionId(null))}><Icon size={17}/>{label}</button>)}</nav>}
   <div className="side-label history-label">RECENT REVIEWS</div>
   <div className="history">{history.slice(0, 7).map(h => <button key={h.id} disabled={!!busy} onClick={() => void run('Opening saved review…', async () => load(await api<Review>(`/reviews/${h.id}`)))}><GitBranch size={14}/><span>{h.repo.split('/').at(-1)}<small>{h.sha.slice(0, 8)} · {h.status}</small></span></button>)}{!history.length && <p>Your reviews will appear here.</p>}</div>
   <div className="sidebar-bottom"><div className="online-dot"/>Local workspace<span>v0.1</span></div>
  </aside>
  <main>
   <header className="topbar"><div><span>Workspace</span><ChevronRight size={14}/><strong>{review ? review.repo.split('/').at(-1) : 'Repositories'}</strong></div><span className="private-label"><ShieldAlert size={14}/>Public repositories only</span></header>
   {error && <div className="error" role="alert">{error}<button aria-label="Dismiss error" onClick={() => setError('')}><X size={16}/></button></div>}
   {busy && <div className="loading" role="status"><LoaderCircle className="spin" size={17}/>{busy}<small>Progress is saved between steps.</small></div>}
   {!review ? <div className="landing content">
    <div className="eyebrow"><span/>YOUR CODE. YOUR UNDERSTANDING.</div>
    <h1>AI understands your code.<br/><span>But do you?</span></h1>
    <p className="hero-copy">Go beyond shipping code. Understand how it works, why it matters,<br className="desktop"/> and what happens when it changes.</p>
    <section className="connect-card"><div className="card-heading"><span className="icon-box"><Github size={23}/></span><div><h2>Start with your repository</h2><p>Get a code-specific review built around what matters.</p></div><span className="pill">PUBLIC REPOS</span></div>
     <form onSubmit={e => {e.preventDefault(); void create();}}><label htmlFor="repo-url">GitHub repository or pull request URL</label><div className="url-input"><Github size={18}/><input id="repo-url" type="url" placeholder="https://github.com/you/your-repository" required value={url} onChange={e => setUrl(e.target.value)}/></div><details className="advanced"><summary>Review a specific commit</summary><input aria-label="Commit SHA" placeholder="Optional commit SHA (7–40 hex characters)" value={commit} onChange={e => setCommit(e.target.value)}/><small>Completed reviews become the baseline for future comparisons. PRs use their base and head.</small></details><button className="primary" disabled={!!busy}>Analyze repository<ArrowRight size={17}/></button></form>
     <div className="connect-foot"><ShieldAlert size={13}/>Code is read, never executed. Tokens stay on your server.</div>
    </section>
    <div className="or"><span/>OR EXPLORE FIRST<span/></div>
    <section className="demo-card"><span className="demo-icon"><Terminal size={23}/></span><div><div className="inline"><h3>Take OwnIt for a spin</h3><span className="pill amber">OFFLINE DEMO</span></div><p>A Python app. An authorization bug. A faster algorithm.<br/>Explore a prerecorded review — no API key needed.</p></div><button className="secondary" disabled={!!busy} onClick={() => void create(true)}>Open demo<ArrowRight size={16}/></button></section>
    <div className="workflow"><div><span>01</span><h3>Analyze the architecture</h3><p>See the connections behind the code.</p></div><ChevronRight/><div><span>02</span><h3>Put understanding to the test</h3><p>Reason through real code decisions.</p></div><ChevronRight/><div><span>03</span><h3>Learn it. Then own it.</h3><p>Close the gaps with a personal tutor.</p></div></div>
    <footer><Sparkles size={14}/>Three focused agents. One shared understanding of your code.</footer>
   </div> : <div className="content review-content">
    <div className="review-heading"><div><div className="eyebrow">{review.analysis.review_type.toUpperCase()} REVIEW <span className="text-dot">/</span> {review.sha.slice(0, 10)}</div><h1 className="review-title">{view === 'analysis' ? 'Understand the whole picture.' : view === 'testing' ? 'Make the reasoning yours.' : view === 'teaching' ? 'A little clarity goes a long way.' : 'Your understanding, with evidence.'}</h1><p>{review.repo} <span className="text-dot">·</span> {review.status}{review.base_sha && ` · compared with ${review.base_sha.slice(0,10)}`}</p></div><span className={`pill ${review.demo ? 'amber' : ''}`}>{review.demo ? 'PRERECORDED DEMO' : 'LIVE AI REVIEW'}</span></div>
    {review.demo && <div className="demo-banner"><Terminal size={15}/>Demo Mode uses fixture analysis, scripted teaching, and keyword-based grading.<button disabled={!!busy} onClick={() => void create(true, 'modified')}>Analyze modified version<ArrowRight size={14}/></button></div>}
    <div className="tabs">{(['analysis', 'testing', 'teaching', 'report'] as View[]).map(v => <button key={v} className={view === v ? 'selected' : ''} disabled={!!busy} onClick={() => v === 'testing' ? void startTesting() : v === 'report' ? void showReport() : (setView(v), v === 'teaching' && setQuestionId(null))}>{v === 'analysis' ? 'Overview' : v === 'testing' ? 'Testing' : v === 'teaching' ? 'Teaching' : 'Report'}</button>)}</div>
    {view === 'analysis' && <>
     <section className="panel summary-panel"><div className="section-title"><Layers3 size={18}/><h2>Architecture at a glance</h2></div><p>{review.analysis.summary}</p><div className="flow">{review.analysis.data_flow.map((s,i) => <div key={i}><span>{String(i+1).padStart(2,'0')}</span>{s}{i < review.analysis.data_flow.length-1 && <ArrowRight size={16}/>}</div>)}</div></section>
     <div className="two-col"><div><h2 className="section-label">Components & algorithms</h2>{[...review.analysis.components, ...review.analysis.algorithms].map((c,i) => <section className="panel concept-card" key={i}><div className="section-title"><Code2 size={17}/><h3>{c.name}</h3></div><p>{c.explanation}</p><References items={c.evidence} review={review}/><button className="text-button" onClick={() => {setConcept(c.name);setQuestionId(null);setView('teaching');}}>Explore with tutor<ArrowRight size={13}/></button></section>)}</div><div><h2 className="section-label">What deserves attention</h2>{review.analysis.risks.map((risk,i) => <section key={i} className="panel risk"><span className={`pill ${risk.level === 'high' ? 'red' : 'amber'}`}>{risk.level} risk · {risk.confirmed ? 'confirmed' : 'potential'}</span><p>{risk.description}</p><References items={risk.evidence} review={review}/></section>)}<section className="panel"><h3>APIs & dependencies</h3>{review.analysis.apis_and_dependencies.map((d,i) => <p key={i}>{d}</p>)}</section><section className="panel"><h3>Learning objectives</h3>{review.analysis.learning_objectives.map(c => <button className="objective" key={c.name} onClick={() => {setConcept(c.name);setQuestionId(null);setView('teaching');}}><BookOpen size={15}/>{c.name}<ChevronRight size={14}/></button>)}</section></div></div>
     {(review.analysis.changed_files.length > 0 || review.base_sha) && <section className="panel"><h2>Change impact</h2><p>{review.analysis.changed_files.join(', ') || 'No file changes between these snapshots.'}</p><p>{review.analysis.changed_functions.join(' · ')}</p>{review.analysis.impacts.map((s,i) => <p key={i}>{s}</p>)}{review.diff && <pre>{review.diff}</pre>}</section>}
     <section className="panel"><div className="file-heading"><h2>Code explorer</h2><select aria-label="Select source file" value={selectedFile} onChange={e => setSelectedFile(e.target.value)}>{Object.keys(review.files).map(p => <option key={p}>{p}</option>)}</select></div><pre className="source-code">{(review.files[selectedFile] || '').split('\n').map((l,i) => `${String(i+1).padStart(3)}  ${l}`).join('\n')}</pre><button className="text-button" onClick={() => {setConcept(selectedFile);setQuestionId(null);setView('teaching');}}>Ask about this file<ArrowRight size={13}/></button></section>
     <details className="limitations"><summary>Review scope & limitations</summary>{review.analysis.limitations.map((s,i) => <p key={i}>{s}</p>)}</details><div className="action-row"><p>Ready to connect the dots?</p><button className="primary" disabled={!!busy} onClick={() => void startTesting()}>Start testing<ArrowRight size={16}/></button></div>
    </>}
    {view === 'testing' && <div className="assessment-grid"><section className="panel question-panel"><div className="question-meta"><span className="pill">{current?.kind || 'ASSESSMENT'}</span><span>{answered.size} of {review.questions.length} answered</span></div><div className="progress-track"><span style={{width:`${review.questions.length ? answered.size/review.questions.length*100 : 0}%`}}/></div>{current ? <><div className="eyebrow">{current.concept}</div><h2>{current.prompt}</h2><References items={current.evidence} review={review} expanded/><form onSubmit={e => {e.preventDefault(); void run('Evaluating your reasoning against code evidence…', async () => {setReview(await api<Review>(`/reviews/${review.id}/answers`, {question_id:current.id, answer}));setFocusId(current.id);setAnswer('');});}}><label htmlFor="answer">Walk us through your reasoning</label><textarea id="answer" value={answer} maxLength={12000} onChange={e => setAnswer(e.target.value)} placeholder="Explain how and why. Concrete inputs and edge cases help." required disabled={!!evaluation || !!busy || review.status === 'completed'}/><div className="answer-actions"><small>Reasoning matters more than perfect wording.</small><button className="primary" disabled={!!busy || !!evaluation || review.status === 'completed'}>Submit answer<ArrowRight size={16}/></button></div></form>
      {evaluation && <div className={`feedback ${evaluation.evaluation.verdict}`}><span className="pill">{evaluation.evaluation.verdict.replaceAll('_',' ')}</span><p>{evaluation.evaluation.feedback}</p>{evaluation.evaluation.knowledge_gap && <p>Explore further: {evaluation.evaluation.knowledge_gap}</p>}<References items={evaluation.evaluation.evidence} review={review}/><div className="button-group"><button className="secondary" disabled={review.status === 'completed'} onClick={() => learn(current)}><GraduationCap size={15}/>Learn this concept</button><button className="text-button" disabled={!!busy || review.status === 'completed'} onClick={() => {const reason = window.prompt('Why should this evaluation be reconsidered?'); if (reason?.trim()) void run('Reconsidering the evaluation…', async () => {setReview(await api<Review>(`/reviews/${review.id}/answers`, {question_id:current.id, answer: evaluation.answer + '\nChallenge: ' + reason, challenge:true}));});}}>Challenge evaluation</button></div><small>AI grading is fallible. Review the evidence and challenge a judgment when needed.</small></div>}
      {evaluation && !allAnswered && <button className="primary next" disabled={!!busy} onClick={() => {setFocusId(null);setAnswer('');}}>Next question<ArrowRight size={16}/></button>}
      {allAnswered && <div className="action-row"><p>All generated questions answered.</p><button className="primary" onClick={() => void showReport()}>View report<ArrowRight size={16}/></button></div>}
     </> : <><h2>Your assessment is ready to begin.</h2><button className="primary" onClick={() => void startTesting()}>Generate questions</button></>}</section><aside className="panel assessment-aside"><h3>Your learning path</h3>{review.questions.map((q,i) => <button className={q.id === current?.id ? 'question-link current' : 'question-link'} key={q.id} onClick={() => {setFocusId(q.id);setAnswer('');}}><span>{answered.has(q.id) ? <Check size={14}/> : i+1}</span><div>{q.concept}<small>{q.kind}</small></div></button>)}<div className="tutor-note"><Sparkles size={20}/><h3>Stuck is a starting point.</h3><p>Your tutor uses this exact code to help you reason through a concept.</p></div></aside></div>}
    {view === 'teaching' && <section className="panel teaching-panel"><div className="file-heading"><div className="section-title"><GraduationCap size={22}/><h2>Your code, explained together</h2></div><button className="secondary" disabled={!!busy} onClick={() => {if (questionId && review.conversations.some(c => c.concept === concept) && answered.has(questionId)) void retest(); else void startTesting();}}><RotateCcw size={15}/>{questionId ? 'Return & retest' : 'Return to testing'}</button></div><label htmlFor="concept">Explore a concept or file</label><select id="concept" value={concept} onChange={e => {setConcept(e.target.value);setQuestionId(null);}}>{Array.from(new Set([...review.analysis.learning_objectives.map(c => c.name), ...review.analysis.components.map(c=>c.name), ...review.analysis.algorithms.map(c=>c.name), ...Object.keys(review.files)])).map(c => <option key={c}>{c}</option>)}</select><div className="chat" aria-live="polite">{!review.conversations.length && <div className="chat-empty"><MessageSquare size={30}/><h3>Let’s work through it.</h3><p>Ask about a function, a design choice, or an edge case.<br/>Your tutor has the analysis and code context.</p></div>}{review.conversations.map(c => <div key={c.id}><div className="chat-message user-message"><span className="chat-label">YOU · {c.concept}</span><p>{c.message}</p></div><div className="chat-message tutor-message"><span className="chat-label"><Sparkles size={13}/>OWNIT TUTOR</span><p>{c.response.explanation}</p><div className="hint">{c.response.hint}</div><p className="checkpoint">{c.response.checkpoint}</p><References items={c.response.evidence} review={review}/></div></div>)}</div><form onSubmit={e => {e.preventDefault(); void run('Your tutor is working through the code…', async () => {setReview(await api<Review>(`/reviews/${review.id}/teach`, {message, concept, question_id:questionId}));setMessage('');});}}><textarea aria-label="Message to tutor" placeholder="Help me understand why this works…" value={message} maxLength={8000} onChange={e => setMessage(e.target.value)} required disabled={!!busy || review.status==='completed'}/><div className="answer-actions"><small>Teaching helps you learn. A retest records what changed.</small><button className="primary" disabled={!!busy || review.status==='completed'}>Send message<ArrowRight size={16}/></button></div></form></section>}
    {view === 'report' && report && <><div className="report-stats">{[[report.questions_answered,'Questions answered'],[report.concepts_understood.length,'Concepts demonstrated'],[report.knowledge_gaps.length,'Concepts to revisit'],[report.teaching_exchanges,'Tutor exchanges']].map(([n,label]) => <section className="panel" key={label}><strong>{n}</strong><p>{label}</p></section>)}</div><div className="two-col"><section className="panel"><h2>Assessment outcomes</h2>{Object.entries(report.outcomes).map(([k,v]) => <div className="outcome" key={k}><span>{k.replaceAll('_',' ')}</span><strong>{v}</strong></div>)}<small>Counts reflect the latest evaluation of each answered question. Teaching alone never counts as a pass.</small></section><section className="panel"><h2>What you’ve demonstrated</h2>{report.concepts_understood.map(c => <p className="success-text" key={c}><Check size={15}/>{c}</p>)}{!report.concepts_understood.length && <p>Complete an assessment to record demonstrated concepts.</p>}<h3>Next learning steps</h3>{report.next_steps.map((s,i) => <p key={i}>{s}</p>)}{!report.next_steps.length && <p>Try a new commit or a different edge case to extend your understanding.</p>}</section></div><section className="panel"><h2>Before → after retesting</h2>{report.retest_improvements.length ? report.retest_improvements.map((r,i) => <div className="outcome" key={i}><span>{r.concept}</span><span>{r.before.replaceAll('_',' ')} → {r.after.replaceAll('_',' ')}</span></div>) : <p>Use Test → Teach → Retest to compare outcomes on the same concept.</p>}<References items={report.evidence} review={review}/></section><div className="action-row"><p>{review.status === 'completed' ? 'Completed. This commit is now the baseline for the next review.' : 'Complete an assessment to use this commit as your next comparison baseline.'}</p><button className="primary" disabled={!!busy || !allAnswered || review.status==='completed'} onClick={() => void run('Completing the review…', async () => {setReview(await api<Review>(`/reviews/${review.id}/complete`, {}));setReport(await api<Report>(`/reviews/${review.id}/report`));setHistory(await api<History[]>('/reviews'));})}>Complete review<Check size={16}/></button></div></>}
   </div>}
  </main>
 </div>;
}
