from __future__ import annotations

import html
import re

from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

from markdown_it import MarkdownIt


MAX_DOCUMENT_BYTES = 512 * 1024
MAX_RENDERED_BYTES = 1024 * 1024


class DocsProviderError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


_ALLOWED_TAGS = {
    "a",
    "blockquote",
    "br",
    "code",
    "del",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "li",
    "ol",
    "p",
    "pre",
    "strong",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "ul",
}

_VOID_TAGS = {
    "br",
    "hr",
}

_LANGUAGE_CLASS_RE = re.compile(
    r"^language-[A-Za-z0-9_+.-]{1,64}$"
)


def _safe_href(value: str) -> str | None:
    value = value.strip()

    if not value:
        return None

    parsed = urlsplit(value)

    scheme = parsed.scheme.lower()

    if scheme in {
        "http",
        "https",
        "mailto",
    }:
        return value

    if (
        scheme == ""
        and parsed.netloc == ""
    ):
        return value

    return None


class _HtmlSanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(
            convert_charrefs=True
        )

        self.output: list[str] = []


    def handle_starttag(
        self,
        tag: str,
        attrs: list[
            tuple[
                str,
                str | None,
            ]
        ],
    ) -> None:
        tag = tag.lower()

        if tag not in _ALLOWED_TAGS:
            return

        clean: list[
            tuple[
                str,
                str,
            ]
        ] = []

        if tag == "a":
            for key, value in attrs:
                if value is None:
                    continue

                if key == "href":
                    href = _safe_href(
                        value
                    )

                    if href is not None:
                        clean.append(
                            (
                                "href",
                                href,
                            )
                        )

                elif key == "title":
                    clean.append(
                        (
                            "title",
                            value,
                        )
                    )

        elif tag == "code":
            for key, value in attrs:
                if (
                    key == "class"
                    and value is not None
                    and _LANGUAGE_CLASS_RE.fullmatch(
                        value
                    )
                ):
                    clean.append(
                        (
                            "class",
                            value,
                        )
                    )

        rendered_attrs = "".join(
            f' {key}="{html.escape(value, quote=True)}"'
            for key, value in clean
        )

        self.output.append(
            f"<{tag}{rendered_attrs}>"
        )


    def handle_startendtag(
        self,
        tag: str,
        attrs: list[
            tuple[
                str,
                str | None,
            ]
        ],
    ) -> None:
        tag = tag.lower()

        if tag not in _VOID_TAGS:
            return

        self.output.append(
            f"<{tag}>"
        )


    def handle_endtag(
        self,
        tag: str,
    ) -> None:
        tag = tag.lower()

        if (
            tag in _ALLOWED_TAGS
            and tag not in _VOID_TAGS
        ):
            self.output.append(
                f"</{tag}>"
            )


    def handle_data(
        self,
        data: str,
    ) -> None:
        self.output.append(
            html.escape(
                data,
                quote=False,
            )
        )


def _render_markdown(
    source: str,
) -> str:
    renderer = MarkdownIt(
        "commonmark",
        {
            "html": False,
            "linkify": False,
            "typographer": False,
        },
    )

    for rule in (
        "table",
        "strikethrough",
    ):
        try:
            renderer.enable(rule)
        except KeyError:
            pass

    rendered = renderer.render(
        source
    )

    sanitizer = _HtmlSanitizer()
    sanitizer.feed(rendered)
    sanitizer.close()

    return "".join(
        sanitizer.output
    )


def _docs_config(
    config: dict[str, Any],
) -> tuple[
    Path,
    str,
    bool,
]:
    section = config.get(
        "docs",
        {},
    )

    if not isinstance(
        section,
        dict,
    ):
        raise DocsProviderError(
            "configuration_error",
            "Некорректная конфигурация документации",
        )

    raw_path = section.get(
        "path",
    )

    extension = section.get(
        "extension",
        ".md",
    )

    recursive = section.get(
        "recursive",
        True,
    )

    if (
        not isinstance(raw_path, str)
        or not raw_path
    ):
        raise DocsProviderError(
            "configuration_error",
            "Не задан путь к документации",
        )

    if (
        not isinstance(extension, str)
        or not extension.startswith(".")
        or len(extension) > 16
    ):
        raise DocsProviderError(
            "configuration_error",
            "Некорректное расширение документации",
        )

    if not isinstance(
        recursive,
        bool,
    ):
        raise DocsProviderError(
            "configuration_error",
            "docs.recursive должен быть boolean",
        )

    root = Path(
        raw_path
    )

    try:
        root = root.resolve(
            strict=True
        )
    except OSError as exc:
        raise DocsProviderError(
            "docs_unavailable",
            "Каталог документации недоступен",
        ) from exc

    if not root.is_dir():
        raise DocsProviderError(
            "docs_unavailable",
            "Путь документации не является каталогом",
        )

    return (
        root,
        extension,
        recursive,
    )


