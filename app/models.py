from pydantic import BaseModel


class AnalyzeRequest(BaseModel):
    project_id: str
    bug_report: str = ""
    error_trace: str = ""
    top_n: int = 8


class FixRequest(BaseModel):
    project_id: str
    suspect_id: str
    instructions: str = ""
    apply_fix: bool = False


class FileContent(BaseModel):
    path: str
    content: str
    