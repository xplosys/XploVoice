# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Knowledge bases (M12): create, add documents (upload or pasted text), remove, archive, and test search.
Agents are granted knowledge bases on their version (`knowledge_base_ids`); retrieval during a call uses only
those."""

import base64
import binascii
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from ...core.context import Ctx, require
from ...core.errors import ApiError, bad_request, conflict, not_found
from ...core.permissions import Perm
from .ingest import MAX_BYTES, IngestError, ScannerUnavailableError, scanner_status
from .models import KbChunk, KbDocument, KnowledgeBase
from .service import add_document, remove_document, search

router = APIRouter(prefix="/v1/knowledge-bases", tags=["knowledge"])


class KbIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)


class KbPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    status: Literal["active", "archived"] | None = None


class KbOut(BaseModel):
    id: UUID
    name: str
    description: str
    status: str
    documents: int
    ready_documents: int
    chunks: int
    created_at: datetime
    updated_at: datetime
    scanner: str


class DocumentOut(BaseModel):
    id: UUID
    title: str
    source: str
    filename: str | None
    mime: str | None
    size_bytes: int
    status: str
    scan_engine: str | None
    scan_result: str | None
    error: str | None
    chunk_count: int
    char_count: int
    created_at: datetime


class UploadIn(BaseModel):
    title: str = Field(default="", max_length=200)
    filename: str = Field(min_length=1, max_length=255)
    content_base64: str = Field(max_length=MAX_BYTES * 4 // 3 + 8)


class TextIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=200_000)


class SearchIn(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=4, ge=1, le=10)


class HitOut(BaseModel):
    document_id: UUID
    document: str
    content: str
    score: float


class ChunkOut(BaseModel):
    seq: int
    content: str


def _kb(ctx: Ctx, kb_id: UUID) -> KnowledgeBase:
    kb = ctx.session.scalar(
        select(KnowledgeBase).where(KnowledgeBase.id == kb_id, KnowledgeBase.tenant_id == ctx.tenant.id)
    )
    if not kb:
        raise not_found()
    return kb


def _out(ctx: Ctx, kb: KnowledgeBase) -> KbOut:
    s = ctx.session
    docs = s.execute(
        select(func.count(), func.count().filter(KbDocument.status == "ready")).where(KbDocument.kb_id == kb.id)
    ).one()
    chunks = s.scalar(select(func.count()).select_from(KbChunk).where(KbChunk.kb_id == kb.id)) or 0
    return KbOut(
        id=kb.id,
        name=kb.name,
        description=kb.description,
        status=kb.status,
        documents=docs[0],
        ready_documents=docs[1],
        chunks=chunks,
        created_at=kb.created_at,
        updated_at=kb.updated_at,
        scanner=scanner_status(),
    )


def _doc_out(d: KbDocument) -> DocumentOut:
    return DocumentOut.model_validate(d, from_attributes=True)


@router.get("", response_model=list[KbOut])
def list_kbs(ctx: Ctx = Depends(require(Perm.KNOWLEDGE_READ))) -> list[KbOut]:
    rows = ctx.session.scalars(select(KnowledgeBase).order_by(KnowledgeBase.status, KnowledgeBase.name)).all()
    return [_out(ctx, kb) for kb in rows]


@router.post("", response_model=KbOut, status_code=status.HTTP_201_CREATED)
def create_kb(data: KbIn, ctx: Ctx = Depends(require(Perm.KNOWLEDGE_MANAGE))) -> KbOut:
    kb = KnowledgeBase(
        tenant_id=ctx.tenant.id,
        name=data.name.strip(),
        description=data.description.strip(),
        created_by_membership_id=ctx.membership.id,
    )
    ctx.session.add(kb)
    ctx.session.flush()
    ctx.audit("knowledge_base.created", resource_type="knowledge_base", resource_id=str(kb.id))
    ctx.session.refresh(kb)
    return _out(ctx, kb)


@router.get("/{kb_id}", response_model=KbOut)
def read_kb(kb_id: UUID, ctx: Ctx = Depends(require(Perm.KNOWLEDGE_READ))) -> KbOut:
    return _out(ctx, _kb(ctx, kb_id))


@router.patch("/{kb_id}", response_model=KbOut)
def update_kb(kb_id: UUID, data: KbPatch, ctx: Ctx = Depends(require(Perm.KNOWLEDGE_MANAGE))) -> KbOut:
    kb = _kb(ctx, kb_id)
    if data.name is not None:
        kb.name = data.name.strip()
    if data.description is not None:
        kb.description = data.description.strip()
    if data.status and data.status != kb.status:
        kb.status = data.status
        ctx.audit(
            f"knowledge_base.{'archived' if data.status == 'archived' else 'restored'}",
            resource_type="knowledge_base",
            resource_id=str(kb.id),
        )
    ctx.session.flush()
    ctx.session.refresh(kb)
    return _out(ctx, kb)


@router.get("/{kb_id}/documents", response_model=list[DocumentOut])
def list_documents(kb_id: UUID, ctx: Ctx = Depends(require(Perm.KNOWLEDGE_READ))) -> list[DocumentOut]:
    kb = _kb(ctx, kb_id)
    rows = ctx.session.scalars(
        select(KbDocument).where(KbDocument.kb_id == kb.id).order_by(KbDocument.created_at.desc())
    ).all()
    return [_doc_out(d) for d in rows]


def _add(ctx: Ctx, kb: KnowledgeBase, **kw: object) -> DocumentOut:
    if kb.status != "active":
        raise conflict("archived", "Restore this knowledge base before adding documents.")
    try:
        doc = add_document(ctx.session, kb, membership_id=ctx.membership.id, **kw)  # type: ignore[arg-type]
    except IngestError as e:
        raise bad_request(e.code, e.message) from None
    except ScannerUnavailableError as e:
        raise ApiError(503, "scanner_unavailable", str(e)) from None
    ctx.session.flush()
    ctx.audit(
        "knowledge_base.document_added",
        result="success" if doc.status == "ready" else "denied",
        resource_type="kb_document",
        resource_id=str(doc.id),
        status=doc.status,
        size_bytes=doc.size_bytes,
        scan_engine=doc.scan_engine,
    )
    ctx.session.refresh(doc)
    return _doc_out(doc)


@router.post("/{kb_id}/documents", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
def upload(kb_id: UUID, data: UploadIn, ctx: Ctx = Depends(require(Perm.KNOWLEDGE_MANAGE))) -> DocumentOut:
    try:
        raw = base64.b64decode(data.content_base64, validate=True)
    except (binascii.Error, ValueError):
        raise bad_request("invalid_file", "The file must be base64 encoded") from None
    if len(raw) > MAX_BYTES:
        raise bad_request("too_large", "Files can be at most 5 MB.")
    if not raw:
        raise bad_request("empty", "The file is empty.")
    name = data.filename.replace("\\", "/").rsplit("/", 1)[-1]
    title = data.title or name.rsplit(".", 1)[0]
    return _add(ctx, _kb(ctx, kb_id), title=title, data=raw, filename=name)


@router.post("/{kb_id}/documents/text", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
def add_text(kb_id: UUID, data: TextIn, ctx: Ctx = Depends(require(Perm.KNOWLEDGE_MANAGE))) -> DocumentOut:
    return _add(ctx, _kb(ctx, kb_id), title=data.title, pasted=data.text)


def _doc(ctx: Ctx, kb: KnowledgeBase, doc_id: UUID) -> KbDocument:
    d = ctx.session.scalar(select(KbDocument).where(KbDocument.id == doc_id, KbDocument.kb_id == kb.id))
    if not d:
        raise not_found()
    return d


@router.get("/{kb_id}/documents/{doc_id}/chunks", response_model=list[ChunkOut])
def read_chunks(kb_id: UUID, doc_id: UUID, ctx: Ctx = Depends(require(Perm.KNOWLEDGE_READ))) -> list[ChunkOut]:
    d = _doc(ctx, _kb(ctx, kb_id), doc_id)
    rows = ctx.session.scalars(select(KbChunk).where(KbChunk.document_id == d.id).order_by(KbChunk.seq)).all()
    return [ChunkOut(seq=c.seq, content=c.content) for c in rows]


@router.delete("/{kb_id}/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(kb_id: UUID, doc_id: UUID, ctx: Ctx = Depends(require(Perm.KNOWLEDGE_MANAGE))) -> Response:
    d = _doc(ctx, _kb(ctx, kb_id), doc_id)
    remove_document(ctx.session, d)
    ctx.audit("knowledge_base.document_removed", resource_type="kb_document", resource_id=str(doc_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{kb_id}/search", response_model=list[HitOut])
def test_search(kb_id: UUID, data: SearchIn, ctx: Ctx = Depends(require(Perm.KNOWLEDGE_READ))) -> list[HitOut]:
    kb = _kb(ctx, kb_id)
    if kb.status != "active":
        return []
    hits = search(ctx.session, [kb.id], data.query, limit=data.limit, source="test")
    return [HitOut(document_id=h.document_id, document=h.document, content=h.content, score=h.score) for h in hits]
