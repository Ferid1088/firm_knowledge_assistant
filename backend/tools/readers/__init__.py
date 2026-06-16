"""FILE_READER tools — registers all readers via ToolRegistry.discover_tools()."""
from backend.core.tool_registry import get_registry as _get_registry

# Trigger registration of all readers in this package via discovery.
# discover_tools() imports every non-underscore .py file in this directory,
# finds Tool subclasses, and calls register_tool() for each one.
# Tools whose optional dependencies are not installed are skipped with a warning.
_get_registry().discover_tools(
    search_paths=["backend/tools/readers"],
    base_module="backend",
)

# Re-export all reader classes for direct import by callers that need them by name.
from backend.tools.readers.pdf import PDFReaderTool
from backend.tools.readers.docx import DOCXReaderTool
from backend.tools.readers.xlsx import XLSXReaderTool
from backend.tools.readers.csv import CSVReaderTool
from backend.tools.readers.txt import TextReaderTool
from backend.tools.readers.eml import EMLReaderTool
from backend.tools.readers.image import ImageReaderTool
from backend.tools.readers.mbox import MBOXReaderTool
from backend.tools.readers.msg import MSGReaderTool
from backend.tools.readers.svg import SVGReaderTool
from backend.tools.readers.dwg import DWGReaderTool
from backend.tools.readers.dxf import DXFReaderTool
from backend.tools.readers.odt import ODTReaderTool
from backend.tools.readers.ods import ODSReaderTool
from backend.tools.readers.pptx import PPTXReaderTool

__all__ = [
    "PDFReaderTool",
    "DOCXReaderTool",
    "XLSXReaderTool",
    "CSVReaderTool",
    "TextReaderTool",
    "EMLReaderTool",
    "ImageReaderTool",
    "MBOXReaderTool",
    "MSGReaderTool",
    "SVGReaderTool",
    "DWGReaderTool",
    "DXFReaderTool",
    "ODTReaderTool",
    "ODSReaderTool",
    "PPTXReaderTool",
]
