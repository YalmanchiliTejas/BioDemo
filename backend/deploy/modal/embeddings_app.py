"""Embedding service for assistant memory recall (docs/architecture/assistant-memory.md).

OpenAI-compatible POST /v1/embeddings on Modal, behind Modal proxy auth (the same wk-/ws- proxy token as the GLM
endpoint; send Modal-Key / Modal-Secret). Text never leaves this Modal workspace. Scales to zero when idle.

Deploy:  MODAL_PROFILE=gauntlet modal deploy backend/deploy/modal/embeddings_app.py
"""
import modal

MODEL = 'Qwen/Qwen3-Embedding-0.6B'
REVISION = 'main'

image = (modal.Image.debian_slim(python_version='3.12')
         .pip_install('sentence-transformers==5.1.0', 'torch==2.8.0', 'fastapi[standard]==0.116.1')
         .env({'HF_HUB_ENABLE_HF_TRANSFER': '0'}))
cache = modal.Volume.from_name('biodemo-embeddings-cache', create_if_missing=True)
app = modal.App('biodemo-embeddings', image=image)


@app.cls(gpu='T4', volumes={'/cache': cache}, scaledown_window=300, timeout=600)
@modal.concurrent(max_inputs=16)
class Embedder:
    @modal.enter()
    def load(self):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(MODEL, revision=REVISION, cache_folder='/cache', device='cuda')

    @modal.fastapi_endpoint(method='POST', requires_proxy_auth=True, label='biodemo-embeddings')
    def embeddings(self, body: dict):
        from fastapi import HTTPException
        texts = body.get('input')
        texts = [texts] if isinstance(texts, str) else texts
        if not isinstance(texts, list) or not texts or len(texts) > 256 or not all(isinstance(t, str) for t in texts):
            raise HTTPException(400, 'input must be a string or a list of 1-256 strings')
        texts = [t[:8000] for t in texts]
        # Queries get the model's retrieval instruction; stored documents are embedded as-is.
        kind = body.get('input_type', 'document')
        vectors = self.model.encode(texts, prompt_name='query' if kind == 'query' else None,
                                    normalize_embeddings=True, batch_size=32)
        return {'object': 'list', 'model': MODEL,
                'data': [{'object': 'embedding', 'index': i, 'embedding': v.tolist()} for i, v in enumerate(vectors)],
                'usage': {'prompt_tokens': sum(len(t) // 4 for t in texts)}}
