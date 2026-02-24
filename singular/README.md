# Singular — Motor de Aprendizado Adaptativo de Idiomas

> "Se o aluno usar o Singular por 90 dias, ele deve aprender mais do que YouTube + Anki + Caderno + Duolingo separados."

Sistema inteligente que transforma aulas do YouTube em um motor completo de aprendizado adaptativo: transcrição → extração → cards → exercícios → revisão espaçada → adaptação.

---

## Stack

| Camada | Tecnologia |
|---|---|
| Backend | FastAPI + SQLAlchemy + SQLite |
| IA | Anthropic Claude (claude-3-haiku) |
| Transcrição | youtube-transcript-api (grátis) |
| Frontend | React + Vite + TypeScript |

---

## Requisitos

- Python 3.10+
- Node.js 18+
- Chave da API Anthropic (para extração e exercícios reais)

---

## Como rodar localmente

### 1. Clone e entre no projeto

```bash
cd singular
```

### 2. Backend

```bash
cd backend

# Cria e ativa ambiente virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou: venv\Scripts\activate  # Windows

# Instala dependências
pip install -r requirements.txt

# Configura variáveis de ambiente
cp env.example .env
# Edite o .env e adicione sua ANTHROPIC_API_KEY

# Roda o seed (cria dados de teste)
python seed.py

# Inicia o servidor
uvicorn app.main:app --reload
```

Backend disponível em: http://localhost:8000
Documentação da API: http://localhost:8000/docs

### 3. Frontend

```bash
# Em outro terminal, a partir de singular/
cd frontend

npm install
npm run dev
```

Frontend disponível em: http://localhost:5173

---

## Testar sem API Key (modo mock)

O sistema funciona **sem ANTHROPIC_API_KEY** usando o modo mock:

1. Abra http://localhost:5173
2. Na tela "Importar Aula", ative o toggle **"Modo de teste (mock)"**
3. Clique em "Importar e Processar Aula"
4. Aguarde o pipeline processar (2-5 segundos)
5. Explore revisão, exercícios e progresso

O seed também já pré-popula dados para exploração imediata.

---

## Variáveis de ambiente

| Variável | Descrição |
|---|---|
| `ANTHROPIC_API_KEY` | Chave da API Anthropic. Se ausente, usa geração local de exercícios. |
| `ENVIRONMENT` | `development` ou `production` |

---

## Estrutura do Projeto

```
singular/
├── backend/
│   ├── app/
│   │   ├── domain/
│   │   │   ├── models.py        # 9 entidades SQLAlchemy
│   │   │   ├── srs.py           # Algoritmo SM-2 adaptado
│   │   │   └── adaptation.py    # Motor de detecção de padrões de erro
│   │   ├── services/
│   │   │   ├── pipeline.py      # Orquestrador: URL → Cards → SRS
│   │   │   ├── transcription.py # youtube-transcript-api
│   │   │   ├── extraction.py    # Extração via Claude (JSON validado)
│   │   │   ├── exercise.py      # Geração de exercícios + avaliação
│   │   │   └── review.py        # Fila de revisão e métricas
│   │   ├── api/
│   │   │   ├── lessons.py       # POST/GET /lessons
│   │   │   ├── cards.py         # GET/POST /review
│   │   │   ├── exercises.py     # GET/POST /exercises
│   │   │   └── progress.py      # GET /progress
│   │   ├── database.py
│   │   └── main.py
│   ├── seed.py
│   └── requirements.txt
└── frontend/
    └── src/
        ├── pages/
        │   ├── ImportLesson.tsx  # Tela 1: importar aula
        │   ├── LessonStatus.tsx  # Tela 2: status do pipeline
        │   ├── Review.tsx        # Tela 3: revisão de cards (SRS)
        │   ├── Exercises.tsx     # Tela 4: exercícios ativos
        │   └── Progress.tsx      # Tela 5: métricas e adaptação
        └── api/client.ts
```

---

## Funcionalidades do MVP

### Pipeline de Importação
1. Recebe URL do YouTube
2. Extrai transcript via `youtube-transcript-api` (grátis)
3. Extrai vocabulário, frases e gramática via Claude
4. Gera cards estruturados (front/back/hint)
5. Gera 3 tipos de exercício por card
6. Inicializa SRS para todos os cards

### Revisão Espaçada (SM-2 adaptado)
- Estados: `new → learning → review → relearning`
- Qualidade 0-5 após cada revisão
- Intervalos calculados por ease_factor + histórico de lapsos
- Penalidade adaptativa para cards com padrões de erro

### Motor de Adaptação
- Detecta `vocab_weakness` se erro > 40% em vocabulário
- Detecta `grammar_confusion` se erro > 35% em gramática
- Detecta `structure_confusion` se erro > 45% em build_sentence
- Reduz limite de novos cards e intervalo SRS conforme severidade
- Recomenda tipo de exercício prioritário

### Exercícios Ativos
- **Tradução**: traduza a palavra/frase para o idioma alvo
- **Completar Lacuna**: preencha o ___ na frase
- **Construir Frase**: organize as palavras na ordem correta
- Avaliação automática com detecção de categoria de erro

---

## Princípios (do bigbang.md)

1. Menos gamificação, mais retenção.
2. Erro é informação, não falha.
3. Aprendizado é cumulativo.
4. Aula é matéria-prima, não produto final.
5. O sistema deve reduzir fricção, não criar nova.
