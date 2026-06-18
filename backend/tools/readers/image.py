"""ImageReaderTool — read raster image files; preserves binary for OCR downstream."""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from backend.core.tool_base import ToolMetadata
from backend.tools.readers.base import FileReaderTool, RawContent

logger = logging.getLogger(__name__)

_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
}


class ImageReaderTool(FileReaderTool):
    """Read raster images (PNG/JPG/TIFF); return raw bytes for downstream OCR."""

    metadata = ToolMetadata(
        name="reader:image",
        version="1.0.0",
        tool_type="reader",
        description="Read raster image files (PNG, JPG, TIFF); pass binary to OCR",
        dependencies=["Pillow>=9.0"],
        capabilities={
            "formats": [".png", ".jpg", ".jpeg", ".tiff", ".tif", ".PNG", ".JPG", ".JPEG"],
            "max_size": 50 * 1024 * 1024,
            "output_binary": True,
        },
        is_production=True,
        is_async=True,
    )

    supported_extensions = [".png", ".jpg", ".jpeg", ".tiff", ".tif", ".PNG", ".JPG", ".JPEG"]
    format_name = "image"

    def _validate_dependencies(self) -> None:
        """Verify Pillow is installed; it ships as 'Pillow' but imports as 'PIL'."""
        # Pillow's pip package is 'Pillow' but it imports as 'PIL'
        import importlib
        try:
            importlib.import_module("PIL")
        except ImportError:
            raise ImportError(
                f"Tool '{self.metadata.name}' requires 'Pillow>=9.0'. "
                "Install with: pip install Pillow"
            )

    async def execute(self, input_data: str, **kwargs) -> RawContent:
        """Validate and read the image file; return raw bytes + confidence=0.5 (OCR needed)."""
        file_path = str(input_data)
        is_valid, error = await self.validate_input(file_path)
        if not is_valid:
            return RawContent(
                format="image",
                content=b"",
                mime_type="image/png",
                is_corrupted=True,
                warnings=[error],
            )

        try:
            from PIL import Image

            p = Path(file_path)
            # Validate the image is readable
            with Image.open(file_path) as img:
                img.verify()

            raw_bytes = p.read_bytes()
            mime = _MIME.get(p.suffix.lower(), "image/png")

            return RawContent(
                format="image",
                content=raw_bytes,
                mime_type=mime,
                page_count=1,
                image_count=1,
                # 0.5 = file is intact and readable, but text extraction requires OCR
                extraction_confidence=0.5,
                warnings=["Image content requires OCR for text extraction"],
                file_size=p.stat().st_size,
                modified_time=datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
            )

        except Exception as e:
            return self._handle_error(e, file_path)
