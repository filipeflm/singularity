/**
 * Cliente HTTP para a API do Singular.
 * Usa o proxy do Vite (/api → http://localhost:8000).
 */

const BASE_URL = '/api'

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `Erro ${res.status}`)
  }

  if (res.status === 204) return null as T
  return res.json()
}

// ─── Tipos ────────────────────────────────────────────────────────────────────

export interface Lesson {
  id: number
  url: string | null
  title: string | null
  language: string | null
  level: string | null
  status: 'pending' | 'processing' | 'ready' | 'error'
  error_message: string | null
  created_at: string
  processed_at: string | null
  cards_count: number
  exercises_count: number
}

export interface LessonStatus {
  lesson_id: number
  status: string
  error_message: string | null
  cards_count: number
  exercises_count: number
  items_count: number
  processed_at: string | null
}

export interface CardDue {
  srs_id: number
  card_id: number
  card_type: string
  front: string
  back: string
  hint: string | null
  state: string
  interval: number
  lapses: number
  retention_probability: number
  due_date: string | null
  lesson_title: string | null
  item_type: string | null
  context_sentence: string | null
}

export interface ReviewResult {
  card_id: number
  was_correct: boolean
  new_state: string
  new_interval: number
  next_due: string
  quality: number
  feedback: string
}

export interface Exercise {
  id: number
  card_id: number
  type: 'translation' | 'fill_blank' | 'build_sentence'
  prompt: string
  context: string | null
  options: string[] | null
  card_type: string | null
}

export interface ExerciseEvaluation {
  exercise_id: number
  is_correct: boolean
  score: number
  feedback: string
  error_category: string | null
  expected_answer: string
  user_answer: string
}

export interface ProgressStats {
  total_cards: number
  cards_by_state: { new: number; learning: number; review: number; relearning: number }
  cards_due_now: number
  mastered_cards: number
  total_lessons: number
  accuracy_7d: number
  reviews_7d: number
  avg_retention_estimate: number
  daily_reviews: Record<string, number>
}

export interface AdaptationSummary {
  active_patterns: Array<{
    type: string
    description: string
    severity: number
    count: number
    last_seen: string | null
  }>
  recommended_exercise_type: string | null
  daily_new_cards_limit: number
  has_active_weaknesses: boolean
}

export interface ReviewStats {
  due_now: number
  new_cards: number
  relearning: number
  total_pending: number
}

// ─── API de Aulas ─────────────────────────────────────────────────────────────

export const lessonsApi = {
  create: (data: { url?: string; title?: string; language?: string; use_mock?: boolean }) =>
    request<Lesson>('/lessons', { method: 'POST', body: JSON.stringify(data) }),

  list: () => request<Lesson[]>('/lessons'),

  get: (id: number) => request<Lesson>(`/lessons/${id}`),

  getStatus: (id: number) => request<LessonStatus>(`/lessons/${id}/status`),

  getItems: (id: number) => request<{ items: any[] }>(`/lessons/${id}/items`),

  delete: (id: number) => request<null>(`/lessons/${id}`, { method: 'DELETE' }),
}

// ─── API de Revisão ───────────────────────────────────────────────────────────

export const reviewApi = {
  getDue: (limit = 20, includeNew = true) =>
    request<{ cards: CardDue[]; total: number }>(
      `/review/due?limit=${limit}&include_new=${includeNew}`
    ),

  submit: (cardId: number, quality: number, responseTimeMs?: number) =>
    request<ReviewResult>('/review/submit', {
      method: 'POST',
      body: JSON.stringify({ card_id: cardId, quality, response_time_ms: responseTimeMs }),
    }),

  getStats: () => request<ReviewStats>('/review/stats'),
}

// ─── API de Exercícios ────────────────────────────────────────────────────────

export const exercisesApi = {
  getAll: (params?: { limit?: number; exercise_type?: string; lesson_id?: number }) => {
    const qs = new URLSearchParams()
    if (params?.limit) qs.set('limit', String(params.limit))
    if (params?.exercise_type) qs.set('exercise_type', params.exercise_type)
    if (params?.lesson_id) qs.set('lesson_id', String(params.lesson_id))
    return request<{ exercises: Exercise[]; total: number }>(`/exercises?${qs}`)
  },

  submit: (exerciseId: number, userAnswer: string, responseTimeMs?: number) =>
    request<ExerciseEvaluation>('/exercises/submit', {
      method: 'POST',
      body: JSON.stringify({
        exercise_id: exerciseId,
        user_answer: userAnswer,
        response_time_ms: responseTimeMs,
      }),
    }),

  getByLesson: (lessonId: number) =>
    request<{ exercises: Exercise[]; total: number }>(`/exercises/by-lesson/${lessonId}`),
}

// ─── API de Progresso ─────────────────────────────────────────────────────────

export const progressApi = {
  get: () => request<ProgressStats>('/progress'),
  getAdaptation: () => request<AdaptationSummary>('/progress/adaptation'),
}
