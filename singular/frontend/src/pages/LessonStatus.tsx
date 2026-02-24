/**
 * Tela 2 — Status da Aula
 * Mostra o progresso do pipeline e os itens extraídos após conclusão.
 * Faz polling do status enquanto o pipeline está rodando.
 */

import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { lessonsApi, type Lesson, type LessonStatus as LessonStatusType } from '../api/client'

const POLL_INTERVAL = 2000 // 2s

const steps = [
  { key: 'pending', label: 'Criando aula', desc: 'Preparando o pipeline...' },
  { key: 'processing', label: 'Processando', desc: 'Transcrevendo, extraindo e gerando cards...' },
  { key: 'ready', label: 'Concluído', desc: 'Aula pronta para estudo!' },
]

export default function LessonStatus() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [lesson, setLesson] = useState<Lesson | null>(null)
  const [status, setStatus] = useState<LessonStatusType | null>(null)
  const [items, setItems] = useState<any[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!id) return

    // Carrega detalhes iniciais
    lessonsApi.get(Number(id)).then(setLesson).catch(e => setError(e.message))

    // Polling do status
    const poll = async () => {
      try {
        const s = await lessonsApi.getStatus(Number(id))
        setStatus(s)

        if (s.status === 'ready') {
          // Carrega itens extraídos
          const data = await lessonsApi.getItems(Number(id))
          setItems(Array.isArray(data) ? data : (data as any).items || [])
        }

        return s.status
      } catch (e: any) {
        setError(e.message)
        return 'error'
      }
    }

    poll().then(s => {
      if (s !== 'ready' && s !== 'error') {
        const interval = setInterval(async () => {
          const newStatus = await poll()
          if (newStatus === 'ready' || newStatus === 'error') {
            clearInterval(interval)
          }
        }, POLL_INTERVAL)
        return () => clearInterval(interval)
      }
    })
  }, [id])

  if (error) {
    return (
      <div style={{ color: 'var(--error)', padding: '24px' }}>
        Erro: {error}
        <button onClick={() => navigate('/')} style={{
          marginLeft: '16px', padding: '6px 14px',
          background: 'var(--surface)', border: '1px solid var(--border)',
          borderRadius: '6px', color: 'var(--text)',
        }}>Voltar</button>
      </div>
    )
  }

  const currentStatus = status?.status || lesson?.status || 'pending'

  const itemTypes = {
    vocab: items.filter(i => i.type === 'vocab'),
    phrase: items.filter(i => i.type === 'phrase'),
    grammar: items.filter(i => i.type === 'grammar'),
  }

  return (
    <div>
      {/* Header */}
      <button
        onClick={() => navigate('/')}
        style={{
          marginBottom: '24px',
          padding: '6px 14px',
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          borderRadius: '6px',
          color: 'var(--text-muted)',
          fontSize: '13px',
        }}
      >
        ← Voltar
      </button>

      <h1 style={{ fontSize: '24px', fontWeight: 700, marginBottom: '4px' }}>
        {lesson?.title || 'Processando aula...'}
      </h1>
      <p style={{ color: 'var(--text-muted)', fontSize: '14px', marginBottom: '32px' }}>
        {lesson?.language === 'ja' ? '🇯🇵 Japonês' : lesson?.language || 'Idioma'} ·
        {lesson?.level ? ` Nível ${lesson.level}` : ''}
      </p>

      {/* Status do pipeline */}
      <div style={{
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: '12px',
        padding: '24px',
        marginBottom: '32px',
      }}>
        <h2 style={{ fontSize: '14px', color: 'var(--text-muted)', marginBottom: '20px', fontWeight: 500 }}>
          PIPELINE DE PROCESSAMENTO
        </h2>

        {currentStatus === 'error' ? (
          <div style={{
            padding: '16px',
            background: 'rgba(252, 129, 129, 0.1)',
            border: '1px solid rgba(252, 129, 129, 0.3)',
            borderRadius: '8px',
            color: 'var(--error)',
          }}>
            <strong>Erro no processamento:</strong><br />
            {status?.error_message || lesson?.error_message || 'Erro desconhecido'}
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {/* Passo 1: Transcrito */}
            <PipelineStep
              label="Transcrição"
              done={currentStatus === 'processing' || currentStatus === 'ready'}
              active={currentStatus === 'processing'}
              info={currentStatus === 'ready' ? 'Transcript obtido' : 'Obtendo transcript do YouTube...'}
            />
            {/* Passo 2: Extração */}
            <PipelineStep
              label="Extração de conhecimento"
              done={currentStatus === 'ready'}
              active={currentStatus === 'processing'}
              info={currentStatus === 'ready'
                ? `${status?.items_count || 0} itens extraídos`
                : 'Analisando com IA...'}
            />
            {/* Passo 3: Cards */}
            <PipelineStep
              label="Geração de cards"
              done={currentStatus === 'ready'}
              active={currentStatus === 'processing'}
              info={currentStatus === 'ready'
                ? `${status?.cards_count || 0} cards criados`
                : 'Gerando cards...'}
            />
            {/* Passo 4: Exercícios */}
            <PipelineStep
              label="Geração de exercícios"
              done={currentStatus === 'ready'}
              active={currentStatus === 'processing'}
              info={currentStatus === 'ready'
                ? `${status?.exercises_count || 0} exercícios criados`
                : 'Gerando exercícios...'}
            />
            {/* Passo 5: SRS */}
            <PipelineStep
              label="Inicialização do SRS"
              done={currentStatus === 'ready'}
              active={currentStatus === 'processing'}
              info={currentStatus === 'ready' ? 'Revisões agendadas' : 'Aguardando...'}
            />
          </div>
        )}
      </div>

      {/* Itens extraídos */}
      {currentStatus === 'ready' && items.length > 0 && (
        <>
          <div style={{ display: 'flex', gap: '12px', marginBottom: '16px', flexWrap: 'wrap' }}>
            {[
              { type: 'vocab', label: 'Vocabulário', items: itemTypes.vocab },
              { type: 'phrase', label: 'Frases', items: itemTypes.phrase },
              { type: 'grammar', label: 'Gramática', items: itemTypes.grammar },
            ].map(({ type, label, items: typeItems }) => (
              <div key={type} style={{
                padding: '12px 20px',
                background: 'var(--surface)',
                border: '1px solid var(--border)',
                borderRadius: '8px',
                textAlign: 'center',
              }}>
                <div style={{ fontSize: '22px', fontWeight: 700 }}>{typeItems.length}</div>
                <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>{label}</div>
              </div>
            ))}
          </div>

          {/* Lista de vocab */}
          {itemTypes.vocab.length > 0 && (
            <ItemSection title="📚 Vocabulário Extraído" items={itemTypes.vocab.slice(0, 8)} type="vocab" />
          )}
          {itemTypes.phrase.length > 0 && (
            <ItemSection title="💬 Frases" items={itemTypes.phrase} type="phrase" />
          )}
          {itemTypes.grammar.length > 0 && (
            <ItemSection title="📝 Gramática" items={itemTypes.grammar} type="grammar" />
          )}

          {/* CTAs */}
          <div style={{ display: 'flex', gap: '12px', marginTop: '32px' }}>
            <button
              onClick={() => navigate('/review')}
              style={{
                flex: 1,
                padding: '13px',
                background: 'var(--accent)',
                color: 'white',
                borderRadius: '8px',
                fontWeight: 600,
                fontSize: '15px',
              }}
            >
              → Iniciar Revisão
            </button>
            <button
              onClick={() => navigate('/exercises')}
              style={{
                flex: 1,
                padding: '13px',
                background: 'var(--surface)',
                color: 'var(--text)',
                border: '1px solid var(--border)',
                borderRadius: '8px',
                fontWeight: 600,
                fontSize: '15px',
              }}
            >
              → Praticar Exercícios
            </button>
          </div>
        </>
      )}

      {/* Polling indicator */}
      {(currentStatus === 'pending' || currentStatus === 'processing') && (
        <div style={{ textAlign: 'center', color: 'var(--text-muted)', marginTop: '24px', fontSize: '13px' }}>
          ⟳ Atualizando a cada {POLL_INTERVAL / 1000}s...
        </div>
      )}
    </div>
  )
}

