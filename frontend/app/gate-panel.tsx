'use client';
import { useEffect, useState } from 'react';
import { Github, LoaderCircle, ShieldAlert, Check } from 'lucide-react';
import { API, api } from './api';
import type { Auth, Gate, Review } from './types';

export default function GatePanel({job, auth, onUpdate, onReady, passed}: {job: Gate; auth: Auth | null; onUpdate: (job: Gate) => void; onReady: (r: Review) => void; passed: boolean}) {
 const [error, setError] = useState('');
 const {id, state} = job;
 const userId = auth?.user?.id;
 useEffect(() => {
  let stopped = false;
  async function refresh() {
   try {
    const next = await api<Gate>(`/pull-requests/${id}`);
    if (stopped) return;
    onUpdate(next);
    if (next.review_id && userId === next.author_id && ['quiz_required','passed'].includes(next.state)) {
     const r = await api<Review>(`/reviews/${next.review_id}`);
     if (!stopped) onReady(r);
    }
   } catch (e) { if (!stopped) setError(e instanceof Error ? e.message : 'Could not load this checkpoint.'); }
  }
  void refresh();
  const timer = ['queued','analyzing'].includes(state) ? setInterval(() => void refresh(), 2500) : null;
  return () => {stopped = true; if (timer) clearInterval(timer);};
 }, [id, state, userId, onUpdate, onReady]);

 async function retry() {
  try {
   setError('');
   const next = state === 'stale'
    ? await api<Gate>('/pull-requests', {url:`https://github.com/${job.repo}/pull/${job.number}`})
    : await api<Gate>(`/pull-requests/${id}/retry`, {});
   window.history.replaceState(null, '', `/?job=${next.id}`);
   onUpdate(next);
  } catch (e) {setError(e instanceof Error ? e.message : 'Could not retry.');}
 }
 const success = state === 'passed' || (passed && !['stale','error'].includes(state));
 return <section className={`panel gate-panel ${success ? 'gate-passed' : ''}`} aria-live="polite">
  <div className="section-title">{success ? <Check size={20}/> : ['queued','analyzing'].includes(state) ? <LoaderCircle size={20} className="spin"/> : <ShieldAlert size={20}/>}<h2>{success ? 'Understanding check passed' : 'Merge checkpoint: blocked'}</h2><span className="pill">PR #{job.number}</span></div>
  <p><a href={`https://github.com/${job.repo}/pull/${job.number}`} target="_blank" rel="noreferrer">{job.repo}</a> · author @{job.author} · commit <code>{job.sha.slice(0,10)}</code></p>
  <p>{success ? 'OwnIt approved this commit. GitHub still applies the repository’s other merge requirements.' : state === 'queued' || state === 'analyzing' ? 'Reading the PR diff and preparing questions about the code you changed. Merging stays blocked.' : 'Explain your changes, their consequences, and edge cases. Every assessed concept needs a correct evaluation before this check can pass.'}</p>
  {(job.error || error) && <p className="gate-error" role="alert">{error || job.error}</p>}
  {!auth?.user && <a className="secondary" href={`${API}/auth/github?job=${id}`}><Github size={15}/>Sign in as the PR author</a>}
  {auth?.user && auth.user.id !== job.author_id && <p className="gate-error">You are signed in as @{auth.user.login}. This quiz belongs to @{job.author}.</p>}
  {userId === job.author_id && ['error','stale'].includes(state) && <button className="secondary" onClick={() => void retry()}>{state === 'stale' ? 'Open checkpoint for latest commit' : 'Retry analysis'}</button>}
 </section>;
}
