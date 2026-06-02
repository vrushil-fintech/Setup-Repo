from datetime import datetime
from typing import Annotated, List
from pydantic import BaseModel, Field
from pydantic import BeforeValidator

PyObjectId = Annotated[str, BeforeValidator(str)]

class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: str | None = None


class User(BaseModel):
    userid: str
    name: str
    email: str
    role: bool = False
    organization: str | None = None
    created_at: datetime | None = None

class UserInDB(User):
    hashed_password: str

class AnalysisHistoryItem(BaseModel):
    id: int | str
    factor: str
    created_at: datetime
    file_name: str

class AnalysisHistoryResponse(BaseModel):
    analysis_history: List[AnalysisHistoryItem]

class IssueItem(BaseModel):
    uid: str | None = None
    issue: str | None = None
    issue_code_snippet: str | None = None
    severity: str | None = None
    solution: str | None = None
    solution_code_snippet: str | None = None

class IssueItemResponse(BaseModel):
    id: PyObjectId | str | None = None
    uid: str | None = None
    issue: str | None = None
    issue_code_snippet: str | None = None
    severity: str | None = None
    severity_level: int | None = None
    solution: str | None = None
    solution_code_snippet: str | None = None
    start_line: int | None = None
    end_line: int | None = None

class CharAnalysis(BaseModel):
    characteristic: str | None = None
    description_of_characteristic: str | None = None
    issue_items: List[IssueItem | None] | None = None

class CharAnalysisResponse(BaseModel):
    characteristic: str | None = None
    description_of_characteristic: str | None = None
    issue_items: List[IssueItemResponse | None] | None = None

class FactorAnalysis(BaseModel):
    id: PyObjectId | None = Field(alias="_id", default=None)
    userid: str | None = None
    factor: str | None = None
    created_at: datetime | None = None
    file_name: str | None = None
    analysis: List[PyObjectId | None] | None = None
    language: str | None = None

class FactorAnalysisResponse(BaseModel):
    id: PyObjectId | str | None = None
    user_id: str | None = None
    factor: str | None = None
    created_at: datetime | None = None
    file_name: str | None = None
    analysis: List[CharAnalysisResponse | None] | str | None = None
    analysis_type: str | None = None
    language: str | None = None
    feedback: str | None = None

class ResponseClass(BaseModel):
    status_code: int
    error_message: str | None = None
    analysis_id: int | PyObjectId | None = None
    content: FactorAnalysisResponse | None = None
    analysis_type: str | None = None

class LLMUsage(BaseModel):
    input_tokens: int = 0
    cached_input_tokens: int = 0
    response_tokens: int = 0
    total_tokens: int = 0
    llm_deployment: str = ""
    cost: float = 0.0
