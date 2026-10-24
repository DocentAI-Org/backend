import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, Response, UploadFile

from app.core.config import get_settings
from app.core.db import DbSession, SessionFactoryDep
from app.core.errors import error_responses
from app.core.pagination import Page, Pagination
from app.core.security import TeacherUser
from app.integrations.storage import StorageClient, get_storage
from app.llm.client import LLMClient, get_llm
from app.schemas.documents import Document, Fragment, FragmentUpdate, SignedUrl
from app.services import courses, documents

router = APIRouter(prefix="/courses/{course_id}/documents", tags=["teacher: material"])

Storage = Annotated[StorageClient, Depends(get_storage)]
LLM = Annotated[LLMClient, Depends(get_llm)]


@router.post(
    "",
    status_code=202,
    response_model=Document,
    responses=error_responses(404, 413, 415, 503),
    summary="Upload a PDF, DOCX or Markdown file; it is processed in the background",
)
def upload_document(
    course_id: uuid.UUID,
    file: Annotated[UploadFile, File()],
    teacher: TeacherUser,
    session: DbSession,
    storage: Storage,
    llm: LLM,
    session_factory: SessionFactoryDep,
    background: BackgroundTasks,
) -> Document:
    settings = get_settings()
    course = courses.get_owned_course(session, course_id, teacher)
    content = file.file.read(settings.max_upload_bytes + 1)
    document = documents.store_upload(
        session,
        storage,
        settings,
        course,
        teacher,
        file.filename or "documento",
        content,
    )
    background.add_task(
        documents.process_document,
        session_factory,
        llm,
        document.id,
        document.file_type,
        content,
    )
    return documents.to_schema(session, document)


@router.get("", response_model=Page[Document], responses=error_responses(404))
def list_documents(
    course_id: uuid.UUID, teacher: TeacherUser, session: DbSession, page: Pagination
) -> Page[Document]:
    course = courses.get_owned_course(session, course_id, teacher)
    rows, total = documents.list_documents(session, course, page.limit, page.offset)
    return Page[Document](
        items=[documents.to_schema(session, d) for d in rows],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/{document_id}", response_model=Document, responses=error_responses(404))
def read_document(
    course_id: uuid.UUID,
    document_id: uuid.UUID,
    teacher: TeacherUser,
    session: DbSession,
) -> Document:
    course = courses.get_owned_course(session, course_id, teacher)
    document = documents.get_course_document(session, course, document_id)
    return documents.to_schema(session, document)


@router.delete("/{document_id}", status_code=204, responses=error_responses(404))
def delete_document(
    course_id: uuid.UUID,
    document_id: uuid.UUID,
    teacher: TeacherUser,
    session: DbSession,
    storage: Storage,
) -> Response:
    course = courses.get_owned_course(session, course_id, teacher)
    document = documents.get_course_document(session, course, document_id)
    documents.delete(session, storage, document)
    return Response(status_code=204)


@router.post(
    "/{document_id}/validate",
    response_model=Document,
    responses=error_responses(404, 409),
)
def validate_document(
    course_id: uuid.UUID,
    document_id: uuid.UUID,
    teacher: TeacherUser,
    session: DbSession,
) -> Document:
    course = courses.get_owned_course(session, course_id, teacher)
    document = documents.get_course_document(session, course, document_id)
    documents.validate(session, document, teacher)
    return documents.to_schema(session, document)


@router.post(
    "/{document_id}/exclude",
    response_model=Document,
    responses=error_responses(404, 409),
)
def exclude_document(
    course_id: uuid.UUID,
    document_id: uuid.UUID,
    teacher: TeacherUser,
    session: DbSession,
) -> Document:
    course = courses.get_owned_course(session, course_id, teacher)
    document = documents.get_course_document(session, course, document_id)
    documents.exclude(session, document)
    return documents.to_schema(session, document)


@router.get(
    "/{document_id}/fragments",
    response_model=Page[Fragment],
    responses=error_responses(404),
)
def list_fragments(
    course_id: uuid.UUID,
    document_id: uuid.UUID,
    teacher: TeacherUser,
    session: DbSession,
    page: Pagination,
) -> Page[Fragment]:
    course = courses.get_owned_course(session, course_id, teacher)
    document = documents.get_course_document(session, course, document_id)
    rows, total = documents.list_fragments(session, document, page.limit, page.offset)
    return Page[Fragment](
        items=[Fragment.model_validate(f, from_attributes=True) for f in rows],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.patch(
    "/{document_id}/fragments/{fragment_id}",
    response_model=Fragment,
    responses=error_responses(404, 422),
)
def update_fragment(
    course_id: uuid.UUID,
    document_id: uuid.UUID,
    fragment_id: uuid.UUID,
    payload: FragmentUpdate,
    teacher: TeacherUser,
    session: DbSession,
) -> Fragment:
    course = courses.get_owned_course(session, course_id, teacher)
    document = documents.get_course_document(session, course, document_id)
    fragment = documents.get_fragment(session, document, fragment_id)
    fragment.excluded = payload.excluded
    session.flush()
    return Fragment.model_validate(fragment, from_attributes=True)


@router.get(
    "/{document_id}/file-url",
    response_model=SignedUrl,
    responses=error_responses(404, 503),
    summary="Short-lived link to the original file",
)
def file_url(
    course_id: uuid.UUID,
    document_id: uuid.UUID,
    teacher: TeacherUser,
    session: DbSession,
    storage: Storage,
) -> SignedUrl:
    course = courses.get_owned_course(session, course_id, teacher)
    document = documents.get_course_document(session, course, document_id)
    return documents.signed_url(storage, get_settings(), document)