def _document_title(
    path: Path,
) -> str:
    try:
        with path.open(
            "r",
            encoding="utf-8",
        ) as fh:
            for _ in range(80):
                line = fh.readline()

                if not line:
                    break

                match = re.match(
                    r"^\s*#\s+(.+?)\s*$",
                    line,
                )

                if match:
                    title = re.sub(
                        r"[`*_~]+",
                        "",
                        match.group(1),
                    ).strip()

                    if title:
                        return title

    except (
        OSError,
        UnicodeError,
    ):
        pass

    name = path.stem

    name = re.sub(
        r"^\d+[-_ ]*",
        "",
        name,
    )

    return (
        name.replace(
            "-",
            " ",
        )
        .replace(
            "_",
            " ",
        )
        .strip()
        or path.name
    )


def _resolve_document(
    config: dict[str, Any],
    document: str,
) -> tuple[
    Path,
    Path,
]:
    root, extension, _ = _docs_config(
        config
    )

    if (
        not isinstance(document, str)
        or not document
        or len(document) > 512
        or "\x00" in document
    ):
        raise DocsProviderError(
            "invalid_document",
            "Некорректное имя документа",
        )

    pure = PurePosixPath(
        document
    )

    if (
        pure.is_absolute()
        or any(
            part in {"", ".", ".."}
            or part.startswith(".")
            for part in pure.parts
        )
    ):
        raise DocsProviderError(
            "invalid_document",
            "Некорректный путь документа",
        )

    if pure.suffix != extension:
        raise DocsProviderError(
            "invalid_document",
            "Недопустимое расширение документа",
        )

    source = root.joinpath(
        *pure.parts
    )

    try:
        resolved = source.resolve(
            strict=True
        )
    except OSError as exc:
        raise DocsProviderError(
            "document_not_found",
            "Документ не найден",
        ) from exc

    try:
        resolved.relative_to(
            root
        )
    except ValueError as exc:
        raise DocsProviderError(
            "invalid_document",
            "Документ находится за пределами каталога документации",
        ) from exc

    if not resolved.is_file():
        raise DocsProviderError(
            "document_not_found",
            "Документ не найден",
        )

    return root, resolved


def list_documents(
    config: dict[str, Any],
) -> dict[str, Any]:
    root, extension, recursive = _docs_config(
        config
    )

    iterator = (
        root.rglob(
            f"*{extension}"
        )
        if recursive
        else root.glob(
            f"*{extension}"
        )
    )

    documents: list[
        dict[str, str]
    ] = []

    for source in iterator:
        try:
            resolved = source.resolve(
                strict=True
            )

            relative = resolved.relative_to(
                root
            )

        except (
            OSError,
            ValueError,
        ):
            continue

        if not resolved.is_file():
            continue

        if any(
            part.startswith(".")
            for part in relative.parts
        ):
            continue

        documents.append(
            {
                "id":
                    relative.as_posix(),

                "title":
                    _document_title(
                        resolved
                    ),

                "filename":
                    relative.name,
            }
        )

    documents.sort(
        key=lambda row:
            row["id"].casefold()
    )

    return {
        "count": len(documents),
        "documents": documents,
    }


def read_document(
    config: dict[str, Any],
    document: str,
) -> dict[str, Any]:
    root, resolved = _resolve_document(
        config,
        document,
    )

    try:
        stat = resolved.stat()

    except OSError as exc:
        raise DocsProviderError(
            "docs_unavailable",
            "Не удалось прочитать документ",
        ) from exc

    if stat.st_size > MAX_DOCUMENT_BYTES:
        raise DocsProviderError(
            "document_too_large",
            "Документ слишком большой",
        )

    try:
        source = resolved.read_text(
            encoding="utf-8"
        )

    except UnicodeError as exc:
        raise DocsProviderError(
            "invalid_encoding",
            "Документ должен быть в UTF-8",
        ) from exc

    except OSError as exc:
        raise DocsProviderError(
            "docs_unavailable",
            "Не удалось прочитать документ",
        ) from exc

    relative = resolved.relative_to(
        root
    ).as_posix()

    rendered = _render_markdown(
        source
    )

    if len(rendered.encode("utf-8")) > MAX_RENDERED_BYTES:
        raise DocsProviderError(
            "document_too_large",
            "Отрендеренный документ слишком большой",
        )

    return {
        "id": relative,
        "title":
            _document_title(
                resolved
            ),
        "size_bytes":
            stat.st_size,
        "html": rendered,
    }
