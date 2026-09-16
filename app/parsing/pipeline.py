import uuid
from app.infra.minio_client import upload_file
from app.parsing.registry import get_parser
from app.parsing.schemas import ParseResult


async def parse_to_markdown(
    *, # 强制后面全部是关键字传参，不能位置传参
    file_data: bytes,
    file_type: str,
    file_name: str,
    owner_id: int,
    document_id: int,
    doc_uuid: str | None = None,
    progress_callback=None
) -> ParseResult:
    # 如果外部没有传入doc_uuid，则本地生成
    doc_uuid = doc_uuid or f"doc_{document_id}_{uuid.uuid4().hex[:8]}"
    # 解析器注册中心：根据文件后缀，分发到对应的解析器(PdfParser / DocxParser / ImageParser等)
    parser = get_parser(file_type)
    # 调用具体解析器的parse方法，真正执行解析逻辑
    result = await parser.parse(
        file_data=file_data,
        file_name=file_name,
        owner_id=owner_id,
        doc_uuid=doc_uuid,
        progress_callback=progress_callback
    )
    # 构造MinIO存储路径：用户隔离 + doc_uuid隔离，存放解析后的markdown
    md_key = f"users/{owner_id}/{doc_uuid}/parsed/content.md"
    # 将解析出来的markdown文本上传MinIO
    upload_file(
        result.markdown.encode("utf-8"),
        md_key,
        "text/markdown; charset=utf-8",
    )
    # 回填minio key到返回对象，补充元数据
    result.markdown_key = md_key
    result.metadata["doc_uuid"] = doc_uuid
    return result