function PipelineStep({ label, done, active, info }: {
  label: string; done: boolean; active: boolean; info: string
}) {
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: '12px',
      padding: '10px 12px',
      borderRadius: '8px',
      background: done ? 'rgba(72, 187, 120, 0.05)' : 'transparent',
    }}>
      <div style={{
        width: '20px', height: '20px',
        borderRadius: '50%',
        background: done ? 'var(--success)' : active ? 'var(--warning)' : 'var(--text-dim)',
        flexShrink: 0,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize: '11px',
      }}>
        {done ? '✓' : active ? '⟳' : '·'}
      </div>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: '14px', fontWeight: 500 }}>{label}</div>
        <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>{info}</div>
      </div>
    </div>
  )
}

function ItemSection({ title, items, type }: { title: string; items: any[]; type: string }) {
  return (
    <div style={{ marginBottom: '24px' }}>
      <h3 style={{ fontSize: '14px', color: 'var(--text-muted)', marginBottom: '12px', fontWeight: 500 }}>
        {title}
      </h3>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
        {items.map((item: any) => (
          <div key={item.id} style={{
            padding: '10px 14px',
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: '8px',
            display: 'flex',
            gap: '16px',
            alignItems: 'baseline',
          }}>
            <span style={{ fontSize: '16px', fontWeight: 600, minWidth: '120px' }}>
              {item.content}
            </span>
            {item.reading && item.reading !== item.content && (
              <span style={{ fontSize: '13px', color: 'var(--text-muted)' }}>{item.reading}</span>
            )}
            <span style={{ fontSize: '13px', color: 'var(--accent-light)', marginLeft: 'auto' }}>
              {item.translation || item.explanation?.slice(0, 60)}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
