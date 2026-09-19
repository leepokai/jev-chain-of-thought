export type Question =
  | { type: "noul"; instructions: unknown; criteria?: { true: unknown; false: unknown } }
  | { type: "choice"; instructions: unknown; criteria: Record<string, unknown> }
  | { type: "score"; instructions: unknown; criteria: unknown[] };
export type Answer = { p?: number; choice?: string; probabilities?: Record<string, number>; score?: number; confidence?: number };
export type Response = { answers: Record<string, Answer>; usage: { input: number; output: number }; model?: string; ms: number };
export type Ask = (state: unknown, questions: Record<string, Question>, opts?: Record<string, unknown>) => Promise<Response>;
export type Opts = { model?: string; key?: string; ask?: Ask; retries?: number; timeoutMs?: number };
export type Result = { answers: Record<string, Answer>; trace: Response[]; calls: number; usage: { input: number; output: number } };

export function ask(state: unknown, questions: Record<string, Question>, opts?: Opts): Promise<Response>;
export function render(answers: Record<string, Answer>): string;
export function feedback<S>(state: S, answers: Record<string, Answer>, kind?: "draft" | "facts"): S | string;
export function label(a: Answer): string;
export function top(a: Answer): number;
export function same(a: Record<string, Answer>, b: Record<string, Answer>): boolean;
export function refine(state: unknown, questions: Record<string, Question>, opts?: Opts & { rounds?: number; first?: Response }): Promise<Result>;
export function chain(state: unknown, steps: Record<string, Question>[], opts?: Opts & { refine?: number }): Promise<Result>;
export function choose(state: unknown, options: Record<string, unknown>, opts?: Opts & {
  instructions?: unknown; strategy?: "direct" | "refine" | "permute" | "verify" | "narrow" | "cot" | "product"; k?: number; permutations?: number; id?: string;
}): Promise<{ choice: string; probabilities: Record<string, number>; trace: Response[]; calls: number }>;
export function rerank(query: unknown, candidates: Record<string, unknown>, opts: Opts & {
  instructions: unknown; criteria?: { true: unknown; false: unknown }; strategy?: "pointwise" | "fanout" | "listwise" | "cot"; topK?: number; concurrency?: number;
  queryKey?: string; candidateKey?: string; pointwise?: "pointwise" | "fanout"; facets?: Record<string, { instructions: unknown; criteria?: { true: unknown; false: unknown } }>; scores?: Record<string, number>;
}): Promise<{ ranking: string[]; scores: Record<string, number>; trace: Response[]; calls: number }>;
export function pmap<T, R>(items: T[], fn: (item: T, i: number) => Promise<R>, n?: number): Promise<R[]>;
