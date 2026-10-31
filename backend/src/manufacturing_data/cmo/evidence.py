"""Durable storage for original CMO files.

Parsing always works on a local cache. With ``SUPABASE_URL`` and
``SUPABASE_SERVICE_ROLE_KEY`` set, original bytes are also written once to a
private Supabase Storage bucket (``CMO_STORAGE_BUCKET``, default
``cmo-evidence``) under content-addressed keys, and restored from there when
the local cache is gone (for example after a container restart). Every read is
re-hashed; a mismatch is an integrity failure, never a silent substitution.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from urllib.parse import quote


class IntegrityError(ValueError):
    pass


def sha256_file(path):
    with Path(path).open('rb') as stream: return hashlib.file_digest(stream,'sha256').hexdigest()


class LocalEvidence:
    backend='local'

    def put(self, key, path): return None

    def get(self, key, destination): raise FileNotFoundError(f'Original {key} is not in the local cache and no durable store is configured')

    def signed_upload(self, key): raise RuntimeError('Direct-to-storage uploads need Supabase Storage')

    def delete(self, key): return None


class SupabaseEvidence:
    backend='supabase'

    def __init__(self, url, service_key, bucket):
        import httpx
        self.base=url.rstrip('/')+'/storage/v1'
        self.bucket=bucket
        self.client=httpx.Client(timeout=120,headers={'Authorization':'Bearer '+service_key,'apikey':service_key},follow_redirects=False)

    def _object(self, key): return f'{self.base}/object/{quote(self.bucket)}/{quote(key)}'

    def put(self, key, path):
        data=Path(path).read_bytes()
        # Content-addressed and write-once: an existing object is never replaced.
        response=self.client.post(self._object(key),content=data,headers={'x-upsert':'false','Content-Type':'application/octet-stream'})
        if response.status_code in {200,201}: return key
        if response.status_code in {400,409} and 'exist' in response.text.lower(): return key
        raise RuntimeError(f'Supabase Storage write failed ({response.status_code}): {response.text[:200]}')

    def signed_upload(self, key):
        """A single-use URL the browser can PUT one file to without other credentials (valid two hours)."""
        response=self.client.post(f'{self.base}/object/upload/sign/{quote(self.bucket)}/{quote(key)}',json={})
        if response.status_code not in {200,201}:
            raise RuntimeError(f'Supabase Storage could not sign an upload ({response.status_code}): {response.text[:200]}')
        path=response.json().get('url','')
        if 'token=' not in path: raise RuntimeError('Supabase Storage returned no upload token')
        return {'url':self.base+path,'method':'PUT',
                'headers':{'Content-Type':'application/octet-stream','x-upsert':'false'}}

    def delete(self, key):
        # Removes a transport copy only; content-addressed originals are never deleted here.
        if not key.startswith('uploads/'): raise ValueError('Only pending uploads can be deleted')
        response=self.client.request('DELETE',f'{self.base}/object/{quote(self.bucket)}',json={'prefixes':[key]})
        if response.status_code not in {200,204,404}:
            raise RuntimeError(f'Supabase Storage delete failed ({response.status_code})')

    def get(self, key, destination):
        response=self.client.get(self._object(key))
        if response.status_code==404 or (response.status_code==400 and 'not found' in response.text.lower()):
            raise FileNotFoundError(f'Original {key} is absent from durable storage')
        if response.status_code!=200: raise RuntimeError(f'Supabase Storage read failed ({response.status_code})')
        destination=Path(destination); destination.parent.mkdir(parents=True,exist_ok=True)
        temporary=destination.with_suffix(destination.suffix+'.partial')
        temporary.write_bytes(response.content); temporary.replace(destination)
        return destination


def evidence_store():
    url=os.getenv('SUPABASE_URL','').strip(); key=os.getenv('SUPABASE_SERVICE_ROLE_KEY','').strip()
    if url and key:
        return SupabaseEvidence(url,key,os.getenv('CMO_STORAGE_BUCKET','cmo-evidence'))
    return LocalEvidence()


def original_key(sha256, suffix):
    return f'originals/{sha256[:2]}/{sha256}{suffix.lower()}'


def restore(store, key, destination, expected_sha256):
    """Return a verified local path, restoring from durable storage if needed."""
    destination=Path(destination)
    if not destination.exists(): store.get(key,destination)
    if sha256_file(destination)!=expected_sha256: raise IntegrityError('Source integrity failed')
    return destination
