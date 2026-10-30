export type Evidence = { path: string; start: number; end: number };
export type Concept = { name: string; explanation: string; evidence: Evidence[] };
export type Question = { id: string; concept: string; prompt: string; evidence: Evidence[]; parent_id?: string; kind: string };
export type Evaluation = { verdict: string; feedback: string; knowledge_gap?: string; followup?: string; evidence: Evidence[] };
export type Teaching = { explanation: string; hint: string; checkpoint: string; evidence: Evidence[] };
export type Review = {
 id: string; repo: string; sha: string; base_sha?: string; demo: boolean; status: string; created_at: string;
 analysis: { review_type: string; summary: string; components: Concept[]; algorithms: Concept[]; apis_and_dependencies: string[]; data_flow: string[]; changed_files: string[]; changed_functions: string[]; impacts: string[]; risks: {level: string; description: string; confirmed: boolean; evidence: Evidence[]}[]; learning_objectives: Concept[]; limitations: string[] };
 files: Record<string, string>; diff: string; questions: Question[];
 answers: { id: string; question_id: string; answer: string; evaluation: Evaluation; challenge: boolean }[];
 conversations: { id: string; concept: string; question_id?: string; message: string; response: Teaching }[];
};
export type Report = { status: string; questions_answered: number; outcomes: Record<string, number>; concepts_understood: string[]; knowledge_gaps: string[]; teaching_exchanges: number; retest_improvements: {concept: string; before: string; after: string}[]; next_steps: string[]; evidence: Evidence[] };
export type History = Pick<Review, 'id' | 'repo' | 'sha' | 'status' | 'demo' | 'created_at'>;
